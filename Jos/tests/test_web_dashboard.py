"""Web dashboard tests.

Tests all Flask routes, auth, rate limiting, pipeline caching, and edge cases.
Mocks scheduler and all heavy agent/LLM modules at the sys.modules level
to prevent APScheduler from starting and to avoid requiring ML dependencies.
"""
from __future__ import annotations

import sys
import os
import json
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mocking: prevent heavy imports from failing.
#
# web_dashboard.py imports agents.*, llm, graph, scheduler, ledger, etc.
# Each of those transitively imports bs4, mlx, mlx_lm, langgraph, etc.
# We mock every module that is either (a) heavy/optional or (b) would
# start background threads (APScheduler).
# ---------------------------------------------------------------------------

# 1. Mock third-party libs that may not be installed in test env
for _mod in (
    "bs4", "snscrape", "snscrape.modules", "snscrape.modules.twitter",
    "mlx", "mlx_lm", "tweepy", "linkedin_api",
    "langgraph", "langgraph.graph",
):
    sys.modules.setdefault(_mod, MagicMock())

# 2. Provide a fake langgraph.graph.END sentinel and StateGraph
_mock_lg = sys.modules["langgraph.graph"]
_mock_lg.END = "END"
_mock_lg.StateGraph = MagicMock()

# 3. Mock llm module (imported by every agent)
_mock_llm = MagicMock()
_mock_llm.generate_with_fallback = MagicMock(return_value="mock llm output")
_mock_llm.build_outreach_prompt = MagicMock(return_value="prompt")
_mock_llm.build_follow_up_prompt = MagicMock(return_value="prompt")
_mock_llm.build_closing_prompt = MagicMock(return_value="prompt")
_mock_llm.build_audit_prompt = MagicMock(return_value="prompt")
_mock_llm.parse_email_output = MagicMock(return_value={"subject": "s", "body": "b"})
_mock_llm.SYSTEM_FOLLOW_UP = "system"
_mock_llm.SYSTEM_CLOSER = "system"
_mock_llm.SYSTEM_AUDITOR = "system"
sys.modules.setdefault("llm", _mock_llm)

# 4. Mock state module (imported by graph)
_mock_state = MagicMock()
_mock_state.SalesState = dict  # just use dict
sys.modules.setdefault("state", _mock_state)

# 5. Mock scheduler module — critical: prevents APScheduler from starting
_mock_sched_instance = MagicMock()
_mock_sched_instance.get_jobs.return_value = []
_mock_sched_instance.start = MagicMock()
_mock_sched_instance.shutdown = MagicMock()
_mock_scheduler_module = MagicMock()
_mock_scheduler_module.scheduler = _mock_sched_instance
_mock_scheduler_module.get_next_runs = MagicMock(return_value=[])
sys.modules["scheduler"] = _mock_scheduler_module

# 6. Mock optional poster / source modules — track which ones we add so we can
#    clean up after import (prevents sys.modules pollution that breaks
#    importlib.reload in test_x_poster.py / test_linkedin_poster.py).
_project_mocks_to_cleanup = []
for _mod in ("x_poster", "linkedin_poster", "lead_sources",
             "engagement_drafter", "feedback_loop", "graph",
             "lead_enricher", "x_scraper"):
    if _mod not in sys.modules:
        _project_mocks_to_cleanup.append(_mod)
    sys.modules.setdefault(_mod, MagicMock())

# ---------------------------------------------------------------------------
# NOW it is safe to import web_dashboard
# ---------------------------------------------------------------------------

import web_dashboard  # noqa: E402
from web_dashboard import app, _pipeline_cache, _rate_buckets, _cache_lock  # noqa: E402

# Cleanup: remove project-module MagicMocks so other test files can import
# the real modules.  web_dashboard already has its bound references.
for _mod in _project_mocks_to_cleanup:
    sys.modules.pop(_mod, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_API_KEY = "test-secret-key-12345"

# Dummy pipeline results returned by the mocked _get_cached_or_run
DUMMY_RESULTS = [
    {
        "name": "Alice Tester",
        "title": "CTO",
        "company": "TestCorp",
        "email": "alice@testcorp.com",
        "x_username": "alice_test",
        "x_post_text": "AI is changing everything",
        "email_confidence": 90,
        "tier": "enterprise",
        "expected_tier": "enterprise",
        "tier_match": True,
        "status": "hot",
        "score": 0.85,
        "channel": "email",
        "route": "closer_manager",
        "dm_preview": "Hi Alice, ...",
        "follow_up_preview": "",
        "closing_script": "Book a demo with Alice",
        "close_action": "book_demo",
        "suggestion": "",
    },
    {
        "name": "Bob Nurture",
        "title": "Engineer",
        "company": "SmallCo",
        "email": "bob@smallco.com",
        "x_username": "",
        "x_post_text": "",
        "email_confidence": 0,
        "tier": "nurture",
        "expected_tier": "nurture",
        "tier_match": True,
        "status": "cold",
        "score": 0.25,
        "channel": "email",
        "route": "follow_up_architect",
        "dm_preview": "Hi Bob, ...",
        "follow_up_preview": "Following up...",
        "closing_script": "",
        "close_action": "",
        "suggestion": "Consider multi-touch approach",
    },
]

DUMMY_KPIS = {
    "total_processed": 2,
    "hot_leads": 1,
    "cold_leads": 1,
    "delivery_rate": 1.0,
    "close_rate": 0.5,
    "responded": 0,
}

DUMMY_TIER_COUNTS = {"enterprise": 1, "nurture": 1}
DUMMY_ROUTE_COUNTS = {"closer_manager": 1, "follow_up_architect": 1}
DUMMY_ACCURACY = {
    "total": 2,
    "correct": 2,
    "pct": 100,
    "mismatches": [],
}
DUMMY_ELAPSED = 1.23


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear rate-limit buckets between tests so state does not leak."""
    _rate_buckets.clear()
    yield
    _rate_buckets.clear()


@pytest.fixture(autouse=True)
def _reset_pipeline_cache():
    """Reset the pipeline cache between tests."""
    with _cache_lock:
        _pipeline_cache["results"] = None
        _pipeline_cache["kpis"] = None
        _pipeline_cache["tier_counts"] = None
        _pipeline_cache["route_counts"] = None
        _pipeline_cache["accuracy"] = None
        _pipeline_cache["elapsed"] = 0
        _pipeline_cache["timestamp"] = 0
        _pipeline_cache["running"] = False
    yield


@pytest.fixture()
def client():
    """Flask test client with TESTING enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def mock_pipeline():
    """Patch _get_cached_or_run to return dummy data (avoids real agent calls)."""
    with patch.object(
        web_dashboard,
        "_get_cached_or_run",
        return_value=(
            DUMMY_RESULTS,
            DUMMY_KPIS,
            DUMMY_TIER_COUNTS,
            DUMMY_ROUTE_COUNTS,
            DUMMY_ACCURACY,
            DUMMY_ELAPSED,
        ),
    ) as m:
        yield m


@pytest.fixture()
def mock_db():
    """Patch all DB helpers used by routes so we never touch real SQLite."""
    with patch.object(web_dashboard, "get_pending_approvals", return_value=[]) as gpa, \
         patch.object(web_dashboard, "get_approval_counts", return_value={"pending": 0, "approved": 0, "rejected": 0}) as gac, \
         patch.object(web_dashboard, "get_pending_engagements", return_value=[]) as gpe, \
         patch.object(web_dashboard, "get_engagement_stats", return_value={}) as ges, \
         patch.object(web_dashboard, "get_connection", return_value=MagicMock()) as gc:
        yield {
            "get_pending_approvals": gpa,
            "get_approval_counts": gac,
            "get_pending_engagements": gpe,
            "get_engagement_stats": ges,
            "get_connection": gc,
        }


@pytest.fixture()
def mock_ledger():
    """Patch ledger.get_log so the dashboard template renders."""
    with patch("web_dashboard.ledger") as m:
        m.get_log.return_value = ["[12:00:00.000] Test log entry"]
        yield m


@pytest.fixture()
def full_dashboard_mocks(mock_pipeline, mock_db, mock_ledger):
    """Convenience: all mocks needed for GET / to render without real work."""
    with patch.object(web_dashboard, "get_next_runs", return_value=[]):
        yield


# ---------------------------------------------------------------------------
# Helper: build a fake DB row (dict-like MagicMock)
# ---------------------------------------------------------------------------

def _fake_row(data: dict):
    """Return a MagicMock that behaves like an sqlite3.Row for dict(row)."""
    mock = MagicMock()
    mock.__iter__ = MagicMock(return_value=iter(data.items()))
    mock.__getitem__ = lambda self, k: data[k]
    mock.keys = MagicMock(return_value=data.keys())
    return mock


def _mock_conn_with_row(data: dict | None):
    """Build a MagicMock connection whose .execute().fetchone() returns data."""
    conn = MagicMock()
    if data is not None:
        conn.execute.return_value.fetchone.return_value = _fake_row(data)
    else:
        conn.execute.return_value.fetchone.return_value = None
    return conn


# ---------------------------------------------------------------------------
# 1. GET / — Dashboard rendering
# ---------------------------------------------------------------------------

class TestDashboardIndex:
    """Tests for the main dashboard page."""

    def test_dashboard_returns_200(self, client, full_dashboard_mocks):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_contains_title(self, client, full_dashboard_mocks):
        resp = client.get("/")
        assert b"Joy V1 Sales Rep" in resp.data

    def test_dashboard_shows_lead_names(self, client, full_dashboard_mocks):
        resp = client.get("/")
        assert b"Alice Tester" in resp.data
        assert b"Bob Nurture" in resp.data

    def test_dashboard_shows_kpis(self, client, full_dashboard_mocks):
        resp = client.get("/")
        assert b"Total Processed" in resp.data
        assert b"Hot Leads" in resp.data

    def test_dashboard_shows_tier_accuracy(self, client, full_dashboard_mocks):
        resp = client.get("/")
        assert b"Tier Accuracy" in resp.data
        assert b"100%" in resp.data

    def test_dashboard_sets_auth_cookie_on_key_param(self, client, full_dashboard_mocks):
        """When ?key=<valid> is passed, a joy_auth cookie should be set."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.get(f"/?key={FAKE_API_KEY}")
            assert resp.status_code == 200
            cookie = client.get_cookie("joy_auth")
            assert cookie is not None
            assert cookie.value == FAKE_API_KEY

    def test_dashboard_no_cookie_without_key(self, client, full_dashboard_mocks):
        """Without ?key param, no auth cookie should be set."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.get("/")
            assert resp.status_code == 200
            cookie = client.get_cookie("joy_auth")
            assert cookie is None

    def test_dashboard_with_pending_items(self, client, mock_pipeline, mock_ledger):
        """Pending approval items should be rendered in the inbox."""
        pending = [{
            "id": 42,
            "lead_name": "Pending Pete",
            "lead_email": "pete@test.com",
            "lead_tier": "enterprise",
            "lead_score": 0.9,
            "channel": "email",
            "outreach_draft": "Hello Pete",
            "follow_up_draft": "",
            "closing_script": "",
            "source": "manual",
        }]
        with patch.object(web_dashboard, "get_pending_approvals", return_value=pending), \
             patch.object(web_dashboard, "get_approval_counts", return_value={"pending": 1, "approved": 0, "rejected": 0}), \
             patch.object(web_dashboard, "get_pending_engagements", return_value=[]), \
             patch.object(web_dashboard, "get_engagement_stats", return_value={}), \
             patch.object(web_dashboard, "get_connection", return_value=MagicMock()), \
             patch.object(web_dashboard, "get_next_runs", return_value=[]):
            resp = client.get("/")
            assert resp.status_code == 200
            assert b"Pending Pete" in resp.data
            assert b"Hello Pete" in resp.data


# ---------------------------------------------------------------------------
# 2. Auth tests — require_auth decorator
# ---------------------------------------------------------------------------

class TestAuth:
    """Test Bearer token, query param, and cookie auth."""

    def test_no_auth_required_when_key_empty(self, client):
        """When DASHBOARD_API_KEY is empty, all endpoints should be open."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "approve_item"):
            resp = client.post("/approve/1")
            assert resp.status_code == 200

    def test_401_without_token(self, client):
        """When key is set, missing auth should return 401."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.post("/approve/1")
            assert resp.status_code == 401
            data = resp.get_json()
            assert data["error"] == "Unauthorized"

    def test_bearer_token_auth(self, client):
        """Bearer token in Authorization header should grant access."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY), \
             patch.object(web_dashboard, "approve_item"):
            resp = client.post(
                "/approve/1",
                headers={"Authorization": f"Bearer {FAKE_API_KEY}"},
            )
            assert resp.status_code == 200

    def test_query_param_auth(self, client):
        """Query param ?key=xxx should grant access."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY), \
             patch.object(web_dashboard, "approve_item"):
            resp = client.post(f"/approve/1?key={FAKE_API_KEY}")
            assert resp.status_code == 200

    def test_cookie_auth(self, client):
        """Cookie joy_auth=xxx should grant access."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY), \
             patch.object(web_dashboard, "approve_item"):
            client.set_cookie("joy_auth", FAKE_API_KEY, domain="localhost")
            resp = client.post("/approve/1")
            assert resp.status_code == 200

    def test_wrong_bearer_token_rejected(self, client):
        """Invalid bearer token should be rejected."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.post(
                "/approve/1",
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert resp.status_code == 401

    def test_wrong_cookie_rejected(self, client):
        """Invalid cookie value should be rejected."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            client.set_cookie("joy_auth", "wrong-value", domain="localhost")
            resp = client.post("/approve/1")
            assert resp.status_code == 401

    def test_auth_on_api_pending(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.get("/api/pending")
            assert resp.status_code == 401

    def test_auth_on_api_schedule(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.get("/api/schedule")
            assert resp.status_code == 401

    def test_auth_on_run_pipeline(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.post("/api/run-pipeline")
            assert resp.status_code == 401

    def test_auth_on_execute(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.post("/execute/1")
            assert resp.status_code == 401

    def test_auth_on_discover(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", FAKE_API_KEY):
            resp = client.post("/api/discover")
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. POST /approve-send/<id> — Approve and send
# ---------------------------------------------------------------------------

class TestApproveSend:
    """Tests for the approve-and-send route."""

    SAMPLE_ROW = {
        "id": 1,
        "lead_name": "Test Lead",
        "lead_email": "test@example.com",
        "lead_tier": "enterprise",
        "lead_score": 0.8,
        "channel": "email",
        "outreach_draft": "Hi Test, great work at TestCo!",
        "follow_up_draft": "",
        "closing_script": "",
        "source": "manual",
        "action_type": "outreach",
    }

    def test_approve_send_success(self, client):
        """Happy path: approve + send returns sent status."""
        conn = _mock_conn_with_row(self.SAMPLE_ROW)

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item") as mock_approve, \
             patch.object(web_dashboard, "send_message", return_value={"status": "sent"}) as mock_send, \
             patch.object(web_dashboard, "upsert_lead", return_value=1), \
             patch.object(web_dashboard, "log_outreach"):
            resp = client.post("/approve-send/1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "sent"
            assert data["channel"] == "email"
            mock_approve.assert_called_once_with(1)
            mock_send.assert_called_once()

    def test_approve_send_not_found(self, client):
        """Nonexistent item should return 404."""
        conn = _mock_conn_with_row(None)

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn):
            resp = client.post("/approve-send/999")
            assert resp.status_code == 404
            data = resp.get_json()
            assert data["error"] == "Item not found"

    def test_approve_send_parses_subject_from_draft(self, client):
        """If draft starts with 'Subject: ...', it should be parsed out."""
        row = {**self.SAMPLE_ROW, "outreach_draft": "Subject: Hello there\nBody text here"}
        conn = _mock_conn_with_row(row)

        captured_message = {}

        def capture_send(lead, message, channel="email"):
            captured_message.update(message)
            return {"status": "sent"}

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "send_message", side_effect=capture_send), \
             patch.object(web_dashboard, "upsert_lead", return_value=1), \
             patch.object(web_dashboard, "log_outreach"):
            resp = client.post("/approve-send/1")
            assert resp.status_code == 200
            assert captured_message["subject"] == "Hello there"
            assert captured_message["body"] == "Body text here"

    def test_approve_send_linkedin_channel(self, client):
        """Channel 'linkedin' should be passed through to send_message."""
        row = {**self.SAMPLE_ROW, "channel": "linkedin"}
        conn = _mock_conn_with_row(row)

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "send_message", return_value={"status": "queued"}) as mock_send, \
             patch.object(web_dashboard, "upsert_lead", return_value=1), \
             patch.object(web_dashboard, "log_outreach"):
            resp = client.post("/approve-send/1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["channel"] == "linkedin"


# ---------------------------------------------------------------------------
# 4. POST /approve/<id> — Approve without send
# ---------------------------------------------------------------------------

class TestApprove:
    """Tests for the approve-only route."""

    def test_approve_success(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "approve_item") as mock_approve:
            resp = client.post("/approve/1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "approved"
            assert data["id"] == 1
            mock_approve.assert_called_once_with(1)

    def test_approve_different_id(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "approve_item") as mock_approve:
            resp = client.post("/approve/42")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["id"] == 42
            mock_approve.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# 5. POST /reject/<id>
# ---------------------------------------------------------------------------

class TestReject:
    """Tests for the reject route."""

    def test_reject_success(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "reject_item") as mock_reject:
            resp = client.post("/reject/1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "rejected"
            mock_reject.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# 6. GET /api/pending
# ---------------------------------------------------------------------------

class TestApiPending:
    """Tests for the pending approvals API."""

    def test_returns_pending_list(self, client):
        pending = [{"id": 1, "lead_name": "Test"}, {"id": 2, "lead_name": "Test2"}]
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_pending_approvals", return_value=pending):
            resp = client.get("/api/pending")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) == 2
            assert data[0]["lead_name"] == "Test"

    def test_returns_empty_list(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_pending_approvals", return_value=[]):
            resp = client.get("/api/pending")
            assert resp.status_code == 200
            assert resp.get_json() == []


# ---------------------------------------------------------------------------
# 7. GET /api/schedule
# ---------------------------------------------------------------------------

class TestApiSchedule:
    """Tests for the schedule API."""

    def test_returns_schedule(self, client):
        schedule = [{"id": "x_8h", "name": "X scan 08:00 PT", "next_run_pt": "Mon 8:00 AM PT"}]
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_next_runs", return_value=schedule):
            resp = client.get("/api/schedule")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data) == 1
            assert data[0]["name"] == "X scan 08:00 PT"

    def test_returns_empty_schedule(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_next_runs", return_value=[]):
            resp = client.get("/api/schedule")
            assert resp.status_code == 200
            assert resp.get_json() == []


# ---------------------------------------------------------------------------
# 8. POST /api/run-pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Tests for the explicit pipeline trigger."""

    def test_run_pipeline_success(self, client):
        async_result = (DUMMY_RESULTS, DUMMY_KPIS, DUMMY_TIER_COUNTS,
                        DUMMY_ROUTE_COUNTS, DUMMY_ACCURACY, DUMMY_ELAPSED)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch("web_dashboard.asyncio.run", return_value=async_result):
            resp = client.post("/api/run-pipeline")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "ok"
            assert data["total"] == 2
            assert data["elapsed"] == DUMMY_ELAPSED

    def test_run_pipeline_updates_cache(self, client):
        async_result = (DUMMY_RESULTS, DUMMY_KPIS, DUMMY_TIER_COUNTS,
                        DUMMY_ROUTE_COUNTS, DUMMY_ACCURACY, DUMMY_ELAPSED)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch("web_dashboard.asyncio.run", return_value=async_result):
            client.post("/api/run-pipeline")
            with _cache_lock:
                assert _pipeline_cache["results"] == DUMMY_RESULTS
                assert _pipeline_cache["running"] is False

    def test_run_pipeline_error(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch("web_dashboard.asyncio.run", side_effect=RuntimeError("boom")):
            resp = client.post("/api/run-pipeline")
            data = resp.get_json()
            assert data["status"] == "error"
            assert "boom" in data["error"]
            with _cache_lock:
                assert _pipeline_cache["running"] is False


# ---------------------------------------------------------------------------
# 9. POST /execute/<id> — Engagement execution
# ---------------------------------------------------------------------------

class TestExecuteEngagement:
    """Tests for the execute engagement route."""

    SAMPLE_ENGAGE = {
        "id": 10,
        "lead_name": "Engage Lead",
        "lead_email": "engage@test.com",
        "lead_tier": "",
        "lead_score": 0.0,
        "channel": "",
        "outreach_draft": "Great post about voice AI!",
        "follow_up_draft": "",
        "closing_script": "",
        "source": "engagement",
        "action_type": "x_reply",
        "target_post_id": "12345",
        "target_post_url": "https://x.com/user/status/12345",
        "target_post_text": "Voice AI is the future",
        "platform": "x",
    }

    def test_execute_x_reply(self, client):
        conn = _mock_conn_with_row(self.SAMPLE_ENGAGE)
        mock_reply = MagicMock(return_value={"reply_id": "r123", "status": "sent"})

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "log_engagement"), \
             patch.dict("sys.modules", {"x_poster": MagicMock(reply_to_tweet=mock_reply)}):
            resp = client.post("/execute/10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "executed"
            assert data["post_id"] == "r123"

    def test_execute_not_found(self, client):
        conn = _mock_conn_with_row(None)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn):
            resp = client.post("/execute/999")
            assert resp.status_code == 404

    def test_execute_unknown_action_type(self, client):
        """Unknown action_type should just mark as approved without dispatch."""
        row = {**self.SAMPLE_ENGAGE, "action_type": "unknown_action"}
        conn = _mock_conn_with_row(row)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"):
            resp = client.post("/execute/10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "approved"

    def test_execute_x_tweet(self, client):
        row = {**self.SAMPLE_ENGAGE, "action_type": "x_tweet"}
        conn = _mock_conn_with_row(row)
        mock_post = MagicMock(return_value={"tweet_id": "t456", "status": "sent"})
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "log_engagement"), \
             patch.dict("sys.modules", {"x_poster": MagicMock(post_tweet=mock_post)}):
            resp = client.post("/execute/10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "executed"
            assert data["post_id"] == "t456"

    def test_execute_error_handling(self, client):
        """If the poster raises, the error should be returned gracefully."""
        row = {**self.SAMPLE_ENGAGE, "action_type": "x_tweet"}
        conn = _mock_conn_with_row(row)
        mock_post = MagicMock(side_effect=RuntimeError("API down"))
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.dict("sys.modules", {"x_poster": MagicMock(post_tweet=mock_post)}):
            resp = client.post("/execute/10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "error"
            assert "API down" in data["error"]


# ---------------------------------------------------------------------------
# 10. POST /api/discover — On-demand lead discovery
# ---------------------------------------------------------------------------

class TestDiscover:
    """Tests for the discover endpoint."""

    def test_discover_success(self, client):
        mock_sources = [{"name": "x_scraper"}]
        mock_leads = [
            {"name": "Disco Lead", "email": "disco@test.com", "x_username": "disco", "source": "x"},
        ]
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "lead_tier": "enterprise",
            "personalized_dm": "Hi Disco",
            "current_lead": mock_leads[0],
            "lead_score": 0.8,
            "channel": "email",
        }

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.dict("sys.modules", {
                 "lead_sources": MagicMock(
                     get_configured_sources=MagicMock(return_value=mock_sources),
                     discover_all=MagicMock(return_value=mock_leads),
                 ),
                 "graph": MagicMock(sales_graph=mock_graph),
             }), \
             patch.object(web_dashboard, "queue_for_approval") as mock_queue:
            resp = client.post("/api/discover")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "ok"
            assert data["count"] == 1
            assert data["sources"] == 1

    def test_discover_no_sources(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.dict("sys.modules", {
                 "lead_sources": MagicMock(
                     get_configured_sources=MagicMock(return_value=[]),
                     discover_all=MagicMock(return_value=[]),
                 ),
             }):
            resp = client.post("/api/discover")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["count"] == 0

    def test_discover_handles_exception(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.dict("sys.modules", {
                 "lead_sources": MagicMock(
                     get_configured_sources=MagicMock(side_effect=ImportError("no module")),
                 ),
             }):
            resp = client.post("/api/discover")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "error"


# ---------------------------------------------------------------------------
# 11. Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Tests for the in-memory rate limiter."""

    def test_rate_limit_triggers_after_10_requests(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "approve_item"):
            for i in range(10):
                resp = client.post("/approve/1")
                assert resp.status_code == 200, f"Request {i+1} should succeed"
            # 11th request should be rate limited
            resp = client.post("/approve/1")
            assert resp.status_code == 429

    def test_rate_limit_per_endpoint(self, client):
        """Rate limit buckets are per-endpoint, not global."""
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "reject_item"):
            for _ in range(10):
                client.post("/approve/1")
            # Reject should still work (different bucket)
            resp = client.post("/reject/1")
            assert resp.status_code == 200

    def test_rate_limit_on_approve_send(self, client):
        conn = _mock_conn_with_row(None)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn):
            for _ in range(10):
                client.post("/approve-send/1")
            resp = client.post("/approve-send/1")
            assert resp.status_code == 429

    def test_rate_limit_on_api_pending(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_pending_approvals", return_value=[]):
            for _ in range(10):
                client.get("/api/pending")
            resp = client.get("/api/pending")
            assert resp.status_code == 429

    def test_rate_limit_on_run_pipeline(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch("web_dashboard.asyncio.run", return_value=(
                 DUMMY_RESULTS, DUMMY_KPIS, DUMMY_TIER_COUNTS,
                 DUMMY_ROUTE_COUNTS, DUMMY_ACCURACY, DUMMY_ELAPSED,
             )):
            for _ in range(10):
                client.post("/api/run-pipeline")
            resp = client.post("/api/run-pipeline")
            assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 12. Pipeline caching
# ---------------------------------------------------------------------------

class TestPipelineCaching:
    """Tests for _get_cached_or_run and the pipeline cache."""

    def test_cache_returns_stored_results(self):
        """When cache is fresh, _get_cached_or_run should NOT call asyncio.run."""
        with _cache_lock:
            _pipeline_cache["results"] = DUMMY_RESULTS
            _pipeline_cache["kpis"] = DUMMY_KPIS
            _pipeline_cache["tier_counts"] = DUMMY_TIER_COUNTS
            _pipeline_cache["route_counts"] = DUMMY_ROUTE_COUNTS
            _pipeline_cache["accuracy"] = DUMMY_ACCURACY
            _pipeline_cache["elapsed"] = DUMMY_ELAPSED
            _pipeline_cache["timestamp"] = time.monotonic()
            _pipeline_cache["running"] = False

        with patch("web_dashboard.asyncio.run") as mock_run:
            result = web_dashboard._get_cached_or_run()
            mock_run.assert_not_called()
            assert result[0] == DUMMY_RESULTS

    def test_cache_miss_runs_pipeline(self):
        """When cache is empty, _get_cached_or_run should call asyncio.run."""
        async_result = (DUMMY_RESULTS, DUMMY_KPIS, DUMMY_TIER_COUNTS,
                        DUMMY_ROUTE_COUNTS, DUMMY_ACCURACY, DUMMY_ELAPSED)
        with patch("web_dashboard.asyncio.run", return_value=async_result) as mock_run:
            result = web_dashboard._get_cached_or_run()
            mock_run.assert_called_once()
            assert result[0] == DUMMY_RESULTS

    def test_stale_cache_triggers_rerun(self):
        """Cache older than CACHE_TTL should trigger a fresh pipeline run."""
        with _cache_lock:
            _pipeline_cache["results"] = DUMMY_RESULTS
            _pipeline_cache["kpis"] = DUMMY_KPIS
            _pipeline_cache["tier_counts"] = DUMMY_TIER_COUNTS
            _pipeline_cache["route_counts"] = DUMMY_ROUTE_COUNTS
            _pipeline_cache["accuracy"] = DUMMY_ACCURACY
            _pipeline_cache["elapsed"] = DUMMY_ELAPSED
            _pipeline_cache["timestamp"] = time.monotonic() - 600  # 10 min ago
            _pipeline_cache["running"] = False

        async_result = (DUMMY_RESULTS, DUMMY_KPIS, DUMMY_TIER_COUNTS,
                        DUMMY_ROUTE_COUNTS, DUMMY_ACCURACY, DUMMY_ELAPSED)
        with patch("web_dashboard.asyncio.run", return_value=async_result) as mock_run:
            web_dashboard._get_cached_or_run()
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# 13. _is_rate_limited function directly
# ---------------------------------------------------------------------------

class TestIsRateLimited:
    """Direct unit tests for the rate limiter function."""

    def test_first_request_not_limited(self):
        assert web_dashboard._is_rate_limited("test-key") is False

    def test_under_limit_not_limited(self):
        for _ in range(9):
            web_dashboard._is_rate_limited("under-limit")
        assert web_dashboard._is_rate_limited("under-limit") is False

    def test_at_limit_is_limited(self):
        for _ in range(10):
            web_dashboard._is_rate_limited("at-limit")
        assert web_dashboard._is_rate_limited("at-limit") is True

    def test_different_keys_independent(self):
        for _ in range(10):
            web_dashboard._is_rate_limited("key-a")
        assert web_dashboard._is_rate_limited("key-b") is False


# ---------------------------------------------------------------------------
# 14. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Miscellaneous edge-case tests."""

    def test_approve_send_empty_channel_defaults_email(self, client):
        """If channel is empty or None, it should default to 'email'."""
        row = {
            "id": 5, "lead_name": "No Channel", "lead_email": "nc@test.com",
            "lead_tier": "self_serve", "lead_score": 0.5, "channel": "",
            "outreach_draft": "Hello", "follow_up_draft": "", "closing_script": "",
            "source": "manual", "action_type": "outreach",
        }
        conn = _mock_conn_with_row(row)

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "send_message", return_value={"status": "sent"}), \
             patch.object(web_dashboard, "upsert_lead", return_value=1), \
             patch.object(web_dashboard, "log_outreach"):
            resp = client.post("/approve-send/5")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["channel"] == "email"

    def test_approve_send_logs_outreach_failure_gracefully(self, client):
        """If upsert_lead raises, the response should still succeed."""
        row = {
            "id": 6, "lead_name": "Log Fail", "lead_email": "logfail@test.com",
            "lead_tier": "enterprise", "lead_score": 0.9, "channel": "email",
            "outreach_draft": "Hello", "follow_up_draft": "", "closing_script": "",
            "source": "manual", "action_type": "outreach",
        }
        conn = _mock_conn_with_row(row)

        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "send_message", return_value={"status": "sent"}), \
             patch.object(web_dashboard, "upsert_lead", side_effect=Exception("DB error")):
            resp = client.post("/approve-send/6")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "sent"

    def test_reject_returns_correct_json_shape(self, client):
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "reject_item"):
            resp = client.post("/reject/77")
            data = resp.get_json()
            assert "status" in data
            assert "id" in data
            assert data["id"] == 77

    def test_404_for_invalid_route(self, client):
        resp = client.get("/nonexistent-route")
        assert resp.status_code == 404

    def test_approve_send_returns_id_in_response(self, client):
        """The response JSON should include the item ID."""
        row = {
            "id": 99, "lead_name": "ID Check", "lead_email": "id@test.com",
            "lead_tier": "enterprise", "lead_score": 0.7, "channel": "email",
            "outreach_draft": "Hi", "follow_up_draft": "", "closing_script": "",
            "source": "manual", "action_type": "outreach",
        }
        conn = _mock_conn_with_row(row)
        with patch.object(web_dashboard, "DASHBOARD_API_KEY", ""), \
             patch.object(web_dashboard, "get_connection", return_value=conn), \
             patch.object(web_dashboard, "approve_item"), \
             patch.object(web_dashboard, "send_message", return_value={"status": "sent"}), \
             patch.object(web_dashboard, "upsert_lead", return_value=1), \
             patch.object(web_dashboard, "log_outreach"):
            resp = client.post("/approve-send/99")
            data = resp.get_json()
            assert data["id"] == 99
