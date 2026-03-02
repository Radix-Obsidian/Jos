"""Tests for Slice 1: Outreach Hunter (scan + qualify + DM generation)."""

import pytest
from unittest.mock import patch, MagicMock
from agents.outreach_hunter import (
    scan_leads, parse_lead, validate_lead,
    qualify_lead, score_lead, assign_tier, determine_status,
    generate_outreach, write_email, write_linkedin,
    hunt,
)
from config import SCORE_ENTERPRISE, SCORE_SELF_SERVE, SCORE_NURTURE
import ledger


# --- Fixtures ---

MOCK_HTML = """
<html><body>
<div class="person">
  <h3>Jane Smith</h3>
  <span class="title">CTO</span>
  <span class="company">Acme AI</span>
  <a href="mailto:jane@acmeai.com">jane@acmeai.com</a>
  <a href="https://linkedin.com/in/janesmith">LinkedIn</a>
</div>
<div class="person">
  <h3>Bob Lee</h3>
  <span class="title">Marketing Intern</span>
  <span class="company">TinyStartup</span>
  <a href="mailto:bob@tiny.com">bob@tiny.com</a>
</div>
</body></html>
"""

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


# --- Scanner Tests ---

def test_scan_leads_returns_list():
    """scan_leads returns a list of lead dicts."""
    with patch("agents.outreach_hunter.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_HTML
        mock_get.return_value = mock_resp

        leads = scan_leads("AI startups")
        assert isinstance(leads, list)
        assert len(leads) > 0


def test_scan_leads_structured_output():
    """Each lead has required fields."""
    with patch("agents.outreach_hunter.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_HTML
        mock_get.return_value = mock_resp

        leads = scan_leads("AI startups")
        for lead in leads:
            assert "name" in lead
            assert "company" in lead
            assert "title" in lead
            assert "email" in lead


def test_parse_lead_extracts_fields():
    """parse_lead extracts name, title, company, email from HTML element."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(MOCK_HTML, "html.parser")
    person = soup.find("div", class_="person")

    lead = parse_lead(person)
    assert lead["name"] == "Jane Smith"
    assert lead["title"] == "CTO"
    assert lead["company"] == "Acme AI"
    assert lead["email"] == "jane@acmeai.com"


def test_validate_lead_good():
    assert validate_lead({"name": "Jane", "email": "j@a.com"}) is True


def test_validate_lead_missing_email():
    assert validate_lead({"name": "Jane", "email": ""}) is False


def test_validate_lead_missing_name():
    assert validate_lead({"name": "", "email": "j@a.com"}) is False


def test_scan_leads_handles_http_error():
    with patch("agents.outreach_hunter.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        assert scan_leads("AI startups") == []


def test_scan_leads_handles_connection_error():
    with patch("agents.outreach_hunter.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("Network down")
        assert scan_leads("AI startups") == []


# --- Qualifier Tests ---

def test_score_lead_returns_float():
    score = score_lead(LEADS[0])
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_enterprise_lead_high():
    """CTO at AI company scores >= enterprise threshold."""
    score = score_lead(LEADS[0])
    assert score >= SCORE_ENTERPRISE


def test_score_self_serve_lead_medium():
    """Engineering Manager at TechCorp scores >= 0.4."""
    score = score_lead(LEADS[3])
    assert score >= SCORE_SELF_SERVE


def test_score_weak_lead_low():
    """Marketing Intern scores low."""
    score = score_lead(LEADS[4])
    assert score < SCORE_SELF_SERVE


def test_score_penalizes_coo_title():
    """COO in title → capped at 0.15 title score, not full +0.4."""
    lead = {"name": "Sobhan Nejad", "title": "Co-Founder & COO", "company": "Bland AI",
            "email": "sobhan@bland.ai", "linkedin_url": ""}
    score = score_lead(lead)
    # Without COO fix, would score ~0.80 (enterprise/hot). With fix, should be < enterprise.
    assert score < SCORE_ENTERPRISE


def test_score_penalizes_large_company():
    """Company with 1400 employees → big penalty pushes score to disqualified range."""
    lead = {"name": "Tiago Paiva", "title": "CEO", "company": "Talkdesk",
            "email": "tiago@talkdesk.com", "linkedin_url": "", "company_size": 1400}
    score = score_lead(lead)
    assert score < SCORE_NURTURE  # disqualified


def test_score_penalizes_tiny_company():
    """Company with 6 employees → soft penalty, not disqualified."""
    lead = {"name": "Zeno Rocha", "title": "CEO", "company": "Resend",
            "email": "zeno@resend.com", "linkedin_url": "https://linkedin.com/in/zenorocha", "company_size": 6}
    score = score_lead(lead)
    # Penalty pushes below enterprise but stays above self_serve threshold
    assert SCORE_SELF_SERVE <= score < SCORE_ENTERPRISE


def test_score_competitor_returns_near_zero():
    """Competitor company → near-zero score → disqualified."""
    lead = {"name": "Mati Staniszewski", "title": "CEO", "company": "ElevenLabs",
            "email": "mati@elevenlabs.io", "linkedin_url": ""}
    score = score_lead(lead)
    assert score <= 0.1


def test_score_email_weighted_more_than_linkedin():
    """Email is worth more than LinkedIn in the new scoring."""
    base = {"name": "X", "title": "CTO", "company": "AISaaS", "email": "", "linkedin_url": ""}
    with_email = {**base, "email": "x@ai.com"}
    with_linkedin = {**base, "linkedin_url": "https://linkedin.com/in/x"}
    assert score_lead(with_email) > score_lead(with_linkedin)


def test_score_lead_uses_industry_field_when_present():
    """Real industry field gives direct +0.3 signal, bypassing company name guessing."""
    # Anysphere has no AI/tech keyword in name — without industry field scores low
    base = {"name": "Michael Truell", "title": "CEO", "company": "Anysphere",
            "email": "m@anysphere.co", "linkedin_url": ""}
    with_industry = {**base, "industry": "developer tools"}
    assert score_lead(with_industry) > score_lead(base)


def test_assign_tier_enterprise():
    assert assign_tier(0.85) == "enterprise"


def test_assign_tier_self_serve():
    assert assign_tier(0.55) == "self_serve"


def test_assign_tier_nurture():
    assert assign_tier(0.3) == "nurture"


def test_assign_tier_disqualified():
    assert assign_tier(0.1) == "disqualified"


def test_qualify_lead_returns_dict():
    result = qualify_lead(LEADS[0])
    assert isinstance(result, dict)
    assert "score" in result
    assert "tier" in result
    assert "lead" in result
    assert "status" in result


def test_qualify_lead_enterprise():
    result = qualify_lead(LEADS[0])
    assert result["tier"] == "enterprise"


def test_determine_status_hot():
    """Enterprise with score >= 0.8 -> hot."""
    assert determine_status(0.9, "enterprise") == "hot"


def test_determine_status_cold():
    """Self-serve -> cold."""
    assert determine_status(0.5, "self_serve") == "cold"


# --- Outreach Writer Tests ---

def test_write_email_returns_dict():
    msg = write_email(LEADS[0], tier="enterprise")
    assert "subject" in msg
    assert "body" in msg


def test_write_email_contains_name():
    msg = write_email(LEADS[0], tier="enterprise")
    assert "Sarah" in msg["body"]


def test_write_email_contains_company():
    msg = write_email(LEADS[0], tier="enterprise")
    assert "DataFlow" in msg["body"]


def test_write_linkedin_returns_dict():
    msg = write_linkedin(LEADS[0], tier="self_serve")
    assert "body" in msg


def test_write_linkedin_contains_name():
    msg = write_linkedin(LEADS[0], tier="self_serve")
    assert "Sarah" in msg["body"]


def test_generate_outreach_email():
    result = generate_outreach(LEADS[0], tier="enterprise", channel="email")
    assert result["channel"] == "email"
    assert "subject" in result["message"]
    assert result["personalized_dm"] != ""


def test_generate_outreach_linkedin():
    result = generate_outreach(LEADS[0], tier="self_serve", channel="linkedin")
    assert result["channel"] == "linkedin"


# --- Full Hunt Pipeline ---

def test_hunt_enterprise_lead():
    """Enterprise lead gets qualified and outreach generated."""
    result = hunt(LEADS[0])
    assert result["tier"] == "enterprise"
    assert result["personalized_dm"] != ""
    assert result["outreach"] is not None


def test_hunt_disqualified_lead():
    """Weak lead gets disqualified with no outreach."""
    result = hunt(LEADS[4])
    assert result["tier"] in ("nurture", "disqualified")
    if result["tier"] == "disqualified":
        assert result["outreach"] is None
        assert result["personalized_dm"] == ""


def test_validate_lead_with_x_username():
    """X-sourced lead is valid with name + x_username (no email needed)."""
    assert validate_lead({"name": "Kyle", "x_username": "KyleVedder", "email": ""}) is True


def test_scan_leads_x_source():
    """scan_leads(source='x') delegates to search_x_leads."""
    with patch("agents.outreach_hunter.search_x_leads") as mock_x:
        mock_x.return_value = [
            {"name": "Kyle Vedder", "title": "CEO", "company": "Voiceflow",
             "email": "", "x_username": "KyleVedder", "x_post_text": "voice coding is the future"},
        ]
        leads = scan_leads("voice coding", source="x")
        assert len(leads) == 1
        assert leads[0]["x_username"] == "KyleVedder"
        mock_x.assert_called_once_with("voice coding")


@patch("agents.outreach_hunter.enrich_lead")
def test_hunt_x_lead_triggers_enrichment(mock_enrich):
    """Hunt enriches X-sourced leads that have no email."""
    mock_enrich.return_value = {
        "name": "Kyle Vedder", "title": "CEO", "company": "Voiceflow",
        "email": "kyle@voiceflow.com", "email_confidence": 95,
        "verified_email": "kyle@voiceflow.com",
        "x_username": "KyleVedder", "x_post_text": "voice coding is great",
        "linkedin_url": "",
    }
    lead = {"name": "Kyle Vedder", "title": "CEO", "company": "Voiceflow",
            "email": "", "x_username": "KyleVedder", "x_post_text": "voice coding is great",
            "linkedin_url": ""}

    result = hunt(lead)
    mock_enrich.assert_called_once()
    assert result["lead"]["email"] == "kyle@voiceflow.com"
    assert result["channel"] == "email"  # verified email -> email channel


def test_hunt_all_5_leads():
    """All 5 test leads process without errors."""
    for lead in LEADS:
        result = hunt(lead)
        assert "tier" in result
        assert "score" in result
        assert result["tier"] in ("enterprise", "self_serve", "nurture", "disqualified")
