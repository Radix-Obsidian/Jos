"""Tests for SQLite lead tracking database."""

import pytest
import os
import tempfile
from db import (
    get_connection, upsert_lead, log_outreach,
    update_lead_status, get_lead_by_email, get_leads_by_status,
    get_kpi_counts, save_kpi_snapshot,
    get_domain_cache, set_domain_cache,
)


@pytest.fixture
def db_conn():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = get_connection(path)
    yield conn
    conn.close()
    os.unlink(path)


LEAD = {
    "name": "Sarah Chen",
    "title": "CTO",
    "company": "DataFlow AI",
    "email": "sarah@dataflow.ai",
    "linkedin_url": "https://linkedin.com/in/sarahchen",
}


def test_upsert_lead_creates(db_conn):
    lead_id = upsert_lead(db_conn, LEAD, score=0.85, tier="enterprise", status="cold")
    assert lead_id > 0


def test_upsert_lead_updates_existing(db_conn):
    id1 = upsert_lead(db_conn, LEAD, score=0.85, tier="enterprise", status="cold")
    id2 = upsert_lead(db_conn, LEAD, score=0.9, tier="enterprise", status="hot")
    assert id1 == id2  # Same lead, same ID


def test_get_lead_by_email(db_conn):
    upsert_lead(db_conn, LEAD, score=0.85, tier="enterprise")
    found = get_lead_by_email(db_conn, "sarah@dataflow.ai")
    assert found is not None
    assert found["name"] == "Sarah Chen"


def test_get_lead_by_email_not_found(db_conn):
    found = get_lead_by_email(db_conn, "nobody@nowhere.com")
    assert found is None


def test_update_lead_status(db_conn):
    lead_id = upsert_lead(db_conn, LEAD, status="cold")
    update_lead_status(db_conn, lead_id, "hot")
    found = get_lead_by_email(db_conn, LEAD["email"])
    assert found["status"] == "hot"


def test_get_leads_by_status(db_conn):
    upsert_lead(db_conn, LEAD, status="cold")
    upsert_lead(db_conn, {"name": "James", "email": "james@co.com"}, status="hot")
    cold = get_leads_by_status(db_conn, "cold")
    hot = get_leads_by_status(db_conn, "hot")
    assert len(cold) == 1
    assert len(hot) == 1


def test_log_outreach(db_conn):
    lead_id = upsert_lead(db_conn, LEAD)
    log_outreach(db_conn, lead_id, "email", "initial", "sent")
    rows = db_conn.execute("SELECT * FROM outreach_log WHERE lead_id = ?", (lead_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["channel"] == "email"


def test_kpi_counts_empty(db_conn):
    kpis = get_kpi_counts(db_conn)
    assert kpis["total_leads"] == 0
    assert kpis["response_rate"] == 0.0


def test_kpi_counts_with_data(db_conn):
    id1 = upsert_lead(db_conn, LEAD, status="hot")
    id2 = upsert_lead(db_conn, {"name": "James", "email": "j@co.com"}, status="cold")
    log_outreach(db_conn, id1, "email", "initial", "sent")
    log_outreach(db_conn, id1, "email", "book_demo", "booked")

    kpis = get_kpi_counts(db_conn)
    assert kpis["total_leads"] == 2
    assert kpis["hot_leads"] == 1
    assert kpis["emails_sent"] == 1
    assert kpis["demos_booked"] == 1


X_LEAD = {
    "name": "Kyle Vedder",
    "title": "CEO",
    "company": "Voiceflow",
    "email": "",
    "linkedin_url": "",
    "x_username": "KyleVedder",
    "x_post_text": "Cursor is great but voice coding would be next level",
    "email_confidence": 0,
}


def test_upsert_x_lead_creates(db_conn):
    """X-sourced lead with no email creates via x_username."""
    lead_id = upsert_lead(db_conn, X_LEAD, score=0.6, tier="self_serve", status="cold")
    assert lead_id > 0
    row = db_conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    assert row["x_username"] == "KyleVedder"
    assert row["x_post_text"] == "Cursor is great but voice coding would be next level"


def test_upsert_x_lead_dedupes_by_username(db_conn):
    """Updating the same x_username returns the same lead ID."""
    id1 = upsert_lead(db_conn, X_LEAD, score=0.6, tier="self_serve", status="cold")
    updated = dict(X_LEAD, email="kyle@voiceflow.com", email_confidence=95)
    id2 = upsert_lead(db_conn, updated, score=0.75, tier="enterprise", status="hot")
    assert id1 == id2
    row = db_conn.execute("SELECT * FROM leads WHERE id = ?", (id1,)).fetchone()
    assert row["email"] == "kyle@voiceflow.com"
    assert row["email_confidence"] == 95


def test_save_kpi_snapshot(db_conn):
    kpis = {
        "total_leads": 5, "hot_leads": 2, "cold_leads": 2,
        "responded": 1, "emails_sent": 4, "demos_booked": 1,
        "payment_links_sent": 1, "response_rate": 0.2, "close_rate": 0.4,
    }
    save_kpi_snapshot(db_conn, kpis)
    rows = db_conn.execute("SELECT * FROM kpi_snapshots").fetchall()
    assert len(rows) == 1
    assert rows[0]["total_leads"] == 5


# --- Domain Cache ---

def test_domain_cache_miss_returns_none():
    """get_domain_cache returns None for an unseen domain."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    result = get_domain_cache("notcached.com", db_path=path)
    os.unlink(path)
    assert result is None


def test_domain_cache_get_set_roundtrip():
    """set_domain_cache persists data that get_domain_cache retrieves."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_domain_cache("railway.app", "cloud infrastructure", 45, db_path=path)
    result = get_domain_cache("railway.app", db_path=path)
    os.unlink(path)
    assert result is not None
    assert result["industry"] == "cloud infrastructure"
    assert result["employees"] == 45


def test_domain_cache_upsert_replaces():
    """Calling set_domain_cache again for same domain updates the record."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_domain_cache("update.io", "saas", 50, db_path=path)
    set_domain_cache("update.io", "developer tools", 120, db_path=path)
    result = get_domain_cache("update.io", db_path=path)
    os.unlink(path)
    assert result["industry"] == "developer tools"
    assert result["employees"] == 120
