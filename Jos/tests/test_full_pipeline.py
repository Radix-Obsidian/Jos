"""Full pipeline integration tests - V2 Architecture."""

import pytest
from unittest.mock import patch, MagicMock
from langgraph.graph import END  # noqa: F401

from agents.outreach_hunter import qualify_lead, generate_outreach, hunt
from agents.follow_up_architect import send_message, generate_follow_up_message
from agents.closer_manager import close_deal, is_hot_lead
from agents.auditor import audit_pipeline, calculate_batch_kpis
from graph import route_after_hunter
import ledger


# --- 5 Test Leads ---

LEADS = [
    {"name": "Sarah Chen", "title": "CTO", "company": "DataFlow AI", "email": "sarah@dataflow.ai", "linkedin_url": "https://linkedin.com/in/sarahchen"},
    {"name": "James Wu", "title": "VP Engineering", "company": "CloudSaaS", "email": "james@cloudsaas.com", "linkedin_url": "https://linkedin.com/in/jameswu"},
    {"name": "Emily Park", "title": "Founder", "company": "AI Startup", "email": "emily@aistartup.com", "linkedin_url": ""},
    {"name": "David Kim", "title": "Engineering Manager", "company": "TechCorp", "email": "david@techcorp.com", "linkedin_url": ""},
    {"name": "Mike Intern", "title": "Marketing Intern", "company": "RandomCo", "email": "mike@random.com", "linkedin_url": ""},
]


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


# --- End-to-end flow tests ---

def test_enterprise_lead_full_flow():
    """Enterprise lead flows: hunt -> audit -> close (book demo)."""
    lead = LEADS[0]  # Sarah Chen, CTO

    # Hunt (qualify + outreach)
    result = hunt(lead)
    assert result["tier"] == "enterprise"
    assert result["personalized_dm"] != ""

    # Audit
    state = {
        "current_lead": lead,
        "lead_tier": result["tier"],
        "lead_status": result["status"],
        "lead_score": result["score"],
        "send_result": {"status": "sent", "channel": "email"},
    }
    audit = audit_pipeline(state)
    assert len(audit["kpi_entries"]) > 0

    # Close (no mock needed - book_demo now generates link, no API call)
    close = close_deal(lead, tier="enterprise")
    assert close["action"] == "book_demo"
    assert close["status"] == "link_generated"
    assert close["closing_script"] != ""
    assert "calendly" in close["url"].lower()


def test_self_serve_lead_full_flow():
    """Self-serve lead flows: hunt -> audit -> follow-up (cold)."""
    lead = LEADS[3]  # David Kim, Engineering Manager at TechCorp

    result = hunt(lead)
    assert result["tier"] in ("self_serve", "enterprise")

    # Cold lead gets follow-up
    msg = generate_follow_up_message(lead, step=1, tier="self_serve")
    assert "David" in msg["body"]


def test_nurture_lead_gets_follow_up():
    """Low-scoring lead gets follow-up sequence instead of close."""
    lead = LEADS[4]  # Mike Intern

    result = hunt(lead)
    assert result["tier"] in ("nurture", "disqualified")

    if result["tier"] == "nurture":
        msg = generate_follow_up_message(lead, step=1, tier="nurture")
        assert "Mike" in msg["body"]


# --- Conditional Edge Tests ---

def test_route_hot_to_closer():
    """Hot lead routes to closer_manager."""
    state = {"lead_tier": "enterprise", "lead_status": "hot", "lead_score": 0.9, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == "closer_manager"


def test_route_responded_to_closer():
    """Responded lead routes to closer_manager."""
    state = {"lead_tier": "self_serve", "lead_status": "responded", "lead_score": 0.5, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == "closer_manager"


def test_route_cold_qualified_to_follow_up():
    """Cold qualified lead routes to follow_up_architect."""
    state = {"lead_tier": "enterprise", "lead_status": "cold", "lead_score": 0.7, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == "follow_up_architect"


def test_route_cold_self_serve_to_follow_up():
    """Cold self-serve lead routes to follow_up_architect."""
    state = {"lead_tier": "self_serve", "lead_status": "cold", "lead_score": 0.5, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == "follow_up_architect"


def test_route_nurture_to_follow_up():
    """Nurture lead routes to follow_up_architect."""
    state = {"lead_tier": "nurture", "lead_status": "cold", "lead_score": 0.3, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == "follow_up_architect"


def test_route_disqualified_to_end():
    """Disqualified lead routes to END."""
    state = {"lead_tier": "disqualified", "lead_status": "cold", "lead_score": 0.1, "current_lead": {}, "error": None}
    assert route_after_hunter(state) == END


def test_route_error_to_end():
    """Error state routes to END."""
    state = {"lead_tier": "enterprise", "lead_status": "hot", "lead_score": 0.9, "current_lead": {}, "error": "Something broke"}
    assert route_after_hunter(state) == END


# --- Batch Processing ---

def test_hunt_all_5_leads():
    """All 5 test leads process end-to-end without errors."""
    results = []
    for lead in LEADS:
        result = hunt(lead)
        assert "tier" in result
        assert "score" in result
        assert result["tier"] in ("enterprise", "self_serve", "nurture", "disqualified")
        results.append({
            "lead_status": result["status"],
            "send_result": {"status": "sent"} if result.get("outreach") else {},
            "close_action": "",
            "close_result": {},
        })

    # Calculate batch KPIs
    kpis = calculate_batch_kpis(results)
    assert kpis["total_processed"] == 5
    assert kpis["delivery_rate"] > 0  # At least some leads get outreach


def test_audit_after_batch():
    """Auditor processes each lead's state."""
    for lead in LEADS:
        result = hunt(lead)
        state = {
            "current_lead": lead,
            "lead_tier": result["tier"],
            "lead_status": result["status"],
            "lead_score": result["score"],
            "send_result": {"status": "sent"} if result.get("outreach") else {},
        }
        audit = audit_pipeline(state)
        assert len(audit["kpi_entries"]) > 0


# --- X-sourced lead tests ---

@patch("agents.outreach_hunter.enrich_lead")
def test_x_lead_full_flow(mock_enrich):
    """X-sourced lead flows: enrich -> hunt -> audit -> route."""
    mock_enrich.return_value = {
        "name": "Kyle Vedder", "title": "CEO", "company": "Voiceflow",
        "email": "kyle@voiceflow.com", "email_confidence": 95,
        "verified_email": "kyle@voiceflow.com",
        "x_username": "KyleVedder",
        "x_post_text": "Cursor is great but voice coding would be next level",
        "linkedin_url": "",
    }

    x_lead = {
        "name": "Kyle Vedder", "title": "CEO", "company": "Voiceflow",
        "email": "", "x_username": "KyleVedder",
        "x_post_text": "Cursor is great but voice coding would be next level",
        "linkedin_url": "",
    }

    # Hunt (enriches + qualifies + generates outreach)
    result = hunt(x_lead)
    assert result["lead"]["email"] == "kyle@voiceflow.com"
    assert result["tier"] in ("enterprise", "self_serve")
    assert result["personalized_dm"] != ""
    assert result["channel"] == "email"  # verified email

    # Audit
    state = {
        "current_lead": result["lead"],
        "lead_tier": result["tier"],
        "lead_status": result["status"],
        "lead_score": result["score"],
        "send_result": {"status": "sent", "channel": "email"},
    }
    audit = audit_pipeline(state)
    assert len(audit["kpi_entries"]) > 0
