"""Tests for X/Twitter lead scraping via snscrape."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from x_scraper import (
    search_x_leads,
    filter_tweet,
    extract_lead_from_tweet,
    parse_bio,
)
import ledger


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


def _make_tweet(
    username="techceo",
    display_name="Tech CEO",
    text="Cursor is great but voice coding would be amazing",
    bio="CEO at TechStartup | AI enthusiast",
    followers=500,
    faves=10,
    created_days_ago=2,
):
    """Create a mock tweet object matching snscrape's Tweet model."""
    tweet = MagicMock()
    tweet.user = MagicMock()
    tweet.user.username = username
    tweet.user.displayname = display_name
    tweet.user.rawDescription = bio
    tweet.user.followersCount = followers
    tweet.rawContent = text
    tweet.likeCount = faves
    tweet.date = datetime.now(timezone.utc) - timedelta(days=created_days_ago)
    return tweet


# --- Bio Parsing Tests ---

def test_parse_bio_ceo():
    result = parse_bio("CEO at TechStartup | AI enthusiast")
    assert result["title"] == "CEO"
    assert "TechStartup" in result["company"]


def test_parse_bio_cto_at_sign():
    result = parse_bio("CTO @CloudSaaS | Building the future")
    assert result["title"] == "CTO"
    assert "CloudSaaS" in result["company"]


def test_parse_bio_founder():
    result = parse_bio("Founder of AITools. YC W24.")
    assert result["title"] == "Founder"
    assert "AITools" in result["company"]


def test_parse_bio_no_title():
    result = parse_bio("Just a person who codes")
    assert result["title"] == ""


def test_parse_bio_empty():
    result = parse_bio("")
    assert result["title"] == ""
    assert result["company"] == ""


# --- Filter Tests ---

def test_filter_tweet_passes_valid():
    tweet = _make_tweet(followers=100, faves=10, created_days_ago=2)
    assert filter_tweet(tweet, min_followers=50, min_faves=5, max_age_days=7) is True


def test_filter_tweet_rejects_low_followers():
    tweet = _make_tweet(followers=10)
    assert filter_tweet(tweet, min_followers=50, min_faves=5, max_age_days=7) is False


def test_filter_tweet_rejects_old():
    tweet = _make_tweet(created_days_ago=14)
    assert filter_tweet(tweet, min_followers=50, min_faves=5, max_age_days=7) is False


def test_filter_tweet_rejects_low_faves():
    tweet = _make_tweet(faves=1)
    assert filter_tweet(tweet, min_followers=50, min_faves=5, max_age_days=7) is False


# --- Extraction Tests ---

def test_extract_lead_from_tweet():
    tweet = _make_tweet()
    lead = extract_lead_from_tweet(tweet)
    assert lead["name"] == "Tech CEO"
    assert lead["x_username"] == "techceo"
    assert lead["x_post_text"] == "Cursor is great but voice coding would be amazing"
    assert "CEO" in lead["title"]
    assert "TechStartup" in lead["company"]


def test_extract_lead_has_all_required_fields():
    tweet = _make_tweet()
    lead = extract_lead_from_tweet(tweet)
    for field in ["name", "title", "company", "email", "linkedin_url", "x_username", "x_post_text"]:
        assert field in lead


# --- Integration (mocked snscrape) ---

def test_search_x_leads_returns_list():
    mock_tweets = [
        _make_tweet(username="user1", display_name="User One", followers=200, faves=15),
        _make_tweet(username="user2", display_name="User Two", followers=30, faves=2),  # filtered out
    ]

    with patch("x_scraper._scrape_tweets") as mock_scrape:
        mock_scrape.return_value = mock_tweets
        leads = search_x_leads("voice coding")
        assert isinstance(leads, list)
        assert len(leads) == 1
        assert leads[0]["x_username"] == "user1"


def test_search_x_leads_handles_empty():
    with patch("x_scraper._scrape_tweets") as mock_scrape:
        mock_scrape.return_value = []
        leads = search_x_leads("nonexistent_keyword")
        assert leads == []


def test_search_x_leads_handles_error():
    with patch("x_scraper._scrape_tweets") as mock_scrape:
        mock_scrape.side_effect = Exception("API error")
        leads = search_x_leads("voice coding")
        assert leads == []
