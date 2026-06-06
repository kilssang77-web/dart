"""Unit tests for scheduler.py"""
from unittest.mock import MagicMock, call, patch

import pytest
from apscheduler.schedulers.background import BackgroundScheduler


def test_create_scheduler_returns_background_scheduler():
    from app.collector.scheduler import create_scheduler

    scheduler = create_scheduler()
    assert isinstance(scheduler, BackgroundScheduler)


def test_create_scheduler_registers_five_jobs():
    from app.collector.scheduler import create_scheduler

    scheduler = create_scheduler()
    jobs = scheduler.get_jobs()
    assert len(jobs) == 5


def test_create_scheduler_job_ids():
    from app.collector.scheduler import create_scheduler

    scheduler = create_scheduler()
    job_ids = {j.id for j in scheduler.get_jobs()}
    assert "collect_notices_daily" in job_ids
    assert "collect_results_and_sync_daily" in job_ids
    assert "collect_scsbid_daily" in job_ids
    assert "collect_bid_notices_inpo21c_daily" in job_ids
    assert "collect_inpo21c_weekly" in job_ids


def test_create_scheduler_job_args():
    from app.collector.scheduler import create_scheduler

    scheduler = create_scheduler()
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert jobs["collect_notices_daily"].args == ("notices",)


def test_run_collection_job_all(monkeypatch):
    """collect_type='all' calls run_full_collection"""
    from app.collector import scheduler as sched_mod

    mock_db = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_db)
    mock_run_full = MagicMock()
    mock_settings = MagicMock(g2b_api_key="test-key")
    mock_client_cls = MagicMock()

    monkeypatch.setattr("app.database.SessionLocal", mock_session_cls)

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.collector.client.NarajangterClient", mock_client_cls),
        patch("app.collector.service.run_full_collection", mock_run_full),
    ):
        sched_mod.run_collection_job("all")

    mock_run_full.assert_called_once_with(mock_db)
    mock_db.close.assert_called_once()


def test_run_collection_job_notices(monkeypatch):
    """collect_type='notices' calls collect_notices 3 times"""
    from app.collector import scheduler as sched_mod

    mock_db = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_db)
    mock_collect_notices = MagicMock()
    mock_settings = MagicMock(g2b_api_key="test-key")
    mock_client = MagicMock()
    mock_client_cls = MagicMock(return_value=mock_client)

    monkeypatch.setattr("app.database.SessionLocal", mock_session_cls)

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.collector.client.NarajangterClient", mock_client_cls),
        patch("app.collector.service.collect_notices", mock_collect_notices),
    ):
        sched_mod.run_collection_job("notices")

    assert mock_collect_notices.call_count == 3
    mock_collect_notices.assert_has_calls(
        [
            call(mock_db, mock_client, "notice_cnstwk"),
            call(mock_db, mock_client, "notice_servc"),
            call(mock_db, mock_client, "notice_thng"),
        ]
    )


def test_run_collection_job_results(monkeypatch):
    """collect_type='results' calls collect_results once"""
    from app.collector import scheduler as sched_mod

    mock_db = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_db)
    mock_collect_results = MagicMock()
    mock_settings = MagicMock(g2b_api_key="test-key")
    mock_client = MagicMock()
    mock_client_cls = MagicMock(return_value=mock_client)

    monkeypatch.setattr("app.database.SessionLocal", mock_session_cls)

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.collector.client.NarajangterClient", mock_client_cls),
        patch("app.collector.service.collect_results", mock_collect_results),
    ):
        sched_mod.run_collection_job("results")

    mock_collect_results.assert_called_once_with(mock_db, mock_client)
    mock_db.close.assert_called_once()


def test_run_collection_job_unknown_type(caplog, monkeypatch):
    """Unknown collect_type logs a warning and does not raise"""
    from app.collector import scheduler as sched_mod
    import logging

    mock_db = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_db)
    mock_settings = MagicMock(g2b_api_key="test-key")
    mock_client_cls = MagicMock()

    monkeypatch.setattr("app.database.SessionLocal", mock_session_cls)

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.collector.client.NarajangterClient", mock_client_cls),
        caplog.at_level(logging.WARNING, logger="app.collector.scheduler"),
    ):
        sched_mod.run_collection_job("invalid")

    mock_db.close.assert_called_once()


def test_run_collection_job_closes_db_on_exception(monkeypatch):
    """db.close() is guaranteed even when an exception occurs during collection"""
    from app.collector import scheduler as sched_mod

    mock_db = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_db)
    mock_settings = MagicMock(g2b_api_key="test-key")
    mock_client_cls = MagicMock()

    monkeypatch.setattr("app.database.SessionLocal", mock_session_cls)

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.collector.client.NarajangterClient", mock_client_cls),
        patch(
            "app.collector.service.run_full_collection",
            side_effect=RuntimeError("DB error"),
        ),
    ):
        sched_mod.run_collection_job("all")

    mock_db.close.assert_called_once()
