"""Tests for scheduler.py - APScheduler cron jobs for Joy V1 Sales Rep."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
import pytz

import ledger
from scheduler import (
    create_scheduler,
    get_next_runs,
    run_scheduled_scan,
    run_engagement_scan,
    collect_engagement_metrics,
    PACIFIC,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


def _make_mock_job(job_id: str, name: str, next_run: datetime):
    """Create a mock APScheduler job with the given next_run_time."""
    job = MagicMock()
    job.id = job_id
    job.name = name
    job.next_run_time = next_run
    return job


# ---------------------------------------------------------------------------
# create_scheduler
# ---------------------------------------------------------------------------

def test_create_scheduler_has_jobs():
    """Scheduler is created with all expected cron jobs."""
    sched = create_scheduler()
    jobs = sched.get_jobs()
    job_ids = [j.id for j in jobs]

    # LinkedIn scans: 9, 12, 17
    assert "linkedin_9h" in job_ids
    assert "linkedin_12h" in job_ids
    assert "linkedin_17h" in job_ids

    # X scans: 8, 19
    assert "x_8h" in job_ids
    assert "x_19h" in job_ids

    # Engagement scans: 10, 14, 18
    assert "engage_10h" in job_ids
    assert "engage_14h" in job_ids
    assert "engage_18h" in job_ids

    # Daily metrics
    assert "daily_metrics" in job_ids

    # Total: 3 LinkedIn + 2 X + 3 engagement + 1 metrics = 9
    assert len(jobs) == 9


def test_create_scheduler_job_names():
    """Jobs have descriptive names."""
    sched = create_scheduler()
    jobs = {j.id: j.name for j in sched.get_jobs()}
    assert "LinkedIn" in jobs["linkedin_9h"]
    assert "PT" in jobs["linkedin_9h"]
    assert "X scan" in jobs["x_8h"]
    assert "Engagement" in jobs["engage_10h"]
    assert "metrics" in jobs["daily_metrics"].lower()


# ---------------------------------------------------------------------------
# get_next_runs
# ---------------------------------------------------------------------------

def test_get_next_runs_returns_sorted():
    """get_next_runs returns jobs sorted by next_run_iso."""
    now_pt = datetime.now(PACIFIC)
    job_a = _make_mock_job("a", "Job A", now_pt + timedelta(hours=3))
    job_b = _make_mock_job("b", "Job B", now_pt + timedelta(hours=1))
    job_c = _make_mock_job("c", "Job C", now_pt + timedelta(hours=2))

    mock_sched = MagicMock()
    mock_sched.get_jobs.return_value = [job_a, job_b, job_c]

    runs = get_next_runs(mock_sched, n=5)
    assert len(runs) == 3
    # Should be sorted: B (1h), C (2h), A (3h)
    assert runs[0]["id"] == "b"
    assert runs[1]["id"] == "c"
    assert runs[2]["id"] == "a"
    # Each entry has expected keys
    for run in runs:
        assert "id" in run
        assert "name" in run
        assert "next_run_pt" in run
        assert "next_run_iso" in run


def test_get_next_runs_empty_scheduler():
    """Empty scheduler returns empty list."""
    mock_sched = MagicMock()
    mock_sched.get_jobs.return_value = []
    runs = get_next_runs(mock_sched, n=5)
    assert runs == []


def test_get_next_runs_respects_n_limit():
    """get_next_runs only returns up to n items."""
    now_pt = datetime.now(PACIFIC)
    jobs = [_make_mock_job(f"j{i}", f"Job {i}", now_pt + timedelta(hours=i)) for i in range(1, 8)]
    mock_sched = MagicMock()
    mock_sched.get_jobs.return_value = jobs

    runs = get_next_runs(mock_sched, n=3)
    assert len(runs) == 3
    assert runs[0]["id"] == "j1"
    assert runs[2]["id"] == "j3"


def test_get_next_runs_skips_none_next_run():
    """Jobs with next_run_time=None are skipped."""
    now_pt = datetime.now(PACIFIC)
    job_ok = _make_mock_job("ok", "Good Job", now_pt + timedelta(hours=1))
    job_none = _make_mock_job("none", "Paused Job", None)

    mock_sched = MagicMock()
    mock_sched.get_jobs.return_value = [job_ok, job_none]

    runs = get_next_runs(mock_sched, n=5)
    assert len(runs) == 1
    assert runs[0]["id"] == "ok"


# ---------------------------------------------------------------------------
# run_scheduled_scan
# ---------------------------------------------------------------------------

def test_run_scheduled_scan_success():
    """run_scheduled_scan calls run_pipeline_async via asyncio.run."""
    mock_pipeline = MagicMock()
    mock_web_dashboard = MagicMock()
    mock_web_dashboard.run_pipeline_async = mock_pipeline

    with patch.dict("sys.modules", {"web_dashboard": mock_web_dashboard}):
        with patch("asyncio.run") as mock_asyncio_run:
            run_scheduled_scan()
            mock_asyncio_run.assert_called_once_with(mock_pipeline())


def test_run_scheduled_scan_error_handling(caplog):
    """run_scheduled_scan logs errors instead of raising."""
    mock_web_dashboard = MagicMock()
    mock_web_dashboard.run_pipeline_async.side_effect = RuntimeError("Pipeline crashed")

    with patch.dict("sys.modules", {"web_dashboard": mock_web_dashboard}):
        with patch("asyncio.run", side_effect=RuntimeError("Pipeline crashed")):
            with caplog.at_level(logging.ERROR):
                # Should not raise
                run_scheduled_scan()
    assert "Scan failed" in caplog.text


# ---------------------------------------------------------------------------
# run_engagement_scan
# ---------------------------------------------------------------------------

def test_run_engagement_scan_success():
    """Engagement scan finds posts, drafts replies, and queues them."""
    mock_x_poster = MagicMock()
    mock_x_poster.search_icp_posts.return_value = [
        {"id": "t1", "text": "Voice AI is amazing", "author_name": "Alice", "author_username": "alice"},
        {"id": "t2", "text": "Building speech tools", "author_name": "Bob", "author_username": "bob"},
    ]
    mock_drafter = MagicMock()
    mock_drafter.draft_x_reply.return_value = {
        "action_type": "x_reply",
        "target_post_id": "t1",
        "body": "Great point!",
    }
    mock_db = MagicMock()
    mock_db.queue_engagement.return_value = 1

    modules = {
        "x_poster": mock_x_poster,
        "engagement_drafter": mock_drafter,
        "db": mock_db,
        "config": MagicMock(ICP_KEYWORDS=["voice AI", "speech"]),
    }
    with patch.dict("sys.modules", modules):
        run_engagement_scan()

    mock_x_poster.search_icp_posts.assert_called_once()
    assert mock_drafter.draft_x_reply.call_count == 2
    assert mock_db.queue_engagement.call_count == 2


def test_run_engagement_scan_no_posts():
    """No posts found -> no drafts or queuing happens."""
    mock_x_poster = MagicMock()
    mock_x_poster.search_icp_posts.return_value = []
    mock_drafter = MagicMock()
    mock_db = MagicMock()

    modules = {
        "x_poster": mock_x_poster,
        "engagement_drafter": mock_drafter,
        "db": mock_db,
        "config": MagicMock(ICP_KEYWORDS=["voice AI"]),
    }
    with patch.dict("sys.modules", modules):
        run_engagement_scan()

    mock_drafter.draft_x_reply.assert_not_called()
    mock_db.queue_engagement.assert_not_called()


def test_run_engagement_scan_error_handling(caplog):
    """Engagement scan logs errors instead of raising."""
    # Force an import error by patching sys.modules to raise
    with patch.dict("sys.modules", {"x_poster": None}):
        with caplog.at_level(logging.ERROR):
            run_engagement_scan()
    assert "Engagement scan failed" in caplog.text


# ---------------------------------------------------------------------------
# collect_engagement_metrics
# ---------------------------------------------------------------------------

def test_collect_metrics_success(caplog):
    """Metrics collection calls feedback_loop functions and logs results."""
    mock_feedback = MagicMock()
    mock_feedback.calculate_source_scores.return_value = {"apollo": 0.35, "github": 0.12}
    mock_feedback.calculate_engagement_scores.return_value = {"x_reply": 0.8}
    mock_feedback.get_recommended_actions.return_value = ["Increase Apollo outreach"]

    with patch.dict("sys.modules", {"feedback_loop": mock_feedback}):
        with caplog.at_level(logging.INFO):
            collect_engagement_metrics()

    mock_feedback.calculate_source_scores.assert_called_once()
    mock_feedback.calculate_engagement_scores.assert_called_once()
    mock_feedback.get_recommended_actions.assert_called_once()
    assert "Metrics" in caplog.text


def test_collect_metrics_error_handling(caplog):
    """Metrics collection logs errors instead of raising."""
    mock_feedback = MagicMock()
    mock_feedback.calculate_source_scores.side_effect = Exception("DB connection failed")

    with patch.dict("sys.modules", {"feedback_loop": mock_feedback}):
        with caplog.at_level(logging.ERROR):
            collect_engagement_metrics()

    assert "Metrics collection failed" in caplog.text


def test_collect_metrics_empty_results(caplog):
    """Metrics collection handles empty results gracefully."""
    mock_feedback = MagicMock()
    mock_feedback.calculate_source_scores.return_value = {}
    mock_feedback.calculate_engagement_scores.return_value = {}
    mock_feedback.get_recommended_actions.return_value = []

    with patch.dict("sys.modules", {"feedback_loop": mock_feedback}):
        with caplog.at_level(logging.INFO):
            collect_engagement_metrics()

    # Should complete without error
    mock_feedback.calculate_source_scores.assert_called_once()
