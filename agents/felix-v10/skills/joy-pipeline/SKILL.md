# Joy Pipeline Skill

Read Joy V1 Sales Rep KPIs from SQLite database.

## Commands

```bash
# Full KPI snapshot
python scripts/joy-kpis.py --kpis

# Pending approvals list
python scripts/joy-kpis.py --pending

# Hot leads list
python scripts/joy-kpis.py --hot-leads

# Stale leads (no update in 7+ days)
python scripts/joy-kpis.py --stale

# Daily summary (all of the above)
python scripts/joy-kpis.py --daily-summary

# Override database path
python scripts/joy-kpis.py --kpis --db /path/to/leads.db
```

## Output
All commands output JSON for easy parsing by Felix.
