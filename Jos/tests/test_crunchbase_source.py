"""Tests for lead_sources/crunchbase_source.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_sources.crunchbase_source import CrunchbaseSource


@pytest.fixture()
def source():
    return CrunchbaseSource()


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setattr("lead_sources.crunchbase_source.CRUNCHBASE_API_KEY", "cb-test-key")


# ---------- is_configured ----------

def test_configured(source):
    assert source.is_configured() is True


def test_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.crunchbase_source.CRUNCHBASE_API_KEY", "")
    assert source.is_configured() is False


# ---------- _parse_employees ----------

def test_parse_employees_range():
    assert CrunchbaseSource._parse_employees("c_0051_0100") == 75


def test_parse_employees_single():
    assert CrunchbaseSource._parse_employees("c_0010_0010") == 10


def test_parse_employees_empty():
    assert CrunchbaseSource._parse_employees("") == 0


def test_parse_employees_invalid():
    assert CrunchbaseSource._parse_employees("unknown") == 0


# ---------- discover_leads ----------

@patch("lead_sources.crunchbase_source.get_source_cache", return_value=None)
@patch("lead_sources.crunchbase_source.set_source_cache")
@patch("lead_sources.crunchbase_source.requests.get")
def test_discover_success(mock_get, mock_set, mock_cache, source):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "entities": [
                {
                    "properties": {
                        "name": "VoiceTech",
                        "funding_stage": "seed",
                        "funding_total": {"value_usd": 5000000},
                        "web_path": "organization/voicetech",
                        "num_employees_enum": "c_0011_0050",
                        "founder_identifiers": [
                            {"value": "John Founder"},
                        ],
                    }
                }
            ]
        },
    )
    leads = source.discover_leads("voice AI", limit=5)
    assert len(leads) == 1
    assert leads[0]["name"] == "John Founder"
    assert leads[0]["funding_stage"] == "seed"
    assert leads[0]["source"] == "crunchbase"


@patch("lead_sources.crunchbase_source.get_source_cache")
def test_discover_cache_hit(mock_cache, source):
    cached = [{"name": "Cached"}]
    mock_cache.return_value = cached
    leads = source.discover_leads("voice AI")
    assert leads == cached


@patch("lead_sources.crunchbase_source.get_source_cache", return_value=None)
@patch("lead_sources.crunchbase_source.requests.get")
def test_discover_http_error(mock_get, mock_cache, source):
    mock_get.return_value = MagicMock(status_code=403)
    assert source.discover_leads("voice AI") == []


def test_discover_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.crunchbase_source.CRUNCHBASE_API_KEY", "")
    assert source.discover_leads("test") == []


# ---------- enrich_lead ----------

@patch("lead_sources.crunchbase_source.get_source_cache", return_value=None)
@patch("lead_sources.crunchbase_source.set_source_cache")
@patch("lead_sources.crunchbase_source.requests.get")
def test_enrich_success(mock_get, mock_set, mock_cache, source):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "properties": {
                "funding_stage": "series_a",
                "funding_total": {"value_usd": 10000000},
                "num_employees_enum": "c_0051_0100",
            }
        },
    )
    result = source.enrich_lead({"company": "TechCo", "name": "Alice"})
    assert result["funding_stage"] == "series_a"


def test_enrich_no_company(source):
    result = source.enrich_lead({"name": "Alice"})
    assert result == {"name": "Alice"}


def test_enrich_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.crunchbase_source.CRUNCHBASE_API_KEY", "")
    result = source.enrich_lead({"company": "TechCo", "name": "Alice"})
    assert result == {"company": "TechCo", "name": "Alice"}


@patch("lead_sources.crunchbase_source.get_source_cache")
def test_enrich_cache_hit(mock_cache, source):
    mock_cache.return_value = {"funding_stage": "seed"}
    result = source.enrich_lead({"company": "TechCo", "name": "Alice"})
    assert result["funding_stage"] == "seed"
