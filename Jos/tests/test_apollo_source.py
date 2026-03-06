"""Tests for lead_sources/apollo_source.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_sources.apollo_source import ApolloSource


@pytest.fixture()
def source():
    return ApolloSource()


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setattr("lead_sources.apollo_source.APOLLO_API_KEY", "test-key")


# ---------- is_configured ----------

def test_configured_with_key(source):
    assert source.is_configured() is True


def test_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.apollo_source.APOLLO_API_KEY", "")
    assert source.is_configured() is False


# ---------- discover_leads ----------

@patch("lead_sources.apollo_source.get_source_cache", return_value=None)
@patch("lead_sources.apollo_source.set_source_cache")
@patch("lead_sources.apollo_source.requests.post")
def test_discover_success(mock_post, mock_set, mock_get, source):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "people": [
                {
                    "name": "Alice Smith",
                    "title": "CTO",
                    "email": "alice@co.com",
                    "linkedin_url": "https://linkedin.com/in/alice",
                    "organization": {
                        "name": "TechCo",
                        "funding_stage": "series_a",
                        "estimated_num_employees": 50,
                    },
                }
            ]
        },
    )
    leads = source.discover_leads("voice AI", limit=5)
    assert len(leads) == 1
    assert leads[0]["name"] == "Alice Smith"
    assert leads[0]["source"] == "apollo"
    assert leads[0]["funding_stage"] == "series_a"
    mock_set.assert_called_once()


@patch("lead_sources.apollo_source.get_source_cache")
def test_discover_cache_hit(mock_get, source):
    cached = [{"name": "Cached Lead", "source": "apollo"}]
    mock_get.return_value = cached
    leads = source.discover_leads("voice AI")
    assert leads == cached


@patch("lead_sources.apollo_source.get_source_cache", return_value=None)
@patch("lead_sources.apollo_source.requests.post")
def test_discover_http_error(mock_post, mock_get, source):
    mock_post.return_value = MagicMock(status_code=429)
    leads = source.discover_leads("voice AI")
    assert leads == []


@patch("lead_sources.apollo_source.get_source_cache", return_value=None)
@patch("lead_sources.apollo_source.requests.post", side_effect=Exception("Timeout"))
def test_discover_exception(mock_post, mock_get, source):
    leads = source.discover_leads("voice AI")
    assert leads == []


def test_discover_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.apollo_source.APOLLO_API_KEY", "")
    leads = source.discover_leads("voice AI")
    assert leads == []


# ---------- enrich_lead ----------

@patch("lead_sources.apollo_source.get_source_cache", return_value=None)
@patch("lead_sources.apollo_source.set_source_cache")
@patch("lead_sources.apollo_source.requests.post")
def test_enrich_by_email(mock_post, mock_set, mock_get, source):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "person": {
                "email": "alice@co.com",
                "title": "CTO",
                "linkedin_url": "https://linkedin.com/in/alice",
                "organization": {
                    "funding_stage": "seed",
                    "estimated_num_employees": 30,
                },
            }
        },
    )
    result = source.enrich_lead({"email": "alice@co.com", "name": "Alice"})
    assert result["funding_stage"] == "seed"


@patch("lead_sources.apollo_source.get_source_cache")
def test_enrich_cache_hit(mock_get, source):
    mock_get.return_value = {"funding_stage": "series_b"}
    result = source.enrich_lead({"email": "a@b.com", "name": "A"})
    assert result["funding_stage"] == "series_b"


def test_enrich_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.apollo_source.APOLLO_API_KEY", "")
    result = source.enrich_lead({"name": "Alice"})
    assert result == {"name": "Alice"}


def test_enrich_no_identifiers(source):
    result = source.enrich_lead({"title": "CTO"})
    assert result == {"title": "CTO"}
