"""Tests for lead_sources/producthunt_source.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lead_sources.producthunt_source import ProductHuntSource


@pytest.fixture()
def source():
    return ProductHuntSource()


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    monkeypatch.setattr("lead_sources.producthunt_source.PRODUCTHUNT_TOKEN", "ph-test-token")


# ---------- is_configured ----------

def test_configured(source):
    assert source.is_configured() is True


def test_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.producthunt_source.PRODUCTHUNT_TOKEN", "")
    assert source.is_configured() is False


# ---------- discover_leads ----------

@patch("lead_sources.producthunt_source.get_source_cache", return_value=None)
@patch("lead_sources.producthunt_source.set_source_cache")
@patch("lead_sources.producthunt_source.requests.post")
def test_discover_success(mock_post, mock_set, mock_get, source):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                "id": "1",
                                "name": "VoiceApp",
                                "tagline": "Voice for teams",
                                "url": "https://producthunt.com/posts/voiceapp",
                                "makers": [
                                    {
                                        "id": "m1",
                                        "name": "Jane Maker",
                                        "headline": "Founder of VoiceApp",
                                        "twitterUsername": "janemaker",
                                        "websiteUrl": "https://voiceapp.com",
                                    }
                                ],
                            }
                        }
                    ]
                }
            }
        },
    )
    leads = source.discover_leads("voice", limit=5)
    assert len(leads) == 1
    assert leads[0]["name"] == "Jane Maker"
    assert leads[0]["source"] == "producthunt"
    assert leads[0]["x_username"] == "janemaker"


@patch("lead_sources.producthunt_source.get_source_cache")
def test_discover_cache_hit(mock_cache, source):
    cached = [{"name": "Cached Maker"}]
    mock_cache.return_value = cached
    leads = source.discover_leads("voice")
    assert leads == cached


@patch("lead_sources.producthunt_source.get_source_cache", return_value=None)
@patch("lead_sources.producthunt_source.requests.post")
def test_discover_http_error(mock_post, mock_cache, source):
    mock_post.return_value = MagicMock(status_code=401)
    leads = source.discover_leads("voice")
    assert leads == []


@patch("lead_sources.producthunt_source.get_source_cache", return_value=None)
@patch("lead_sources.producthunt_source.requests.post", side_effect=Exception("Timeout"))
def test_discover_exception(mock_post, mock_cache, source):
    leads = source.discover_leads("voice")
    assert leads == []


def test_discover_not_configured(source, monkeypatch):
    monkeypatch.setattr("lead_sources.producthunt_source.PRODUCTHUNT_TOKEN", "")
    assert source.discover_leads("voice") == []


# ---------- enrich_lead ----------

def test_enrich_passthrough(source):
    lead = {"name": "Alice", "email": "a@b.com"}
    result = source.enrich_lead(lead)
    assert result == lead
