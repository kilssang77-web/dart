"""나라장터 API 클라이언트 단위 테스트"""
from __future__ import annotations

import pytest
import httpx

from app.collector.client import BidNotice, BidResult, NarajangterClient


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


@pytest.fixture()
def api_key() -> str:
    return "TEST_API_KEY_1234"


@pytest.fixture()
def client(api_key: str) -> NarajangterClient:
    return NarajangterClient(api_key=api_key)


def _make_notice_response(items: list[dict], total: int = 1, page: int = 1) -> dict:
    item_node = items[0] if len(items) == 1 else items
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": {"item": item_node},
                "numOfRows": 100,
                "pageNo": page,
                "totalCount": total,
            },
        }
    }


def _make_empty_response() -> dict:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": "", "numOfRows": 100, "pageNo": 1, "totalCount": 0},
        }
    }


CONSTRUCTION_ITEM = {
    "bidNtceNo": "20240001001",
    "bidNtceNm": "서울 도로 포장 공사",
    "ntceInsttNm": "서울특별시",
    "asignBdgtAmt": "100000000",
    "bidNtceDt": "202401010900",
    "opengDt": "202401100900",
    "indutyNm": "토목공사",
    "rgstTyNm": "서울",
}

RESULT_ITEM = {
    "bidNtceNo": "20240001001",
    "corpNm": "테스트건설(주)",
    "bizRegNo": "1234567890",
    "bidAmt": "97500000",
    "rate": "0.9750",
    "rank": "1",
    "sucsfbidYn": "Y",
}


# ------------------------------------------------------------------ #
# NARA_API_KEY 검증                                                    #
# ------------------------------------------------------------------ #


def test_missing_api_key_raises_value_error(monkeypatch):
    """G2B_API_KEY 미설정 시 ValueError 발생 확인"""
    monkeypatch.setenv("G2B_API_KEY", "")

    # lru_cache 무력화
    from app import config as cfg
    cfg.get_settings.cache_clear()

    with pytest.raises(ValueError, match="G2B_API_KEY"):
        NarajangterClient()

    cfg.get_settings.cache_clear()


# ------------------------------------------------------------------ #
# 응답 파싱 — BidNotice                                               #
# ------------------------------------------------------------------ #


def test_parse_construction_notice(mocker, client: NarajangterClient):
    """공사 입찰공고 응답 파싱 정확도 검증"""
    mock_response = _make_notice_response([CONSTRUCTION_ITEM])
    mocker.patch.object(client, "_get", return_value=mock_response)

    raw = client.get_construction_bids("202401010000", "202401310000")
    items = NarajangterClient._extract_items(raw)
    notices = [NarajangterClient._parse_notice(i, "construction") for i in items]

    assert len(notices) == 1
    n: BidNotice = notices[0]
    assert n.announcement_no == "20240001001"
    assert n.title == "서울 도로 포장 공사"
    assert n.agency_name == "서울특별시"
    assert n.base_amount == 100_000_000
    assert n.bid_type == "construction"
    assert n.notice_date == "202401010900"
    assert n.bid_open_date == "202401100900"
    assert n.industry_code == "토목공사"


def test_parse_service_notice(mocker, client: NarajangterClient):
    """용역 입찰공고 bid_type 매핑 확인"""
    item = {**CONSTRUCTION_ITEM, "bidNtceNo": "20240002001"}
    mock_response = _make_notice_response([item])
    mocker.patch.object(client, "_get", return_value=mock_response)

    raw = client.get_service_bids("202401010000", "202401310000")
    items = NarajangterClient._extract_items(raw)
    notice = NarajangterClient._parse_notice(items[0], "service")

    assert notice.bid_type == "service"
    assert notice.announcement_no == "20240002001"


def test_parse_notice_missing_amount(mocker, client: NarajangterClient):
    """기초금액 누락 시 None 처리 확인"""
    item = {**CONSTRUCTION_ITEM, "asignBdgtAmt": None}
    mock_response = _make_notice_response([item])
    mocker.patch.object(client, "_get", return_value=mock_response)

    raw = client.get_construction_bids("202401010000", "202401310000")
    items = NarajangterClient._extract_items(raw)
    notice = NarajangterClient._parse_notice(items[0], "construction")

    assert notice.base_amount is None


# ------------------------------------------------------------------ #
# 응답 파싱 — BidResult                                               #
# ------------------------------------------------------------------ #


def test_parse_bid_result(mocker, client: NarajangterClient):
    """낙찰결과 응답 파싱 정확도 검증"""
    mock_response = _make_notice_response([RESULT_ITEM])
    mocker.patch.object(client, "_get", return_value=mock_response)

    raw = client.get_bid_results("202401010000", "202401310000")
    items = NarajangterClient._extract_items(raw)
    result: BidResult = NarajangterClient._parse_bid_result(items[0])

    assert result.announcement_no == "20240001001"
    assert result.competitor_name == "테스트건설(주)"
    assert result.biz_reg_no == "1234567890"
    assert result.bid_amount == 97_500_000
    assert result.bid_rate == pytest.approx(0.975)
    assert result.rank == 1
    assert result.is_winner is True


def test_parse_bid_result_loser(mocker, client: NarajangterClient):
    """낙찰 실패 항목 is_winner=False 확인"""
    item = {**RESULT_ITEM, "sucsfbidYn": "N", "rank": "2"}
    mock_response = _make_notice_response([item])
    mocker.patch.object(client, "_get", return_value=mock_response)

    raw = client.get_bid_results("202401010000", "202401310000")
    items = NarajangterClient._extract_items(raw)
    result = NarajangterClient._parse_bid_result(items[0])

    assert result.is_winner is False
    assert result.rank == 2


# ------------------------------------------------------------------ #
# 재시도 로직                                                          #
# ------------------------------------------------------------------ #


def test_retry_succeeds_on_third_attempt(mocker, client: NarajangterClient):
    """2회 실패 후 3번째 시도에서 성공하는 재시도 로직 검증"""
    mock_sleep = mocker.patch("app.collector.client.time.sleep")
    success_response = _make_notice_response([CONSTRUCTION_ITEM])

    call_count = 0

    def fake_get_side_effect(url, params):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("연결 실패")
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = success_response
        return mock_resp

    mock_client_instance = mocker.MagicMock()
    mock_client_instance.__enter__ = mocker.MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = mocker.MagicMock(return_value=False)
    mock_client_instance.get.side_effect = fake_get_side_effect
    mocker.patch("app.collector.client.httpx.Client", return_value=mock_client_instance)

    result = client.get_construction_bids("202401010000", "202401310000")

    assert call_count == 3
    assert mock_sleep.call_count == 2
    assert NarajangterClient._extract_items(result) != []


def test_retry_raises_after_max_attempts(mocker, client: NarajangterClient):
    """최대 재시도(3회) 소진 후 예외 전파 확인"""
    mocker.patch("app.collector.client.time.sleep")

    mock_client_instance = mocker.MagicMock()
    mock_client_instance.__enter__ = mocker.MagicMock(return_value=mock_client_instance)
    mock_client_instance.__exit__ = mocker.MagicMock(return_value=False)
    mock_client_instance.get.side_effect = httpx.ConnectError("연결 거부")
    mocker.patch("app.collector.client.httpx.Client", return_value=mock_client_instance)

    with pytest.raises(httpx.ConnectError):
        client.get_construction_bids("202401010000", "202401310000")

    assert mock_client_instance.get.call_count == 3


# ------------------------------------------------------------------ #
# 페이지네이션                                                         #
# ------------------------------------------------------------------ #


def test_pagination_single_page(mocker, client: NarajangterClient):
    """totalCount <= numOfRows 이면 1페이지만 순회"""
    response = _make_notice_response([CONSTRUCTION_ITEM], total=1)
    mocker.patch.object(client, "_get", return_value=response)

    pages = list(client.paginate_construction_bids("202401010000", "202401310000"))

    assert len(pages) == 1
    assert len(pages[0]) == 1
    assert pages[0][0].announcement_no == "20240001001"


def test_pagination_multiple_pages(mocker, client: NarajangterClient):
    """totalCount > numOfRows 이면 여러 페이지 순회"""
    item_p1 = {**CONSTRUCTION_ITEM, "bidNtceNo": "20240001001"}
    item_p2 = {**CONSTRUCTION_ITEM, "bidNtceNo": "20240001002"}

    responses = [
        _make_notice_response([item_p1], total=2, page=1),
        _make_notice_response([item_p2], total=2, page=2),
    ]
    mocker.patch.object(client, "_get", side_effect=responses)

    pages = list(client.paginate_construction_bids("202401010000", "202401310000", num_of_rows=1))

    assert len(pages) == 2
    assert pages[0][0].announcement_no == "20240001001"
    assert pages[1][0].announcement_no == "20240001002"


def test_pagination_empty_response(mocker, client: NarajangterClient):
    """빈 응답 시 페이지 없이 종료"""
    mocker.patch.object(client, "_get", return_value=_make_empty_response())

    pages = list(client.paginate_construction_bids("202401010000", "202401310000"))

    assert pages == []


def test_pagination_bid_results(mocker, client: NarajangterClient):
    """낙찰결과 페이지네이션 정상 동작 확인"""
    result_p1 = {**RESULT_ITEM, "bidNtceNo": "20240001001"}
    result_p2 = {**RESULT_ITEM, "bidNtceNo": "20240001002"}

    responses = [
        _make_notice_response([result_p1], total=2, page=1),
        _make_notice_response([result_p2], total=2, page=2),
    ]
    mocker.patch.object(client, "_get", side_effect=responses)

    pages = list(client.paginate_bid_results("202401010000", "202401310000", num_of_rows=1))

    assert len(pages) == 2
    assert pages[0][0].announcement_no == "20240001001"
    assert pages[1][0].announcement_no == "20240001002"
