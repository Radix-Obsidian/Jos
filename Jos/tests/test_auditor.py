"""Tests for Slice 4: Auditor (KPI tracking + suggestions)."""

import pytest
from agents.auditor import (
    audit_pipeline, generate_suggestions,
    determine_post_audit_status, calculate_batch_kpis,
)
import ledger


@pytest.fixture(autouse=True)
def clear_ledger():
    ledger.clear()
    yield
    ledger.clear()


# --- Audit Pipeline Tests ---

def test_audit_pipeline_returns_dict():
    state = {
        "current_lead": {"name": "Sarah Chen"},
        "lead_tier": "enterprise",
        "lead_status": "cold",
        "lead_score": 0.85,
        "send_result": {"status": "sent", "channel": "email"},
    }
    result = audit_pipeline(state)
    assert isinstance(result, dict)
    assert "kpi_entries" in result
    assert "suggestions" in result
    assert "lead_status" in result


def test_audit_pipeline_tracks_lead():
    state = {
        "current_lead": {"name": "James Wu"},
        "lead_tier": "self_serve",
        "lead_status": "cold",
        "lead_score": 0.55,
        "send_result": {},
    }
    result = audit_pipeline(state)
    assert any("James Wu" in entry for entry in result["kpi_entries"])


def test_audit_pipeline_tracks_outreach():
    state = {
        "current_lead": {"name": "Sarah Chen"},
        "lead_tier": "enterprise",
        "lead_status": "cold",
        "lead_score": 0.85,
        "send_result": {"status": "sent", "channel": "email"},
    }
    result = audit_pipeline(state)
    assert any("OUTREACH" in entry for entry in result["kpi_entries"])


def test_audit_pipeline_tracks_close():
    state = {
        "current_lead": {"name": "Sarah Chen"},
        "lead_tier": "enterprise",
        "lead_status": "hot",
        "lead_score": 0.9,
        "send_result": {"status": "sent"},
        "close_action": "book_demo",
        "close_result": {"status": "booked"},
    }
    result = audit_pipeline(state)
    assert any("CLOSE" in entry for entry in result["kpi_entries"])


# --- Suggestion Tests ---

def test_suggestions_near_threshold():
    suggestion = generate_suggestions("nurture", "cold", 0.38, {})
    assert "threshold" in suggestion.lower()


def test_suggestions_delivery_failed():
    suggestion = generate_suggestions("enterprise", "cold", 0.8, {"status": "failed"})
    assert "alternate channel" in suggestion.lower()


def test_suggestions_cold_qualified():
    suggestion = generate_suggestions("enterprise", "cold", 0.8, {"status": "sent"})
    assert "follow-up" in suggestion.lower()


def test_suggestions_empty_for_hot():
    suggestion = generate_suggestions("enterprise", "hot", 0.9, {"status": "sent"})
    assert suggestion == ""


# --- Post-Audit Status Tests ---

def test_post_audit_status_hot_stays_hot():
    assert determine_post_audit_status("hot", {"status": "sent"}) == "hot"


def test_post_audit_status_responded_stays():
    assert determine_post_audit_status("responded", {}) == "responded"


def test_post_audit_status_cold_after_send():
    assert determine_post_audit_status("cold", {"status": "sent"}) == "cold"


# --- Batch KPI Tests ---

def test_batch_kpis_empty():
    kpis = calculate_batch_kpis([])
    assert kpis["total_processed"] == 0
    assert kpis["delivery_rate"] == 0.0


def test_batch_kpis_mixed():
    states = [
        {"lead_status": "hot", "send_result": {"status": "sent"}, "close_action": "book_demo", "close_result": {"status": "booked"}},
        {"lead_status": "cold", "send_result": {"status": "sent"}, "close_action": "", "close_result": {}},
        {"lead_status": "cold", "send_result": {"status": "failed"}, "close_action": "", "close_result": {}},
    ]
    kpis = calculate_batch_kpis(states)
    assert kpis["total_processed"] == 3
    assert kpis["hot_leads"] == 1
    assert kpis["cold_leads"] == 2
    assert kpis["delivery_rate"] == pytest.approx(2/3, abs=0.01)
    assert kpis["close_rate"] == pytest.approx(1/3, abs=0.01)


def test_batch_kpis_all_hot():
    states = [
        {"lead_status": "hot", "send_result": {"status": "sent"}, "close_action": "book_demo", "close_result": {"status": "booked"}},
        {"lead_status": "hot", "send_result": {"status": "sent"}, "close_action": "payment_link", "close_result": {"status": "sent"}},
    ]
    kpis = calculate_batch_kpis(states)
    assert kpis["hot_leads"] == 2
    assert kpis["close_rate"] == 1.0
