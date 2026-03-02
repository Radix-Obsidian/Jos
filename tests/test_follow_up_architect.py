"""Tests for Slice 2: Follow-Up Architect (tracking + timed follow-ups)."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from agents.follow_up_architect import (
    send_message, send_email, send_linkedin,
    schedule_follow_up, advance_follow_up, get_due_follow_ups,
    generate_follow_up_message, architect_follow_up,
)
from config import FOLLOW_UP_DAYS
import ledger


LEAD = {
    "name": "Sarah Chen",
    "title": "CTO",
    "company": "DataFlow AI",
    "email": "sarah@dataflow.ai",
    "linkedin_url": "https://linkedin.com/in/sarahchen",
}

EMAIL_MSG = {"subject": "Test Subject", "body": "Test body content"}
LINKEDIN_MSG = {"body": "Hey Sarah, quick note..."}


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


# --- Message Sending Tests ---

def test_send_email_returns_result():
    with patch("agents.follow_up_architect.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = send_email(LEAD, EMAIL_MSG)
        assert result["status"] == "sent"
        assert result["channel"] == "email"


def test_send_email_failure():
    with patch("agents.follow_up_architect.smtplib.SMTP") as mock_smtp:
        mock_smtp.side_effect = Exception("SMTP failed")
        result = send_email(LEAD, EMAIL_MSG)
        assert result["status"] == "failed"


def test_send_linkedin_queued():
    result = send_linkedin(LEAD, LINKEDIN_MSG)
    assert result["status"] in ("queued", "sent")
    assert result["channel"] == "linkedin"


def test_send_message_routes_email():
    with patch("agents.follow_up_architect.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = send_message(LEAD, EMAIL_MSG, channel="email")
        assert result["channel"] == "email"


def test_send_message_routes_linkedin():
    result = send_message(LEAD, LINKEDIN_MSG, channel="linkedin")
    assert result["channel"] == "linkedin"


# --- Follow-Up Scheduling Tests ---

def test_schedule_follow_up_returns_entry():
    entry = schedule_follow_up(LEAD, tier="enterprise")
    assert isinstance(entry, dict)
    assert entry["step"] == 1
    assert "due_date" in entry


def test_schedule_follow_up_first_due_date():
    entry = schedule_follow_up(LEAD, tier="enterprise")
    expected = datetime.now() + timedelta(days=FOLLOW_UP_DAYS[0])
    assert abs((entry["due_date"] - expected).total_seconds()) < 2


def test_advance_follow_up_increments_step():
    entry = schedule_follow_up(LEAD, tier="enterprise")
    advanced = advance_follow_up(entry)
    assert advanced["step"] == 2


def test_advance_follow_up_step_3_is_final():
    entry = {"lead": LEAD, "step": 3, "tier": "enterprise", "due_date": datetime.now()}
    advanced = advance_follow_up(entry)
    assert advanced is None


def test_get_due_follow_ups_filters_by_date():
    past = datetime.now() - timedelta(days=1)
    future = datetime.now() + timedelta(days=5)
    queue = [
        {"lead": LEAD, "step": 1, "tier": "enterprise", "due_date": past},
        {"lead": LEAD, "step": 2, "tier": "enterprise", "due_date": future},
    ]
    due = get_due_follow_ups(queue)
    assert len(due) == 1
    assert due[0]["step"] == 1


# --- Follow-Up Message Tests ---

def test_generate_follow_up_message_step_1():
    msg = generate_follow_up_message(LEAD, step=1, tier="enterprise")
    assert "subject" in msg
    assert "body" in msg
    assert "Sarah" in msg["body"]


def test_generate_follow_up_message_step_2():
    msg1 = generate_follow_up_message(LEAD, step=1, tier="enterprise")
    msg2 = generate_follow_up_message(LEAD, step=2, tier="enterprise")
    assert msg1["subject"] != msg2["subject"]


def test_generate_follow_up_message_step_3_final():
    msg = generate_follow_up_message(LEAD, step=3, tier="enterprise")
    body_lower = msg["body"].lower()
    assert "last" in body_lower or "final" in body_lower or "closing" in body_lower


def test_three_touch_sequence_unique_subjects():
    """Three-touch follow-up generates different messages."""
    msgs = []
    for step in range(1, 4):
        msg = generate_follow_up_message(LEAD, step=step, tier="self_serve")
        msgs.append(msg)
        assert "Sarah" in msg["body"]
    subjects = [m["subject"] for m in msgs]
    assert len(set(subjects)) == 3


# --- Full Architect Pipeline ---

def test_architect_follow_up_returns_result():
    result = architect_follow_up(LEAD, tier="enterprise", step=1)
    assert "entry" in result
    assert "message" in result
    assert "follow_up_text" in result
    assert result["follow_up_text"] != ""
