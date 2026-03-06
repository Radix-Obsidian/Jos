"""Tests for lead_sources/pdl_source.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_sources.pdl_source import PDLSource


@pytest.fixture()
def source():
    return PDLSource()


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setattr("lead_sources.pdl_source.PDL_API_KEY", "pdl-test-key")


# ---------- is_configured ----------

def test_configured(source):
    assert source.is_configured() is True


def test_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.pdl_source.PDL_API_KEY", "")
    assert source.is_configured() is False


# ---------- _parse_size ----------

def test_parse_size_range():
    assert PDLSource._parse_size("51-200") == 125


def test_parse_size_single():
    assert PDLSource._parse_size("100") == 100


def test_parse_size_empty():
    assert PDLSource._parse_size("") == 0


def test_parse_size_none():
    assert PDLSource._parse_size(None) == 0


# ---------- discover_leads ----------

@patch("lead_sources.pdl_source.get_source_cache", return_value=None)
@patch("lead_sources.pdl_source.set_source_cache")
@patch("lead_sources.pdl_source.requests.post")
def test_discover_success(mock_post, mock_set, mock_cache, source):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": [
                {
                    "full_name": "Alice PDL",
                    "first_name": "Alice",
                    "last_name": "PDL",
                    "job_title": "CTO",
                    "job_company_name": "DataCo",
                    "work_email": "alice@dataco.com",
                    "linkedin_url": "https://linkedin.com/in/alice",
                    "twitter_url": "https://twitter.com/alicepdl",
                    "github_url": "https://github.com/alice",
                    "job_company_size": "51-200",
                }
            ]
        },
    )
    leads = source.discover_leads("data science", limit=5)
    assert len(leads) == 1
    assert leads[0]["name"] == "Alice PDL"
    assert leads[0]["source"] == "pdl"
    assert leads[0]["email"] == "alice@dataco.com"
    assert leads[0]["x_username"] == "alicepdl"


@patch("lead_sources.pdl_source.get_source_cache")
def test_discover_cache_hit(mock_cache, source):
    cached = [{"name": "Cached"}]
    mock_cache.return_value = cached
    leads = source.discover_leads("data")
    assert leads == cached


@patch("lead_sources.pdl_source.get_source_cache", return_value=None)
@patch("lead_sources.pdl_source.requests.post")
def test_discover_http_error(mock_post, mock_cache, source):
    mock_post.return_value = MagicMock(status_code=402)
    assert source.discover_leads("data") == []


def test_discover_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.pdl_source.PDL_API_KEY", "")
    assert source.discover_leads("test") == []


# ---------- enrich_lead ----------

@patch("lead_sources.pdl_source.get_source_cache", return_value=None)
@patch("lead_sources.pdl_source.set_source_cache")
@patch("lead_sources.pdl_source.requests.get")
def test_enrich_by_email(mock_get, mock_set, mock_cache, source):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "work_email": "alice@dataco.com",
            "job_title": "CTO",
            "linkedin_url": "https://linkedin.com/in/alice",
            "twitter_url": "https://twitter.com/alice",
            "github_url": "https://github.com/alice",
            "job_company_size": "51-200",
        },
    )
    result = source.enrich_lead({"email": "alice@dataco.com", "name": "Alice"})
    assert result["linkedin_url"] == "https://linkedin.com/in/alice"


@patch("lead_sources.pdl_source.get_source_cache", return_value=None)
@patch("lead_sources.pdl_source.set_source_cache")
@patch("lead_sources.pdl_source.requests.get")
def test_enrich_by_name_company(mock_get, mock_set, mock_cache, source):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "work_email": "bob@co.com",
            "job_title": "VP Engineering",
            "linkedin_url": "",
            "twitter_url": "",
            "github_url": "",
            "job_company_size": "11-50",
        },
    )
    result = source.enrich_lead({"name": "Bob Smith", "company": "TechCo", "email": ""})
    assert result["email"] == "bob@co.com"


def test_enrich_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.pdl_source.PDL_API_KEY", "")
    result = source.enrich_lead({"name": "Alice"})
    assert result == {"name": "Alice"}


def test_enrich_no_identifiers(source):
    result = source.enrich_lead({"title": "CTO"})
    assert result == {"title": "CTO"}


@patch("lead_sources.pdl_source.get_source_cache")
def test_enrich_cache_hit(mock_cache, source):
    mock_cache.return_value = {"email": "cached@co.com"}
    result = source.enrich_lead({"email": "x@y.com", "name": "Alice"})
    assert result["email"] == "cached@co.com"
