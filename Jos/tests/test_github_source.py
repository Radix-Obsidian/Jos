"""Tests for lead_sources/github_source.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_sources.github_source import GitHubSource


@pytest.fixture()
def source():
    return GitHubSource()


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    monkeypatch.setattr("lead_sources.github_source.GITHUB_TOKEN", "ghp_test123")


# ---------- is_configured ----------

def test_configured(source):
    assert source.is_configured() is True


def test_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.github_source.GITHUB_TOKEN", "")
    assert source.is_configured() is False


# ---------- _extract_title ----------

def test_extract_title_cto():
    assert GitHubSource._extract_title("CTO at TechCo") == "CTO"


def test_extract_title_founder():
    assert GitHubSource._extract_title("Co-Founder building cool stuff") == "Co-Founder"


def test_extract_title_empty():
    assert GitHubSource._extract_title("") == ""


def test_extract_title_no_match():
    assert GitHubSource._extract_title("Software developer who loves cats") == ""


# ---------- discover_leads ----------

@patch("lead_sources.github_source.get_source_cache", return_value=None)
@patch("lead_sources.github_source.set_source_cache")
@patch("lead_sources.github_source.requests.get")
def test_discover_success(mock_get, mock_set, mock_cache_get, source):
    # Mock repo search
    repo_resp = MagicMock(
        status_code=200,
        json=lambda: {"items": [{"full_name": "org/voice-lib"}]},
    )
    # Mock stargazers
    sg_resp = MagicMock(
        status_code=200,
        json=lambda: [{"login": "alice"}],
    )
    # Mock user profile
    user_resp = MagicMock(
        status_code=200,
        json=lambda: {
            "name": "Alice Smith",
            "bio": "CTO at VoiceCo",
            "company": "VoiceCo",
            "email": "alice@voiceco.com",
            "twitter_username": "alicesmith",
            "html_url": "https://github.com/alice",
        },
    )

    mock_get.side_effect = [repo_resp, sg_resp, user_resp]
    leads = source.discover_leads("voice AI", limit=5)
    assert len(leads) == 1
    assert leads[0]["name"] == "Alice Smith"
    assert leads[0]["source"] == "github"


@patch("lead_sources.github_source.get_source_cache")
def test_discover_cache_hit(mock_cache, source):
    cached = [{"name": "Cached", "source": "github"}]
    mock_cache.return_value = cached
    leads = source.discover_leads("voice AI")
    assert leads == cached


@patch("lead_sources.github_source.get_source_cache", return_value=None)
@patch("lead_sources.github_source.requests.get")
def test_discover_http_error(mock_get, mock_cache, source):
    mock_get.return_value = MagicMock(status_code=403)
    leads = source.discover_leads("voice AI")
    assert leads == []


def test_discover_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.github_source.GITHUB_TOKEN", "")
    assert source.discover_leads("test") == []


# ---------- enrich_lead ----------

@patch("lead_sources.github_source.get_source_cache", return_value=None)
@patch("lead_sources.github_source.set_source_cache")
@patch("lead_sources.github_source.requests.get")
def test_enrich_success(mock_get, mock_set, mock_cache, source):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "email": "alice@co.com",
            "company": "TechCo",
            "twitter_username": "alice",
            "blog": "",
        },
    )
    result = source.enrich_lead({"github_url": "https://github.com/alice", "name": "Alice"})
    assert result["email"] == "alice@co.com"
    assert result["company"] == "TechCo"


def test_enrich_no_github_url(source):
    result = source.enrich_lead({"name": "Alice"})
    assert result == {"name": "Alice"}


@patch("lead_sources.github_source.get_source_cache")
def test_enrich_cache_hit(mock_cache, source):
    mock_cache.return_value = {"email": "cached@co.com"}
    result = source.enrich_lead({"github_url": "https://github.com/alice", "name": "Alice"})
    assert result["email"] == "cached@co.com"
