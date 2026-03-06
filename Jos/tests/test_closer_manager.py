"""Tests for Slice 3: Closer Manager (hot-lead detection + closing scripts + deals)."""

import pytest
from unittest.mock import patch, MagicMock
from agents.closer_manager import (
    close_deal, book_demo, send_payment_link,
    decide_close_action, is_hot_lead, generate_closing_script,
)
import ledger


ENTERPRISE_LEAD = {
    "name": "Sarah Chen",
    "title": "CTO",
    "company": "DataFlow AI",
    "email": "sarah@dataflow.ai",
}

SELF_SERVE_LEAD = {
    "name": "Mike Johnson",
    "title": "Senior Dev",
    "company": "SmallSaaS",
    "email": "mike@smallsaas.com",
}


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


# --- Decision Tests ---

def test_decide_close_action_enterprise():
    assert decide_close_action("enterprise") == "book_demo"


def test_decide_close_action_self_serve():
    assert decide_close_action("self_serve") == "payment_link"


def test_decide_close_action_nurture():
    assert decide_close_action("nurture") == "none"


# --- Hot Lead Detection ---

def test_is_hot_lead_by_status():
    """Lead with status 'hot' is hot."""
    assert is_hot_lead(ENTERPRISE_LEAD, 0.5, "hot") is True


def test_is_hot_lead_by_responded():
    """Lead with status 'responded' is hot."""
    assert is_hot_lead(ENTERPRISE_LEAD, 0.5, "responded") is True


def test_is_hot_lead_by_score():
    """Lead with score >= 0.8 is hot."""
    assert is_hot_lead(ENTERPRISE_LEAD, 0.85, "cold") is True


def test_is_not_hot_lead():
    """Low score cold lead is not hot."""
    assert is_hot_lead(SELF_SERVE_LEAD, 0.4, "cold") is False


# --- Closing Script Tests ---

def test_closing_script_enterprise():
    script = generate_closing_script(ENTERPRISE_LEAD, "enterprise", "book_demo")
    assert "Sarah" in script
    assert "demo" in script.lower() or "calendly" in script.lower()


def test_closing_script_self_serve():
    script = generate_closing_script(SELF_SERVE_LEAD, "self_serve", "payment_link")
    assert "Mike" in script
    assert "stripe" in script.lower() or "get started" in script.lower()


def test_closing_script_none():
    script = generate_closing_script(SELF_SERVE_LEAD, "nurture", "none")
    assert script == ""


# --- Book Demo Tests ---

def test_book_demo_returns_result():
    """book_demo generates a pre-filled Calendly link (no API call)."""
    result = book_demo(ENTERPRISE_LEAD)
    assert result["status"] == "link_generated"
    assert "name=Sarah" in result["url"]
    assert "email=sarah" in result["url"]
    assert "calendly" in result["url"].lower()


def test_book_demo_with_missing_fields():
    """book_demo handles leads with missing optional fields."""
    lead = {"name": "Test", "email": ""}
    result = book_demo(lead)
    assert result["status"] == "link_generated"
    assert "name=Test" in result["url"]


# --- Payment Link Tests ---

def test_send_payment_link():
    result = send_payment_link(SELF_SERVE_LEAD)
    assert result["status"] == "sent"
    assert "url" in result


# --- Close Deal Tests ---

def test_close_deal_enterprise():
    result = close_deal(ENTERPRISE_LEAD, tier="enterprise")
    assert result["action"] == "book_demo"
    assert result["status"] == "link_generated"
    assert "closing_script" in result
    assert "calendly" in result["url"].lower()


def test_close_deal_self_serve():
    result = close_deal(SELF_SERVE_LEAD, tier="self_serve")
    assert result["action"] == "payment_link"
    assert result["status"] == "sent"
    assert "closing_script" in result


def test_close_deal_nurture_skips():
    result = close_deal(SELF_SERVE_LEAD, tier="nurture")
    assert result["action"] == "none"
