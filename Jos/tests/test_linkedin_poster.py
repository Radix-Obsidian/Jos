"""Tests for linkedin_poster.py — LinkedIn engagement via unofficial API."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------- Setup: inject fake linkedin_api ----------

@pytest.fixture(autouse=True)
def _mock_linkedin_module(monkeypatch):
    """Inject a mock linkedin_api module so linkedin_poster imports successfully."""
    monkeypatch.setenv("LINKEDIN_EMAIL", "test@example.com")
    monkeypatch.setenv("LINKEDIN_PASSWORD", "testpass")

    fake_linkedin_api = MagicMock()
    monkeypatch.setitem(sys.modules, "linkedin_api", fake_linkedin_api)

    # Force reimport
    if "linkedin_poster" in sys.modules:
        importlib.reload(sys.modules["linkedin_poster"])

    yield fake_linkedin_api

    sys.modules.pop("linkedin_api", None)


@pytest.fixture()
def lp(_mock_linkedin_module):
    """Return a freshly-configured linkedin_poster module + mock client."""
    fake_linkedin_api = _mock_linkedin_module
    mock_client = MagicMock()
    fake_linkedin_api.Linkedin.return_value = mock_client

    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = True
    linkedin_poster.LI_EMAIL = "test@example.com"
    linkedin_poster.LI_PASSWORD = "testpass"
    linkedin_poster._client = None  # reset singleton

    return linkedin_poster, mock_client


# ---------- get_client ----------

def test_get_client_none_when_lib_missing():
    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = False
    linkedin_poster._client = None
    result = linkedin_poster.get_client()
    assert result is None


def test_get_client_none_when_creds_missing():
    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = True
    linkedin_poster.LI_EMAIL = ""
    linkedin_poster._client = None
    result = linkedin_poster.get_client()
    assert result is None


def test_get_client_returns_client(lp):
    mod, mock_client = lp
    client = mod.get_client()
    assert client is mock_client


def test_get_client_singleton(lp):
    mod, mock_client = lp
    c1 = mod.get_client()
    c2 = mod.get_client()
    assert c1 is c2


def test_get_client_auth_failure(_mock_linkedin_module):
    fake_api = _mock_linkedin_module
    fake_api.Linkedin.side_effect = Exception("Bad creds")

    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = True
    linkedin_poster.LI_EMAIL = "test@example.com"
    linkedin_poster.LI_PASSWORD = "testpass"
    linkedin_poster._client = None
    result = linkedin_poster.get_client()
    assert result is None


# ---------- post_update ----------

def test_post_update_success(lp):
    mod, mock_client = lp
    mock_client.post.return_value = "urn:li:share:12345"
    result = mod.post_update("Hello LinkedIn!")
    assert result["status"] == "sent"
    assert result["post_urn"] == "urn:li:share:12345"


def test_post_update_failure(lp):
    mod, mock_client = lp
    mock_client.post.side_effect = Exception("Rate limited")
    result = mod.post_update("Hello")
    assert result["status"] == "failed"
    assert "Rate limited" in result["error"]


def test_post_update_no_client():
    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = False
    linkedin_poster._client = None
    result = linkedin_poster.post_update("Hello")
    assert result["status"] == "error"


# ---------- comment_on_post ----------

def test_comment_success(lp):
    mod, mock_client = lp
    mock_client.comment.return_value = "urn:li:comment:999"
    result = mod.comment_on_post("urn:li:share:123", "Great post!")
    assert result["status"] == "sent"
    assert result["comment_urn"] == "urn:li:comment:999"


def test_comment_failure(lp):
    mod, mock_client = lp
    mock_client.comment.side_effect = Exception("Forbidden")
    result = mod.comment_on_post("urn:li:share:123", "Great post!")
    assert result["status"] == "failed"


# ---------- send_connection_request ----------

def test_connection_request_success(lp):
    mod, mock_client = lp
    result = mod.send_connection_request("john-doe-123", "Hi John!")
    assert result["status"] == "sent"
    mock_client.add_connection.assert_called_once_with("john-doe-123", message="Hi John!")


def test_connection_request_failure(lp):
    mod, mock_client = lp
    mock_client.add_connection.side_effect = Exception("Not found")
    result = mod.send_connection_request("unknown-123")
    assert result["status"] == "failed"


# ---------- get_profile ----------

def test_get_profile_success(lp):
    mod, mock_client = lp
    mock_client.get_profile.return_value = {"firstName": "John", "lastName": "Doe"}
    result = mod.get_profile("john-doe-123")
    assert result["firstName"] == "John"


def test_get_profile_no_client():
    import linkedin_poster
    linkedin_poster.HAS_LINKEDIN = False
    linkedin_poster._client = None
    result = linkedin_poster.get_profile("john-doe-123")
    assert result == {}


def test_get_profile_failure(lp):
    mod, mock_client = lp
    mock_client.get_profile.side_effect = Exception("Error")
    result = mod.get_profile("john-doe-123")
    assert result == {}
