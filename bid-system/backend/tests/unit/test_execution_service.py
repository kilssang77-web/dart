"""ExecutionService unit tests — CRUD + defeat analysis + import logic"""
from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import ExecutionService


# ── helpers ─────────────────────────────────────────────────────────────────

def _exec(
    id=1, user_id=1, title="테스트 공고",
    status="검토중", agency_name="테스트기관",
    base_amount=100_000_000, bid_open_date=None,
    submitted_rate=None, winner_rate=None,
    total_bidders=None, result_rank=None,
    floor_rate=None, announcement_no=None,
):
    obj = MagicMock()
    obj.id = id
    obj.user_id = user_id
    obj.title = title
    obj.status = status
    obj.agency_name = agency_name
    obj.base_amount = base_amount
    obj.bid_open_date = bid_open_date or datetime(2026, 7, 1)
    obj.submitted_rate = submitted_rate
    obj.winner_rate = winner_rate
    obj.total_bidders = total_bidders
    obj.result_rank = result_rank
    obj.floor_rate = floor_rate
    obj.announcement_no = announcement_no
    return obj


def _db_returning(obj):
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = obj
    q.filter.return_value.count.return_value = 1
    q.filter.return_value.all.return_value = [obj] if obj else []
    q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [obj] if obj else []
    q.group_by.return_value.all.return_value = [("검토중", 1)]
    q.filter.return_value.group_by.return_value.all.return_value = [("검토중", 1)]
    db.query.return_value = q
    return db


def _update_data(status: str, **kwargs):
    """Create a mock Pydantic model_dump-compatible update payload."""
    data = MagicMock()
    data.status = status
    d = {"status": status, **kwargs}
    data.model_dump.return_value = d
    return data


# ── get_summary ──────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_returns_status_counts_and_today_closing(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.group_by.return_value.all.return_value = [
            ("검토중", 2), ("참여결정", 1)
        ]
        q.filter.return_value.all.return_value = []
        db.query.return_value = q

        svc = ExecutionService(db)
        result = svc.get_summary(user_id=1)

        assert "status_counts" in result
        assert "today_closing" in result

    def test_summary_includes_all_status_keys(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.group_by.return_value.all.return_value = []
        q.filter.return_value.all.return_value = []
        db.query.return_value = q

        svc = ExecutionService(db)
        result = svc.get_summary(user_id=1)

        for status in ExecutionService.STATUS_ORDER:
            assert status in result["status_counts"]

    def test_summary_counts_default_zero(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.group_by.return_value.all.return_value = []
        q.filter.return_value.all.return_value = []
        db.query.return_value = q

        svc = ExecutionService(db)
        result = svc.get_summary(user_id=1)

        assert all(v == 0 for v in result["status_counts"].values())


# ── get ──────────────────────────────────────────────────────────────────────

class TestGet:
    def test_returns_execution_when_found(self):
        obj = _exec()
        svc = ExecutionService(_db_returning(obj))
        result = svc.get(1)
        assert result is obj

    def test_returns_none_when_not_found(self):
        svc = ExecutionService(_db_returning(None))
        result = svc.get(999)
        assert result is None


# ── delete ───────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_removes_defeat_analyses_first(self):
        obj = _exec(id=5, user_id=1)
        db = _db_returning(obj)

        svc = ExecutionService(db)
        svc.delete(5, user_id=1)

        # DefeatAnalysis delete must be called before BidExecution delete
        db.query.return_value.filter.return_value.delete.assert_called_once()
        db.delete.assert_called_once_with(obj)
        db.commit.assert_called_once()

    def test_delete_no_op_when_not_found(self):
        db = _db_returning(None)
        svc = ExecutionService(db)
        svc.delete(999, user_id=1)
        db.delete.assert_not_called()
        db.commit.assert_not_called()


# ── _auto_defeat_analysis ────────────────────────────────────────────────────

class TestAutoDefeatAnalysis:
    def _svc_no_existing_da(self):
        db = MagicMock()
        q = MagicMock()
        # DefeatAnalysis query returns None (no existing)
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        return ExecutionService(db)

    def test_cause_투찰률과도_when_rate_gap_large(self):
        svc = self._svc_no_existing_da()
        obj = _exec(submitted_rate=0.905, winner_rate=0.895)

        from app.models import DefeatAnalysis
        created = []

        def fake_add(o):
            created.append(o)

        svc.db.add.side_effect = fake_add
        svc._auto_defeat_analysis(obj)

        assert svc.db.add.called
        added = svc.db.add.call_args[0][0]
        assert added.cause_primary == "투찰률과도"

    def test_cause_투찰률과도_미세_when_rate_gap_small(self):
        svc = self._svc_no_existing_da()
        # gap = 0.003 → "투찰률과도" (미세)
        obj = _exec(submitted_rate=0.9023, winner_rate=0.8993)
        svc._auto_defeat_analysis(obj)
        added = svc.db.add.call_args[0][0]
        assert added.cause_primary == "투찰률과도"

    def test_cause_경쟁사과다_when_many_bidders(self):
        svc = self._svc_no_existing_da()
        # No rate data, but 20 bidders
        obj = _exec(submitted_rate=None, winner_rate=None, total_bidders=20)
        svc._auto_defeat_analysis(obj)
        added = svc.db.add.call_args[0][0]
        assert added.cause_primary == "경쟁사과다"

    def test_cause_기타_when_no_data(self):
        svc = self._svc_no_existing_da()
        obj = _exec(submitted_rate=None, winner_rate=None, total_bidders=5)
        svc._auto_defeat_analysis(obj)
        added = svc.db.add.call_args[0][0]
        assert added.cause_primary == "기타"

    def test_winner_gap_pct_computed_correctly(self):
        svc = self._svc_no_existing_da()
        # submitted 90.5%, winner 90.0% → gap = 0.5%p
        obj = _exec(submitted_rate=0.905, winner_rate=0.900)
        svc._auto_defeat_analysis(obj)
        added = svc.db.add.call_args[0][0]
        assert added.winner_gap_pct == pytest.approx(0.5, abs=0.01)

    def test_improvement_contains_adjustment(self):
        svc = self._svc_no_existing_da()
        obj = _exec(submitted_rate=0.910, winner_rate=0.900)
        svc._auto_defeat_analysis(obj)
        added = svc.db.add.call_args[0][0]
        assert "낮게 조정" in added.improvement

    def test_no_duplicate_analysis(self):
        db = MagicMock()
        existing_da = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = existing_da
        db.query.return_value = q

        svc = ExecutionService(db)
        obj = _exec(submitted_rate=0.910, winner_rate=0.900)
        svc._auto_defeat_analysis(obj)
        db.add.assert_not_called()


# ── update — status transitions ──────────────────────────────────────────────

class TestUpdate:
    def _svc_with_exec(self, exec_obj):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = exec_obj
        # second filter for DefeatAnalysis
        db.query.return_value = q
        return ExecutionService(db), db

    def test_update_raises_404_when_not_found(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        svc = ExecutionService(db)

        from fastapi import HTTPException
        data = _update_data("참여결정")
        with pytest.raises(HTTPException) as exc:
            svc.update(999, user_id=1, data=data)
        assert exc.value.status_code == 404

    def test_update_sets_status(self):
        obj = _exec(status="검토중")
        svc, db = self._svc_with_exec(obj)

        with patch.object(svc, "_auto_defeat_analysis"):
            data = _update_data("참여결정")
            svc.update(1, user_id=1, data=data)

        assert obj.status == "참여결정"
        db.commit.assert_called()

    def test_패찰_triggers_defeat_analysis(self):
        obj = _exec(status="개찰대기", submitted_rate=0.910, winner_rate=0.900)
        svc, db = self._svc_with_exec(obj)

        da_mock = MagicMock()
        da_mock.cause_primary = "투찰률과도"
        da_mock.improvement = "낮게 조정 권장"

        # after _auto_defeat_analysis, query for da
        call_count = {"n": 0}

        def query_side(model):
            call_count["n"] += 1
            q = MagicMock()
            if call_count["n"] == 1:
                q.filter.return_value.first.return_value = obj
            else:
                q.filter.return_value.first.return_value = da_mock
            return q

        db.query.side_effect = query_side

        with patch.object(svc, "_auto_defeat_analysis") as mock_da:
            from app.services import NotificationService
            with patch.object(NotificationService, "create"):
                data = _update_data("패찰")
                data.status = "패찰"
                svc.update(1, user_id=1, data=data)
            mock_da.assert_called_once_with(obj)

    def test_낙찰_sends_notification(self):
        obj = _exec(status="개찰대기", submitted_rate=0.905)
        svc, db = self._svc_with_exec(obj)

        with patch("app.services.notifications.NotificationService") as MockNS:
            mock_ns_instance = MockNS.return_value
            data = _update_data("낙찰")
            data.status = "낙찰"
            svc.update(1, user_id=1, data=data)
            mock_ns_instance.create.assert_called_once()
            call_kwargs = mock_ns_instance.create.call_args
            assert "낙찰" in call_kwargs[1]["title"] or "낙찰" in str(call_kwargs)


# ── list_executions ──────────────────────────────────────────────────────────

class TestListExecutions:
    def test_returns_total_and_items(self):
        obj = _exec()
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.count.return_value = 1
        q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [obj]
        db.query.return_value = q

        svc = ExecutionService(db)
        from app.schemas import BidExecutionOut
        with patch.object(BidExecutionOut, "model_validate") as mock_validate:
            mock_validate.return_value.model_dump.return_value = {"id": 1}
            result = svc.list_executions(user_id=1)

        assert "total" in result
        assert "items" in result
        assert result["total"] == 1

    def test_status_filter_applied(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 0
        q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        db.query.return_value = q

        svc = ExecutionService(db)
        from app.schemas import BidExecutionOut
        with patch.object(BidExecutionOut, "model_validate"):
            svc.list_executions(user_id=1, status="패찰")

        # filter called more than once (user_id + status)
        assert q.filter.call_count >= 2


# ── STATUS_ORDER constant ────────────────────────────────────────────────────

class TestStatusOrder:
    def test_contains_all_seven_statuses(self):
        expected = {"검토중", "참여결정", "투찰완료", "개찰대기", "낙찰", "패찰", "포기"}
        assert set(ExecutionService.STATUS_ORDER) == expected

    def test_active_statuses_come_before_terminal(self):
        order = ExecutionService.STATUS_ORDER
        terminal = {"낙찰", "패찰", "포기"}
        last_active_idx = max(
            i for i, s in enumerate(order) if s not in terminal
        )
        first_terminal_idx = min(
            i for i, s in enumerate(order) if s in terminal
        )
        assert last_active_idx < first_terminal_idx
