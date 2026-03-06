"""Tests for graph.py - LangGraph sales pipeline orchestrator."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from langgraph.graph import END

import ledger
from state import SalesState
from graph import (
    outreach_hunter_node,
    auditor_node,
    follow_up_architect_node,
    closer_manager_node,
    route_after_hunter,
    build_sales_graph,
    sales_graph,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


def _base_lead():
    return {
        "name": "Sarah Chen",
        "title": "CTO",
        "company": "Acme AI",
        "email": "sarah@acme.ai",
        "linkedin_url": "https://linkedin.com/in/sarahchen",
    }


# ---------------------------------------------------------------------------
# outreach_hunter_node
# ---------------------------------------------------------------------------

@patch("graph.send_message")
@patch("graph.hunt")
def test_outreach_hunter_node_success(mock_hunt, mock_send):
    """hunt() returns a fully qualified result; node populates state."""
    lead = _base_lead()
    mock_hunt.return_value = {
        "lead": {**lead, "x_post_text": "AI is the future", "verified_email": "sarah@acme.ai", "email_confidence": 95},
        "score": 0.85,
        "tier": "enterprise",
        "status": "hot",
        "outreach": {"message": {"subject": "Hello", "body": "Hi Sarah"}},
        "personalized_dm": "Hi Sarah, loved your take on AI.",
        "channel": "email",
    }
    mock_send.return_value = {"status": "sent", "channel": "email"}

    state: SalesState = {"current_lead": lead}
    result = outreach_hunter_node(state)

    assert result["lead_score"] == 0.85
    assert result["lead_tier"] == "enterprise"
    assert result["lead_status"] == "hot"
    assert result["personalized_dm"] == "Hi Sarah, loved your take on AI."
    assert result["x_post_text"] == "AI is the future"
    assert result["verified_email"] == "sarah@acme.ai"
    assert result["email_confidence"] == 95
    assert result["send_result"]["status"] == "sent"
    assert "error" not in result or result.get("error") is None
    mock_hunt.assert_called_once_with(lead)


@patch("graph.scan_leads")
@patch("graph.hunt")
def test_outreach_hunter_node_no_lead(mock_hunt, mock_scan):
    """Empty current_lead and scan returns nothing -> error in state."""
    mock_scan.return_value = []
    state: SalesState = {"current_lead": {}}
    result = outreach_hunter_node(state)
    assert result["error"] == "No leads found"
    mock_hunt.assert_not_called()


@patch("graph.hunt")
def test_outreach_hunter_node_error_handling(mock_hunt):
    """hunt() raises -> node catches and sets error."""
    mock_hunt.side_effect = RuntimeError("API timeout")
    state: SalesState = {"current_lead": _base_lead()}
    result = outreach_hunter_node(state)
    assert "error" in result
    assert "Outreach hunter failed" in result["error"]
    assert "API timeout" in result["error"]


# ---------------------------------------------------------------------------
# auditor_node
# ---------------------------------------------------------------------------

@patch("graph.audit_pipeline")
def test_auditor_node_appends_kpi_log(mock_audit):
    """Auditor appends KPI entries and updates lead_status."""
    mock_audit.return_value = {
        "kpi_entries": ["LEAD: Sarah Chen | tier=enterprise score=0.85 status=hot"],
        "suggestions": "Prioritize demo booking",
        "lead_status": "hot",
    }
    state: SalesState = {
        "current_lead": _base_lead(),
        "kpi_log": ["existing entry"],
        "lead_status": "cold",
    }
    result = auditor_node(state)
    assert len(result["kpi_log"]) == 2
    assert result["kpi_log"][0] == "existing entry"
    assert "Sarah Chen" in result["kpi_log"][1]
    assert result["lead_status"] == "hot"


@patch("graph.audit_pipeline")
def test_auditor_node_error_handling(mock_audit):
    """audit_pipeline() raises -> node catches and sets error."""
    mock_audit.side_effect = ValueError("KPI computation failed")
    state: SalesState = {"current_lead": _base_lead()}
    result = auditor_node(state)
    assert "error" in result
    assert "Audit failed" in result["error"]
    assert "KPI computation failed" in result["error"]


# ---------------------------------------------------------------------------
# follow_up_architect_node
# ---------------------------------------------------------------------------

@patch("graph.generate_follow_up_message")
@patch("graph.schedule_follow_up")
def test_follow_up_architect_node_queues_follow_up(mock_schedule, mock_gen):
    """Node schedules a follow-up and queues it."""
    lead = _base_lead()
    mock_schedule.return_value = {
        "lead": lead,
        "tier": "self_serve",
        "step": 1,
        "due_date": "2026-03-05",
    }
    mock_gen.return_value = {
        "subject": "Following up",
        "body": "Hi Sarah, just checking in.",
    }
    state: SalesState = {
        "current_lead": lead,
        "lead_tier": "self_serve",
        "follow_up_step": 1,
        "follow_up_queue": [],
    }
    result = follow_up_architect_node(state)
    assert result["outreach_message"] == {"subject": "Following up", "body": "Hi Sarah, just checking in."}
    assert result["follow_up_text"] == "Hi Sarah, just checking in."
    assert len(result["follow_up_queue"]) == 1
    assert result["follow_up_queue"][0]["tier"] == "self_serve"


@patch("graph.generate_follow_up_message")
@patch("graph.schedule_follow_up")
def test_follow_up_architect_node_error_handling(mock_schedule, mock_gen):
    """schedule_follow_up raises -> node catches and sets error."""
    mock_schedule.side_effect = Exception("DB error")
    state: SalesState = {"current_lead": _base_lead(), "lead_tier": "nurture"}
    result = follow_up_architect_node(state)
    assert "error" in result
    assert "Follow-up failed" in result["error"]


# ---------------------------------------------------------------------------
# closer_manager_node
# ---------------------------------------------------------------------------

@patch("graph.close_deal")
def test_closer_manager_node_closes_deal(mock_close):
    """Node calls close_deal and populates closing fields."""
    mock_close.return_value = {
        "action": "book_demo",
        "status": "link_generated",
        "url": "https://calendly.com/voco-demo?name=Sarah+Chen",
        "closing_script": "Hi Sarah, here is your demo link.",
    }
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "enterprise",
    }
    result = closer_manager_node(state)
    assert result["close_action"] == "book_demo"
    assert result["close_result"]["status"] == "link_generated"
    assert result["closing_script"] == "Hi Sarah, here is your demo link."


@patch("graph.close_deal")
def test_closer_manager_node_error_handling(mock_close):
    """close_deal raises -> node catches and sets error."""
    mock_close.side_effect = RuntimeError("Stripe API down")
    state: SalesState = {"current_lead": _base_lead(), "lead_tier": "self_serve"}
    result = closer_manager_node(state)
    assert "error" in result
    assert "Close failed" in result["error"]


# ---------------------------------------------------------------------------
# route_after_hunter (conditional edges)
# ---------------------------------------------------------------------------

@patch("graph.is_hot_lead", return_value=True)
def test_route_hot_to_closer(mock_hot):
    """Hot lead routes to closer_manager."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "enterprise",
        "lead_status": "hot",
        "lead_score": 0.9,
    }
    assert route_after_hunter(state) == "closer_manager"


@patch("graph.is_hot_lead", return_value=False)
def test_route_cold_enterprise_to_follow_up(mock_hot):
    """Cold enterprise lead routes to follow_up_architect."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "enterprise",
        "lead_status": "cold",
        "lead_score": 0.7,
    }
    assert route_after_hunter(state) == "follow_up_architect"


@patch("graph.is_hot_lead", return_value=False)
def test_route_cold_self_serve_to_follow_up(mock_hot):
    """Cold self_serve lead routes to follow_up_architect."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "self_serve",
        "lead_status": "cold",
        "lead_score": 0.5,
    }
    assert route_after_hunter(state) == "follow_up_architect"


@patch("graph.is_hot_lead", return_value=False)
def test_route_nurture_to_follow_up(mock_hot):
    """Nurture-tier lead routes to follow_up_architect."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "nurture",
        "lead_status": "cold",
        "lead_score": 0.25,
    }
    assert route_after_hunter(state) == "follow_up_architect"


@patch("graph.is_hot_lead", return_value=False)
def test_route_disqualified_to_end(mock_hot):
    """Disqualified lead routes to END."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "disqualified",
        "lead_status": "cold",
        "lead_score": 0.05,
    }
    assert route_after_hunter(state) == END


def test_route_error_to_end():
    """State with error routes to END immediately."""
    state: SalesState = {
        "current_lead": _base_lead(),
        "lead_tier": "enterprise",
        "lead_status": "hot",
        "lead_score": 0.9,
        "error": "Something went wrong",
    }
    assert route_after_hunter(state) == END


# ---------------------------------------------------------------------------
# build_sales_graph
# ---------------------------------------------------------------------------

def test_build_sales_graph_compiles():
    """build_sales_graph returns a compiled LangGraph that can be invoked."""
    compiled = build_sales_graph()
    # Should have an invoke method (compiled CompiledStateGraph)
    assert hasattr(compiled, "invoke")
    # The singleton should also be a compiled graph
    assert hasattr(sales_graph, "invoke")


# ---------------------------------------------------------------------------
# Full graph invoke (all externals mocked)
# ---------------------------------------------------------------------------

@patch("graph.close_deal")
@patch("graph.is_hot_lead")
@patch("graph.audit_pipeline")
@patch("graph.send_message")
@patch("graph.hunt")
def test_full_graph_invoke_with_mocked_externals(
    mock_hunt, mock_send, mock_audit, mock_is_hot, mock_close
):
    """Invoke the full sales_graph with a hot lead - should flow through closer."""
    lead = _base_lead()
    mock_hunt.return_value = {
        "lead": lead,
        "score": 0.9,
        "tier": "enterprise",
        "status": "hot",
        "outreach": {"message": {"subject": "Demo?", "body": "Hi Sarah"}},
        "personalized_dm": "Hi Sarah",
        "channel": "email",
    }
    mock_send.return_value = {"status": "sent", "channel": "email"}
    mock_audit.return_value = {
        "kpi_entries": ["LEAD: Sarah Chen | hot"],
        "suggestions": "",
        "lead_status": "hot",
    }
    mock_is_hot.return_value = True
    mock_close.return_value = {
        "action": "book_demo",
        "status": "link_generated",
        "url": "https://calendly.com/voco-demo",
        "closing_script": "Book your demo!",
    }

    initial_state: SalesState = {"current_lead": lead}
    result = sales_graph.invoke(initial_state)

    # Verify full pipeline ran
    assert result["lead_tier"] == "enterprise"
    assert result["lead_status"] == "hot"
    assert result["close_action"] == "book_demo"
    assert result["closing_script"] == "Book your demo!"
    assert len(result.get("kpi_log", [])) >= 1
    mock_hunt.assert_called_once()
    mock_audit.assert_called_once()
    mock_close.assert_called_once()


@patch("graph.generate_follow_up_message")
@patch("graph.schedule_follow_up")
@patch("graph.is_hot_lead")
@patch("graph.audit_pipeline")
@patch("graph.send_message")
@patch("graph.hunt")
def test_full_graph_invoke_cold_lead_flows_to_follow_up(
    mock_hunt, mock_send, mock_audit, mock_is_hot, mock_schedule, mock_gen
):
    """Cold lead should flow through follow_up_architect, not closer."""
    lead = _base_lead()
    mock_hunt.return_value = {
        "lead": lead,
        "score": 0.5,
        "tier": "self_serve",
        "status": "cold",
        "outreach": {"message": {"subject": "Hey", "body": "Hi"}},
        "personalized_dm": "Hi",
        "channel": "email",
    }
    mock_send.return_value = {"status": "sent", "channel": "email"}
    mock_audit.return_value = {
        "kpi_entries": ["LEAD: Sarah Chen | cold"],
        "suggestions": "",
        "lead_status": "cold",
    }
    mock_is_hot.return_value = False
    mock_schedule.return_value = {
        "lead": lead, "tier": "self_serve", "step": 1, "due_date": "2026-03-05",
    }
    mock_gen.return_value = {"subject": "Follow up", "body": "Checking in."}

    initial_state: SalesState = {"current_lead": lead}
    result = sales_graph.invoke(initial_state)

    assert result["lead_status"] == "cold"
    assert result.get("follow_up_text") == "Checking in."
    assert len(result.get("follow_up_queue", [])) >= 1
    mock_schedule.assert_called_once()
    mock_gen.assert_called_once()
