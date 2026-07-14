"""수집 서비스 단위 테스트"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.collector.client import BidNotice
from app.collector.client import BidResult as BidResultData
from app.collector.service import (
    _upsert_agency,
    _upsert_bid,
    collect_notices,
    collect_results,
)
from app.models import Agency, Bid, CollectionLog


# ------------------------------------------------------------------ #
# 헬퍼                                                                 #
# ------------------------------------------------------------------ #


def _make_notice(
    announcement_no: str = "20240001",
    title: str = "테스트 공고",
    agency_name: str = "서울시",
    base_amount: int = 1_000_000,
) -> BidNotice:
    return BidNotice(
        announcement_no=announcement_no,
        title=title,
        agency_name=agency_name,
        base_amount=base_amount,
        notice_date="202401010900",
        bid_open_date="202401100900",
        bid_type="construction",
    )


def _make_result_data(
    announcement_no: str = "20240001",
    biz_reg_no: str = "123-45-67890",
    is_winner: bool = True,
) -> BidResultData:
    return BidResultData(
        announcement_no=announcement_no,
        competitor_name="(주)테스트건설",
        biz_reg_no=biz_reg_no,
        bid_amount=950_000,
        bid_rate=0.9500,
        rank=1,
        is_winner=is_winner,
    )


def _mock_db(*first_values):
    """db.query().filter().first()가 순서대로 반환할 값들로 MagicMock DB 생성"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = list(first_values)
    return db


# ------------------------------------------------------------------ #
# upsert 중복 처리                                                     #
# ------------------------------------------------------------------ #


class TestUpsertBid:
    def test_creates_bid_when_not_found(self):
        """announcement_no 미존재 → Bid 생성 후 db.add 호출"""
        db = _mock_db(None)
        notice = _make_notice("BID-001")

        bid, is_new = _upsert_bid(db, notice, agency_id=1)

        assert is_new is True
        db.add.assert_called_once()
        db.flush.assert_called_once()
        added = db.add.call_args.args[0]
        assert isinstance(added, Bid)
        assert added.announcement_no == "BID-001"

    def test_updates_existing_bid_on_duplicate(self):
        """동일 announcement_no 재수집 → title·base_amount 업데이트, db.add 미호출"""
        existing = Bid(
            announcement_no="BID-002",
            title="원본 제목",
            agency_id=1,
            base_amount=1_000_000,
        )
        db = _mock_db(existing)
        notice = _make_notice("BID-002", title="수정된 제목", base_amount=2_000_000)

        bid, is_new = _upsert_bid(db, notice, agency_id=1)

        assert is_new is False
        assert bid.title == "수정된 제목"
        assert bid.base_amount == 2_000_000
        db.add.assert_not_called()

    def test_same_announcement_no_add_called_once(self):
        """같은 announcement_no 2회 수집 → db.add(Bid) 1회만 호출"""
        created = Bid(
            announcement_no="BID-003",
            title="테스트 공고",
            agency_id=1,
            base_amount=1_000_000,
        )
        # 첫 번째 조회 → None(신규), 두 번째 조회 → 기존 Bid(업데이트)
        db = _mock_db(None, created)

        _upsert_bid(db, _make_notice("BID-003", title="원본"), agency_id=1)
        _upsert_bid(db, _make_notice("BID-003", title="수정"), agency_id=1)

        # add는 첫 번째 insert 1회만
        assert db.add.call_count == 1


# ------------------------------------------------------------------ #
# CollectionLog 기록 검증                                             #
# ------------------------------------------------------------------ #


class TestCollectionLog:
    def test_collect_notices_creates_one_log(self, mocker):
        """collect_notices() 완료 후 CollectionLog 1건 db.add"""
        client = MagicMock()
        client.paginate_construction_bids.return_value = iter([[_make_notice("BID-L01")]])

        db = MagicMock()
        mocker.patch("app.collector.service._upsert_agency", return_value=MagicMock(id=1))
        mocker.patch("app.collector.service._upsert_bid", return_value=(MagicMock(), True))

        log = collect_notices(db, client, "notice_cnstwk", days_back=1)

        assert isinstance(log, CollectionLog)
        added_types = [type(c.args[0]) for c in db.add.call_args_list]
        assert CollectionLog in added_types

    def test_log_collect_type_matches_argument(self, mocker):
        """collect_type 인자가 CollectionLog.collect_type에 그대로 기록된다"""
        client = MagicMock()
        client.paginate_service_bids.return_value = iter([[_make_notice()]])

        db = MagicMock()
        mocker.patch("app.collector.service._upsert_agency", return_value=MagicMock(id=1))
        mocker.patch("app.collector.service._upsert_bid", return_value=(MagicMock(), True))

        log = collect_notices(db, client, "notice_servc", days_back=1)

        assert log.collect_type == "notice_servc"

    def test_log_success_count(self, mocker):
        """공고 3건 성공 → success_count == 3, fail_count == 0"""
        notices = [_make_notice(f"BID-{i:03d}") for i in range(3)]
        client = MagicMock()
        client.paginate_construction_bids.return_value = iter([notices])

        db = MagicMock()
        mocker.patch("app.collector.service._upsert_agency", return_value=MagicMock(id=1))
        mocker.patch("app.collector.service._upsert_bid", return_value=(MagicMock(), True))

        log = collect_notices(db, client, "notice_cnstwk", days_back=1)

        assert log.success_count == 3
        assert log.fail_count == 0

    def test_collect_results_log_type(self, mocker):
        """collect_results() 완료 후 CollectionLog.collect_type == 'result'"""
        client = MagicMock()
        client.paginate_bid_results.return_value = iter([])

        db = MagicMock()

        log = collect_results(db, client, days_back=1)

        assert isinstance(log, CollectionLog)
        assert log.collect_type == "result"


# ------------------------------------------------------------------ #
# 수집 실패 → error_summary 기록                                       #
# ------------------------------------------------------------------ #


class TestCollectionError:
    def test_upsert_failure_records_error_summary(self, mocker):
        """개별 공고 저장 실패 시 fail_count 증가 + error_summary 기록"""
        client = MagicMock()
        client.paginate_construction_bids.return_value = iter([[_make_notice("BID-ERR")]])

        db = MagicMock()
        mocker.patch(
            "app.collector.service._upsert_agency",
            side_effect=Exception("DB 연결 오류"),
        )

        log = collect_notices(db, client, "notice_cnstwk", days_back=1)

        assert log.fail_count == 1
        assert log.success_count == 0
        assert log.error_summary is not None
        assert "DB 연결 오류" in log.error_summary

    def test_pagination_error_records_error_summary(self):
        """페이지네이션 중 예외 발생 시 error_summary에 기록"""
        client = MagicMock()
        client.paginate_construction_bids.side_effect = RuntimeError("API 연결 실패")

        db = MagicMock()

        log = collect_notices(db, client, "notice_cnstwk", days_back=1)

        assert log.error_summary is not None
        assert "API 연결 실패" in log.error_summary

    def test_partial_failure_counts_correctly(self, mocker):
        """3건 중 1건 실패 → success_count=2, fail_count=1"""
        notices = [_make_notice(f"BID-{i:03d}") for i in range(3)]
        client = MagicMock()
        client.paginate_construction_bids.return_value = iter([notices])

        db = MagicMock()
        mocker.patch("app.collector.service._upsert_agency", return_value=MagicMock(id=1))

        call_count = [0]

        def upsert_bid_se(db_, notice_, agency_id_):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("두 번째 공고 저장 실패")
            return MagicMock(), True

        mocker.patch("app.collector.service._upsert_bid", side_effect=upsert_bid_se)

        log = collect_notices(db, client, "notice_cnstwk", days_back=1)

        assert log.success_count == 2
        assert log.fail_count == 1
        assert log.error_summary is not None
