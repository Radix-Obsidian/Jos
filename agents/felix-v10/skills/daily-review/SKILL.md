---
name: daily-review
description: Run a nightly revenue review and plan the next day. Use at the end of each day to summarize performance, identify wins/issues, and propose tomorrow's priorities.
---

# Daily Review — Nightly Deep Dive

Felix runs this at the end of each day (typically ~3 AM via cron) to close out the day and set up tomorrow.

## Process

### 1. Revenue Review
```bash
python3 ~/clawd/skills/revenue-metrics/scripts/stripe-metrics.py --period yesterday
```

⚠️ **CRITICAL:** If running at 3 AM, always use `--period yesterday`. Using `--period today` at 3 AM captures midnight-3am (nearly empty).

Calculate:
- Yesterday's net revenue, per-account breakdown
- Trend vs prior days
- What sold, what didn't, any patterns

### 2. Day Review
- What got done from today's plan?
- What didn't get done and why?
- What worked, what didn't?

### 3. Propose Tomorrow's Plan
- 3-5 concrete actions ranked by expected revenue impact
- Each item should connect clearly to the revenue goal
- Include both execution tasks and growth experiments
- Write to `memory/YYYY-MM-DD.md` (next day's file) under "## Today's Plan"

### 4. Send Summary
Send the user a brief summary with:
- Revenue numbers (yesterday's final)
- Day recap (done vs planned)
- Tomorrow's proposed plan
- Any issues or blockers

## Report Template

```markdown
## Daily Review — YYYY-MM-DD

### Revenue
| Account | Gross | Refunds | Net | Txns | vs Prior |
|---------|-------|---------|-----|------|----------|
| ... | ... | ... | ... | ... | ... |
| **Total** | **$X** | **$X** | **$X** | **N** | **+X%** |

### Execution
- ✅ Completed: [items]
- ❌ Missed: [items + why]
- 🔄 Carried: [items moving to tomorrow]

### Tomorrow's Plan
1. [Highest impact action]
2. [Second priority]
3. [Third priority]

### Notes
[Patterns, insights, experiments to try]
```

## Cron Setup

```json
{
  "name": "nightly-review",
  "schedule": {"kind": "cron", "expr": "0 3 * * *", "tz": "America/Chicago"},
  "sessionTarget": "main",
  "payload": {
    "kind": "systemEvent",
    "text": "Run the nightly deep dive. Pull yesterday's revenue, review today's execution, propose tomorrow's plan."
  }
}
```

Use `main` session so Felix has full context about the day's conversations and decisions.
