"""Pytest config and shared fixtures."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# --- Shared Test Leads ---
ENTERPRISE_LEAD = {"name": "Sarah Chen", "title": "CTO", "company": "DataFlow AI", "email": "sarah@dataflow.ai", "linkedin_url": "https://linkedin.com/in/sarahchen"}
SELF_SERVE_LEAD = {"name": "David Kim", "title": "Engineering Manager", "company": "TechCorp", "email": "david@techcorp.com", "linkedin_url": ""}
NURTURE_LEAD = {"name": "Emily Park", "title": "Founder", "company": "AI Startup", "email": "emily@aistartup.com", "linkedin_url": ""}
DISQUALIFIED_LEAD = {"name": "Mike Intern", "title": "Marketing Intern", "company": "RandomCo", "email": "mike@random.com", "linkedin_url": ""}


@pytest.fixture
def enterprise_lead():
    return ENTERPRISE_LEAD.copy()

@pytest.fixture
def self_serve_lead():
    return SELF_SERVE_LEAD.copy()

@pytest.fixture
def nurture_lead():
    return NURTURE_LEAD.copy()

@pytest.fixture
def disqualified_lead():
    return DISQUALIFIED_LEAD.copy()


@pytest.fixture(autouse=True)
def mock_llm_loading():
    """Prevent MLX model loading in all tests."""
    from unittest.mock import patch
    with patch("llm._load_model", return_value=(None, None)):
        yield


@pytest.fixture(autouse=True)
def clear_ledger_fixture():
    """Clear ledger before/after each test."""
    import ledger
    ledger.clear()
    yield
    ledger.clear()
