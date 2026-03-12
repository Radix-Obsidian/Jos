"""Tests for Hunter.io email enrichment + domain search."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from lead_enricher import (
    find_email,
    verify_email,
    is_email_verified,
    enrich_lead,
    enrich_lead_with_domain,
    domain_search,
    _extract_domain,
)


# --- Domain Extraction ---

def test_extract_domain_simple():
    assert _extract_domain("TechStartup") == "techstartup.com"


def test_extract_domain_with_spaces():
    assert _extract_domain("Acme Corp") == "acmecorp.com"


def test_extract_domain_empty():
    assert _extract_domain("") == ""


def test_extract_domain_already_domain():
    assert _extract_domain("example.com") == "example.com"


# --- Email Finder ---

@patch("lead_enricher.requests.get")
def test_find_email_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "email": "kyle@voiceflow.com",
            "score": 91,
        }
    }
    mock_get.return_value = mock_resp

    result = find_email("voiceflow.com", "Kyle", "Vedder")
    assert result["email"] == "kyle@voiceflow.com"
    assert result["score"] == 91


@patch("lead_enricher.requests.get")
def test_find_email_not_found(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "email": None,
            "score": 0,
        }
    }
    mock_get.return_value = mock_resp

    result = find_email("unknown.com", "Nobody", "Here")
    assert result["email"] == ""
    assert result["score"] == 0


@patch("lead_enricher.requests.get")
def test_find_email_api_error(mock_get):
    mock_get.side_effect = Exception("Connection error")
    result = find_email("fail.com", "Test", "User")
    assert result["email"] == ""
    assert result["score"] == 0


# --- Email Verifier ---

@patch("lead_enricher.requests.get")
def test_verify_email_deliverable(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "score": 95,
            "status": "valid",
            "result": "deliverable",
        }
    }
    mock_get.return_value = mock_resp

    result = verify_email("kyle@voiceflow.com")
    assert result["score"] == 95
    assert result["status"] == "valid"


@patch("lead_enricher.requests.get")
def test_verify_email_risky(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "score": 45,
            "status": "accept_all",
            "result": "risky",
        }
    }
    mock_get.return_value = mock_resp

    result = verify_email("maybe@risky.com")
    assert result["score"] == 45


@patch("lead_enricher.requests.get")
def test_verify_email_api_error(mock_get):
    mock_get.side_effect = Exception("Timeout")
    result = verify_email("error@test.com")
    assert result["score"] == 0
    assert result["status"] == "error"


# --- Verification Threshold ---

def test_is_email_verified_high_score():
    assert is_email_verified(95) is True


def test_is_email_verified_at_threshold():
    assert is_email_verified(80) is True


def test_is_email_verified_below_threshold():
    assert is_email_verified(79) is False


def test_is_email_verified_zero():
    assert is_email_verified(0) is False


# --- Full Enrichment ---

@patch("lead_enricher.verify_email")
@patch("lead_enricher.find_email")
def test_enrich_lead_full_flow(mock_find, mock_verify):
    mock_find.return_value = {"email": "kyle@voiceflow.com", "score": 91}
    mock_verify.return_value = {"score": 95, "status": "valid"}

    lead = {
        "name": "Kyle Vedder",
        "title": "CEO",
        "company": "Voiceflow",
        "email": "",
        "x_username": "KyleVedder",
    }

    enriched = enrich_lead(lead)
    assert enriched["email"] == "kyle@voiceflow.com"
    assert enriched["email_confidence"] == 95
    assert enriched["verified_email"] == "kyle@voiceflow.com"


@patch("lead_enricher.verify_email")
@patch("lead_enricher.find_email")
def test_enrich_lead_no_email_found(mock_find, mock_verify):
    mock_find.return_value = {"email": "", "score": 0}

    lead = {
        "name": "Nobody Known",
        "title": "Engineer",
        "company": "Unknown",
        "email": "",
        "x_username": "nobody",
    }

    enriched = enrich_lead(lead)
    assert enriched["email"] == ""
    assert enriched["email_confidence"] == 0
    assert enriched["verified_email"] == ""
    mock_verify.assert_not_called()


@patch("lead_enricher.verify_email")
@patch("lead_enricher.find_email")
def test_enrich_lead_existing_email_verified(mock_find, mock_verify):
    """If lead already has an email, verify it instead of finding a new one."""
    mock_verify.return_value = {"score": 88, "status": "valid"}

    lead = {
        "name": "Test User",
        "title": "CTO",
        "company": "TestCo",
        "email": "test@testco.com",
        "x_username": "testuser",
    }

    enriched = enrich_lead(lead)
    assert enriched["email"] == "test@testco.com"
    assert enriched["email_confidence"] == 88
    mock_find.assert_not_called()


@patch("lead_enricher.verify_email")
@patch("lead_enricher.find_email")
def test_enrich_lead_no_company(mock_find, mock_verify):
    """If no company, can't find email — skip enrichment."""
    lead = {
        "name": "Solo Dev",
        "title": "",
        "company": "",
        "email": "",
        "x_username": "solodev",
    }

    enriched = enrich_lead(lead)
    assert enriched["email"] == ""
    assert enriched["email_confidence"] == 0
    mock_find.assert_not_called()
    mock_verify.assert_not_called()


# --- Domain Search ---

@patch("lead_enricher.HUNTER_API_KEY", "fake-key-for-test")
@patch("lead_enricher.requests.get")
def test_domain_search_returns_industry_and_size(mock_get):
    """domain_search returns industry and employees from Hunter response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {"domain": "railway.app", "industry": "cloud infrastructure", "employees": 45}
    }
    mock_get.return_value = mock_resp

    result = domain_search("railway.app")
    assert result["industry"] == "cloud infrastructure"
    assert result["employees"] == 45


@patch("lead_enricher.requests.get")
def test_domain_search_returns_empty_on_api_error(mock_get):
    """domain_search returns empty gracefully on non-200 response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_get.return_value = mock_resp

    result = domain_search("somecompany.com")
    assert result["industry"] == ""
    assert result["employees"] == 0


@patch("lead_enricher.requests.get")
def test_domain_search_returns_empty_on_exception(mock_get):
    """domain_search returns empty gracefully on network error."""
    mock_get.side_effect = ConnectionError("down")
    result = domain_search("somecompany.com")
    assert result["industry"] == ""
    assert result["employees"] == 0


def test_domain_search_skips_when_no_api_key(monkeypatch):
    """domain_search returns empty when HUNTER_API_KEY is not set."""
    monkeypatch.setattr("lead_enricher.HUNTER_API_KEY", "")
    result = domain_search("railway.app")
    assert result["industry"] == ""
    assert result["employees"] == 0


# --- enrich_lead_with_domain ---

@patch("lead_enricher.HUNTER_API_KEY", "fake-key-for-test")
@patch("lead_enricher.set_domain_cache")
@patch("lead_enricher.get_domain_cache", return_value=None)
@patch("lead_enricher.requests.get")
def test_enrich_lead_populates_industry_from_domain_search(mock_get, mock_cache_get, mock_cache_set):
    """enrich_lead_with_domain sets industry and company_size from Hunter on cache miss."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {"industry": "developer tools", "employees": 80}
    }
    mock_get.return_value = mock_resp

    import lead_enricher
    lead_enricher._DOMAIN_CACHE.pop("anysphere.com", None)  # clear in-memory cache

    lead = {"name": "Michael Truell", "company": "Anysphere", "email": "m@anysphere.co"}
    enriched = enrich_lead_with_domain(lead)
    assert enriched["industry"] == "developer tools"
    assert enriched["company_size"] == 80
    mock_cache_set.assert_called_once_with("anysphere.com", "developer tools", 80, None)


@patch("lead_enricher.requests.get")
def test_enrich_lead_with_domain_does_not_overwrite_existing(mock_get):
    """enrich_lead_with_domain skips API call if both fields already set."""
    lead = {"name": "Jane", "company": "Acme", "industry": "saas", "company_size": 50}
    result = enrich_lead_with_domain(lead)
    mock_get.assert_not_called()
    assert result["industry"] == "saas"
    assert result["company_size"] == 50


def test_enrich_lead_with_domain_handles_missing_company():
    """enrich_lead_with_domain skips gracefully if no company."""
    lead = {"name": "No One", "company": ""}
    result = enrich_lead_with_domain(lead)
    assert result == lead


@patch("lead_enricher.set_domain_cache")
@patch("lead_enricher.get_domain_cache")
@patch("lead_enricher.requests.get")
def test_enrich_lead_with_domain_sqlite_cache_hit_skips_api(mock_get, mock_cache_get, mock_cache_set):
    """SQLite cache hit means Hunter API is not called."""
    mock_cache_get.return_value = {"industry": "cloud infrastructure", "employees": 45}

    import lead_enricher
    lead_enricher._DOMAIN_CACHE.pop("railway.com", None)

    lead = {"name": "Jake Cooper", "company": "Railway"}
    enriched = enrich_lead_with_domain(lead)

    mock_get.assert_not_called()          # Hunter API never called
    mock_cache_set.assert_not_called()    # Nothing new to write
    assert enriched["industry"] == "cloud infrastructure"
    assert enriched["company_size"] == 45


@patch("lead_enricher.set_domain_cache")
@patch("lead_enricher.get_domain_cache", return_value=None)
@patch("lead_enricher.requests.get")
def test_enrich_lead_with_domain_memory_cache_hit_skips_both(mock_get, mock_cache_get, mock_cache_set):
    """In-memory cache hit skips both SQLite and Hunter API."""
    import lead_enricher
    lead_enricher._DOMAIN_CACHE["memcache-test.com"] = {
        "industry": "fintech", "employees": 100
    }

    lead = {"name": "Test Person", "company": "memcache-test.com"}
    enriched = enrich_lead_with_domain(lead)

    mock_get.assert_not_called()
    mock_cache_get.assert_not_called()
    assert enriched["industry"] == "fintech"

    # Cleanup
    lead_enricher._DOMAIN_CACHE.pop("memcache-test.com", None)
