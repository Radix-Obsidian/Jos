"""Tests for x_poster.py — X/Twitter engagement via tweepy."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------- Setup: inject a fake tweepy into sys.modules ----------

@pytest.fixture(autouse=True)
def _mock_tweepy_module(monkeypatch):
    """Inject a mock tweepy module so x_poster imports successfully."""
    monkeypatch.setenv("X_API_KEY", "test-key")
    monkeypatch.setenv("X_API_SECRET", "test-secret")
    monkeypatch.setenv("X_ACCESS_TOKEN", "test-access")
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "test-access-secret")
    monkeypatch.setenv("X_BEARER_TOKEN", "test-bearer")

    fake_tweepy = MagicMock()
    monkeypatch.setitem(sys.modules, "tweepy", fake_tweepy)

    # Force reimport so x_poster picks up the fake tweepy
    if "x_poster" in sys.modules:
        importlib.reload(sys.modules["x_poster"])

    yield fake_tweepy

    # Cleanup: remove the injected module
    sys.modules.pop("tweepy", None)


@pytest.fixture()
def xp(_mock_tweepy_module):
    """Return a freshly-imported x_poster with mock tweepy wired in."""
    fake_tweepy = _mock_tweepy_module
    mock_client = MagicMock()
    fake_tweepy.Client.return_value = mock_client

    import x_poster
    x_poster.HAS_TWEEPY = True
    x_poster.X_API_KEY = "test-key"
    x_poster.X_API_SECRET = "test-secret"
    x_poster.X_ACCESS_TOKEN = "test-access"
    x_poster.X_ACCESS_TOKEN_SECRET = "test-access-secret"
    x_poster.X_BEARER_TOKEN = "test-bearer"

    return x_poster, mock_client


# ---------- get_client ----------

def test_get_client_returns_none_when_tweepy_missing():
    import x_poster
    x_poster.HAS_TWEEPY = False
    result = x_poster.get_client()
    assert result is None


def test_get_client_returns_none_when_keys_missing():
    import x_poster
    x_poster.HAS_TWEEPY = True
    x_poster.X_API_KEY = ""
    result = x_poster.get_client()
    assert result is None


def test_get_client_returns_client(xp):
    mod, mock_client = xp
    client = mod.get_client()
    assert client is mock_client


# ---------- post_tweet ----------

def test_post_tweet_success(xp):
    mod, mock_client = xp
    mock_client.create_tweet.return_value = MagicMock(data={"id": "123456"})
    result = mod.post_tweet("Hello world")
    assert result["status"] == "sent"
    assert result["tweet_id"] == "123456"
    assert result["error"] == ""


def test_post_tweet_failure(xp):
    mod, mock_client = xp
    mock_client.create_tweet.side_effect = Exception("Rate limited")
    result = mod.post_tweet("Hello world")
    assert result["status"] == "failed"
    assert "Rate limited" in result["error"]


def test_post_tweet_no_client():
    import x_poster
    x_poster.HAS_TWEEPY = False
    result = x_poster.post_tweet("Hello")
    assert result["status"] == "error"
    assert "not configured" in result["error"]


# ---------- reply_to_tweet ----------

def test_reply_to_tweet_success(xp):
    mod, mock_client = xp
    mock_client.create_tweet.return_value = MagicMock(data={"id": "789"})
    result = mod.reply_to_tweet("111", "Nice post!")
    assert result["status"] == "sent"
    assert result["reply_id"] == "789"
    mock_client.create_tweet.assert_called_once_with(text="Nice post!", in_reply_to_tweet_id="111")


def test_reply_to_tweet_failure(xp):
    mod, mock_client = xp
    mock_client.create_tweet.side_effect = Exception("Forbidden")
    result = mod.reply_to_tweet("111", "Nice post!")
    assert result["status"] == "failed"
    assert "Forbidden" in result["error"]


def test_reply_no_client():
    import x_poster
    x_poster.HAS_TWEEPY = False
    result = x_poster.reply_to_tweet("111", "hi")
    assert result["status"] == "error"


# ---------- like_tweet ----------

def test_like_tweet_success(xp):
    mod, mock_client = xp
    result = mod.like_tweet("555")
    assert result["status"] == "sent"
    mock_client.like.assert_called_once_with("555")


def test_like_tweet_failure(xp):
    mod, mock_client = xp
    mock_client.like.side_effect = Exception("Not found")
    result = mod.like_tweet("555")
    assert result["status"] == "failed"


def test_like_no_client():
    import x_poster
    x_poster.HAS_TWEEPY = False
    result = x_poster.like_tweet("555")
    assert result["status"] == "error"


# ---------- quote_tweet ----------

def test_quote_tweet_success(xp):
    mod, mock_client = xp
    mock_client.create_tweet.return_value = MagicMock(data={"id": "999"})
    result = mod.quote_tweet("444", "Great thread")
    assert result["status"] == "sent"
    assert result["tweet_id"] == "999"


def test_quote_tweet_failure(xp):
    mod, mock_client = xp
    mock_client.create_tweet.side_effect = Exception("Duplicate")
    result = mod.quote_tweet("444", "Great thread")
    assert result["status"] == "failed"


# ---------- search_icp_posts ----------

def test_search_icp_posts_success(xp):
    mod, mock_client = xp

    mock_tweet = MagicMock()
    mock_tweet.id = 12345
    mock_tweet.text = "Voice AI is the future"
    mock_tweet.author_id = 100
    mock_tweet.public_metrics = {"like_count": 10, "reply_count": 2}

    mock_user = MagicMock()
    mock_user.id = 100
    mock_user.name = "Jane Doe"
    mock_user.username = "janedoe"
    mock_user.description = "CTO at VoiceCo"

    mock_resp = MagicMock()
    mock_resp.data = [mock_tweet]
    mock_resp.includes = {"users": [mock_user]}

    mock_client.search_recent_tweets.return_value = mock_resp

    results = mod.search_icp_posts(["voice AI"])
    assert len(results) == 1
    assert results[0]["author_name"] == "Jane Doe"
    assert results[0]["likes"] == 10


def test_search_icp_posts_empty(xp):
    mod, mock_client = xp
    mock_resp = MagicMock()
    mock_resp.data = None
    mock_client.search_recent_tweets.return_value = mock_resp

    results = mod.search_icp_posts(["voice AI"])
    assert results == []


def test_search_icp_posts_no_client():
    import x_poster
    x_poster.HAS_TWEEPY = False
    results = x_poster.search_icp_posts(["voice AI"])
    assert results == []


def test_search_icp_posts_exception(xp):
    mod, mock_client = xp
    mock_client.search_recent_tweets.side_effect = Exception("Timeout")
    results = mod.search_icp_posts(["voice AI"])
    assert results == []
