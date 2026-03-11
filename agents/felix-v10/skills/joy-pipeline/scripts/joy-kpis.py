#!/usr/bin/env python3
"""Joy Pipeline KPIs -- reads Joy V1 Sales Rep SQLite database for Felix."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# Add project root to path so we can import db.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import db


def get_kpis(db_path=None):
    conn = db.get_connection(db_path)
    kpis = db.get_kpi_counts(conn)
    approval_counts = db.get_approval_counts(db_path)
    kpis["pending_approvals"] = approval_counts["pending"]
    kpis["approved_total"] = approval_counts["approved"]
    kpis["rejected_total"] = approval_counts["rejected"]
    return kpis


def get_pending(db_path=None):
    items = db.get_pending_approvals(db_path)
    return [{"id": i["id"], "name": i["lead_name"], "email": i["lead_email"],
             "tier": i["lead_tier"], "score": i["lead_score"],
             "channel": i["channel"], "created_at": i["created_at"]}
            for i in items]


def get_hot_leads(db_path=None):
    conn = db.get_connection(db_path)
    rows = conn.execute(
        "SELECT id, name, company, email, score, tier, updated_at "
        "FROM leads WHERE status='hot' ORDER BY score DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_stale_leads(db_path=None, days=7):
    conn = db.get_connection(db_path)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT id, name, company, email, status, score, updated_at "
        "FROM leads WHERE updated_at < ? AND status NOT IN ('rejected', 'closed') "
        "ORDER BY updated_at ASC",
        (cutoff,)
    ).fetchall()
    return [dict(r) for r in rows]


def daily_summary(db_path=None):
    return {
        "kpis": get_kpis(db_path),
        "hot_leads": get_hot_leads(db_path),
        "pending_approvals": get_pending(db_path),
        "stale_leads": get_stale_leads(db_path),
        "generated_at": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Joy Pipeline KPIs")
    parser.add_argument("--db", help="Override database path (default: project leads.db)")
    parser.add_argument("--kpis", action="store_true", help="Show KPI snapshot")
    parser.add_argument("--pending", action="store_true", help="Show pending approvals")
    parser.add_argument("--hot-leads", action="store_true", help="Show hot leads")
    parser.add_argument("--stale", action="store_true", help="Show stale leads (7+ days)")
    parser.add_argument("--daily-summary", action="store_true", help="Full daily summary")
    args = parser.parse_args()

    db_path = args.db

    if args.daily_summary:
        print(json.dumps(daily_summary(db_path), indent=2, default=str))
    elif args.kpis:
        print(json.dumps(get_kpis(db_path), indent=2))
    elif args.pending:
        print(json.dumps(get_pending(db_path), indent=2, default=str))
    elif args.hot_leads:
        print(json.dumps(get_hot_leads(db_path), indent=2, default=str))
    elif args.stale:
        print(json.dumps(get_stale_leads(db_path), indent=2, default=str))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
