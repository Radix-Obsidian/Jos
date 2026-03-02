"""SQLite lead tracking database for Joy V1 Sales Rep."""
from __future__ import annotations

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Get SQLite connection (creates DB + tables if needed)."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT DEFAULT '',
            company TEXT DEFAULT '',
            email TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            score REAL DEFAULT 0.0,
            tier TEXT DEFAULT 'unknown',
            status TEXT DEFAULT 'cold',
            channel TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

    """)

    # Migrate: add new columns if they don't exist yet
    for col, coltype in [
        ("x_username", "TEXT DEFAULT ''"),
        ("x_post_text", "TEXT DEFAULT ''"),
        ("email_confidence", "INTEGER DEFAULT 0"),
        ("source", "TEXT DEFAULT 'manual'"),
        ("sources_json", "TEXT DEFAULT '[]'"),
        ("funding_stage", "TEXT DEFAULT ''"),
        ("funding_amount", "TEXT DEFAULT ''"),
        ("github_url", "TEXT DEFAULT ''"),
        ("producthunt_url", "TEXT DEFAULT ''"),
        ("industry", "TEXT DEFAULT ''"),
        ("company_size", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS approval_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_name TEXT NOT NULL,
            lead_email TEXT DEFAULT '',
            lead_tier TEXT DEFAULT '',
            lead_score REAL DEFAULT 0.0,
            channel TEXT DEFAULT '',
            outreach_draft TEXT NOT NULL,
            follow_up_draft TEXT DEFAULT '',
            closing_script TEXT DEFAULT '',
            approval_status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT DEFAULT '',
            source TEXT DEFAULT 'manual'
        );
    """)

    # Migrate approval_queue: add engagement columns
    for col, coltype in [
        ("action_type", "TEXT DEFAULT 'outreach'"),
        ("target_post_id", "TEXT DEFAULT ''"),
        ("target_post_url", "TEXT DEFAULT ''"),
        ("target_post_text", "TEXT DEFAULT ''"),
        ("platform", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE approval_queue ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS outreach_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            message_type TEXT NOT NULL,
            status TEXT NOT NULL,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS kpi_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_leads INTEGER DEFAULT 0,
            hot_leads INTEGER DEFAULT 0,
            cold_leads INTEGER DEFAULT 0,
            responded INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            demos_booked INTEGER DEFAULT 0,
            payment_links_sent INTEGER DEFAULT 0,
            response_rate REAL DEFAULT 0.0,
            close_rate REAL DEFAULT 0.0,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS domain_cache (
            domain TEXT PRIMARY KEY,
            industry TEXT DEFAULT '',
            employees INTEGER DEFAULT 0,
            cached_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS engagement_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_post_id TEXT DEFAULT '',
            our_post_id TEXT DEFAULT '',
            our_post_text TEXT DEFAULT '',
            lead_name TEXT DEFAULT '',
            lead_email TEXT DEFAULT '',
            status TEXT DEFAULT 'sent',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS source_cache (
            cache_key TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            data TEXT NOT NULL,
            cached_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)


def upsert_lead(conn: sqlite3.Connection, lead: dict, score: float = 0.0,
                 tier: str = "unknown", status: str = "cold") -> int:
    """Insert or update a lead. Returns lead ID.

    Matches existing leads by email (if non-empty) or x_username.
    """
    email = lead.get("email", "")
    x_username = lead.get("x_username", "")

    existing = None
    if email:
        existing = conn.execute(
            "SELECT id FROM leads WHERE email = ? AND email != ''",
            (email,)
        ).fetchone()
    if not existing and x_username:
        existing = conn.execute(
            "SELECT id FROM leads WHERE x_username = ? AND x_username != ''",
            (x_username,)
        ).fetchone()

    now = datetime.now().isoformat()

    if existing:
        conn.execute("""
            UPDATE leads SET name=?, title=?, company=?, email=?, linkedin_url=?,
                score=?, tier=?, status=?, x_username=?, x_post_text=?,
                email_confidence=?, updated_at=?
            WHERE id=?
        """, (
            lead.get("name", ""), lead.get("title", ""),
            lead.get("company", ""), email,
            lead.get("linkedin_url", ""),
            score, tier, status,
            x_username, lead.get("x_post_text", ""),
            lead.get("email_confidence", 0),
            now, existing["id"]
        ))
        conn.commit()
        return existing["id"]

    cursor = conn.execute("""
        INSERT INTO leads (name, title, company, email, linkedin_url,
            score, tier, status, x_username, x_post_text, email_confidence,
            created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead.get("name", ""), lead.get("title", ""),
        lead.get("company", ""), email,
        lead.get("linkedin_url", ""), score, tier, status,
        x_username, lead.get("x_post_text", ""),
        lead.get("email_confidence", 0),
        now, now
    ))
    conn.commit()
    return cursor.lastrowid


def log_outreach(conn: sqlite3.Connection, lead_id: int, channel: str,
                 message_type: str, status: str):
    """Log an outreach action."""
    conn.execute("""
        INSERT INTO outreach_log (lead_id, channel, message_type, status)
        VALUES (?, ?, ?, ?)
    """, (lead_id, channel, message_type, status))
    conn.commit()


def update_lead_status(conn: sqlite3.Connection, lead_id: int, status: str):
    """Update a lead's status (hot/cold/responded)."""
    conn.execute(
        "UPDATE leads SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), lead_id)
    )
    conn.commit()


def get_lead_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    """Fetch lead by email."""
    row = conn.execute("SELECT * FROM leads WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_leads_by_status(conn: sqlite3.Connection, status: str) -> list[dict]:
    """Fetch all leads with given status."""
    rows = conn.execute("SELECT * FROM leads WHERE status = ?", (status,)).fetchall()
    return [dict(r) for r in rows]


def get_kpi_counts(conn: sqlite3.Connection) -> dict:
    """Calculate current KPI counts from the database."""
    leads = conn.execute("SELECT COUNT(*) as total FROM leads").fetchone()
    hot = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status='hot'").fetchone()
    cold = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status='cold'").fetchone()
    responded = conn.execute("SELECT COUNT(*) as c FROM leads WHERE status='responded'").fetchone()
    emails = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE channel='email' AND status='sent'"
    ).fetchone()
    demos = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE message_type='book_demo' AND status='booked'"
    ).fetchone()
    payments = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE message_type='payment_link' AND status='sent'"
    ).fetchone()

    total = leads["total"] or 0
    hot_count = hot["c"] or 0
    responded_count = responded["c"] or 0

    return {
        "total_leads": total,
        "hot_leads": hot_count,
        "cold_leads": cold["c"] or 0,
        "responded": responded_count,
        "emails_sent": emails["c"] or 0,
        "demos_booked": demos["c"] or 0,
        "payment_links_sent": payments["c"] or 0,
        "response_rate": responded_count / total if total > 0 else 0.0,
        "close_rate": (hot_count / total) if total > 0 else 0.0,
    }


def save_kpi_snapshot(conn: sqlite3.Connection, kpis: dict):
    """Save a KPI snapshot to the database."""
    conn.execute("""
        INSERT INTO kpi_snapshots (total_leads, hot_leads, cold_leads, responded,
            emails_sent, demos_booked, payment_links_sent, response_rate, close_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        kpis["total_leads"], kpis["hot_leads"], kpis["cold_leads"],
        kpis["responded"], kpis["emails_sent"], kpis["demos_booked"],
        kpis["payment_links_sent"], kpis["response_rate"], kpis["close_rate"],
    ))
    conn.commit()


# ---------- Approval Queue ----------

def queue_for_approval(item: dict, db_path: str = None) -> int:
    """Add a lead's outreach draft to the approval queue. Returns item ID.

    Deduplicates: if a pending item already exists for this email, skip insert
    and return the existing ID.
    """
    conn = get_connection(db_path)
    email = item.get("lead_email", "")
    if email:
        existing = conn.execute(
            "SELECT id FROM approval_queue WHERE lead_email=? AND approval_status='pending'",
            (email,)
        ).fetchone()
        if existing:
            return existing["id"]

    cursor = conn.execute("""
        INSERT INTO approval_queue
            (lead_name, lead_email, lead_tier, lead_score, channel,
             outreach_draft, follow_up_draft, closing_script, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("lead_name", ""),
        item.get("lead_email", ""),
        item.get("lead_tier", ""),
        item.get("lead_score", 0.0),
        item.get("channel", ""),
        item.get("outreach_draft", ""),
        item.get("follow_up_draft", ""),
        item.get("closing_script", ""),
        item.get("source", "manual"),
    ))
    conn.commit()
    return cursor.lastrowid


def approve_item(item_id: int, db_path: str = None):
    """Mark an approval queue item as approved."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE approval_queue SET approval_status='approved', reviewed_at=? WHERE id=?",
        (datetime.now().isoformat(), item_id)
    )
    conn.commit()


def reject_item(item_id: int, db_path: str = None):
    """Mark an approval queue item as rejected."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE approval_queue SET approval_status='rejected', reviewed_at=? WHERE id=?",
        (datetime.now().isoformat(), item_id)
    )
    conn.commit()


def get_pending_approvals(db_path: str = None) -> list[dict]:
    """Return all pending approval queue items, newest first."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT * FROM approval_queue
        WHERE approval_status = 'pending'
        ORDER BY created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_approval_counts(db_path: str = None) -> dict:
    """Return counts of pending/approved/rejected items."""
    conn = get_connection(db_path)
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN approval_status='pending'  THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN approval_status='approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN approval_status='rejected' THEN 1 ELSE 0 END) as rejected
        FROM approval_queue
    """).fetchone()
    return {
        "pending":  row["pending"]  or 0,
        "approved": row["approved"] or 0,
        "rejected": row["rejected"] or 0,
    }


# ---------- Domain Cache ----------

def get_domain_cache(domain: str, db_path: str = None) -> dict | None:
    """Return cached Hunter domain enrichment data, or None if not cached."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT industry, employees FROM domain_cache WHERE domain = ?", (domain,)
    ).fetchone()
    return {"industry": row["industry"], "employees": row["employees"]} if row else None


def set_domain_cache(domain: str, industry: str, employees: int,
                     db_path: str = None):
    """Persist domain enrichment data so Hunter is only called once per domain."""
    conn = get_connection(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO domain_cache (domain, industry, employees, cached_at)
        VALUES (?, ?, ?, ?)
    """, (domain, industry, employees, datetime.now().isoformat()))
    conn.commit()


# ---------- Engagement ----------

def queue_engagement(item: dict, db_path: str = None) -> int:
    """Queue an engagement action (X reply, tweet, LinkedIn post, etc.) for approval.

    Uses the same approval_queue table but with action_type and target fields set.
    Deduplicates by target_post_id + action_type to avoid double-replying.
    """
    conn = get_connection(db_path)
    target_id = item.get("target_post_id", "")
    action_type = item.get("action_type", "")

    if target_id and action_type:
        existing = conn.execute(
            "SELECT id FROM approval_queue WHERE target_post_id=? AND action_type=? AND approval_status='pending'",
            (target_id, action_type)
        ).fetchone()
        if existing:
            return existing["id"]

    cursor = conn.execute("""
        INSERT INTO approval_queue
            (lead_name, lead_email, lead_tier, lead_score, channel,
             outreach_draft, follow_up_draft, closing_script, source,
             action_type, target_post_id, target_post_url, target_post_text, platform)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("lead_name", ""),
        item.get("lead_email", ""),
        item.get("lead_tier", ""),
        item.get("lead_score", 0.0),
        item.get("channel", ""),
        item.get("outreach_draft", ""),
        item.get("follow_up_draft", ""),
        item.get("closing_script", ""),
        item.get("source", "engagement"),
        item.get("action_type", ""),
        item.get("target_post_id", ""),
        item.get("target_post_url", ""),
        item.get("target_post_text", ""),
        item.get("platform", ""),
    ))
    conn.commit()
    return cursor.lastrowid


def log_engagement(platform: str, action_type: str, target_post_id: str,
                   our_post_id: str, our_post_text: str, lead_name: str,
                   status: str, db_path: str = None):
    """Record an executed engagement action."""
    conn = get_connection(db_path)
    conn.execute("""
        INSERT INTO engagement_log
            (platform, action_type, target_post_id, our_post_id,
             our_post_text, lead_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (platform, action_type, target_post_id, our_post_id,
          our_post_text, lead_name, status))
    conn.commit()


def get_engagement_stats(db_path: str = None) -> dict:
    """Aggregate engagement stats by platform and action type."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT platform, action_type, status, COUNT(*) as cnt
        FROM engagement_log
        GROUP BY platform, action_type, status
    """).fetchall()
    stats = {}
    for r in rows:
        key = f"{r['platform']}_{r['action_type']}"
        if key not in stats:
            stats[key] = {"total": 0, "sent": 0, "failed": 0}
        stats[key]["total"] += r["cnt"]
        stats[key][r["status"]] = stats[key].get(r["status"], 0) + r["cnt"]
    return stats


def get_pending_engagements(db_path: str = None) -> list[dict]:
    """Return pending engagement items (action_type != 'outreach')."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT * FROM approval_queue
        WHERE approval_status = 'pending' AND action_type != 'outreach'
        ORDER BY created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


# ---------- Source Cache ----------

def get_source_cache(cache_key: str, db_path: str = None) -> dict | None:
    """Return cached source data as parsed JSON, or None if not cached."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT data FROM source_cache WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    if row:
        return json.loads(row["data"])
    return None


def set_source_cache(cache_key: str, source: str, data: dict,
                     db_path: str = None):
    """Persist source API response data for future lookups."""
    conn = get_connection(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO source_cache (cache_key, source, data, cached_at)
        VALUES (?, ?, ?, ?)
    """, (cache_key, source, json.dumps(data), datetime.now().isoformat()))
    conn.commit()
