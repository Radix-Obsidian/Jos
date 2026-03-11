# HEARTBEAT.md

Felix runs through this checklist on every heartbeat. Customized for Voco/Proof Inc.

## Execution Check (every heartbeat)
1. Read today's plan from `memory/YYYY-MM-DD.md` under "## Today's Plan"
2. Check progress against each planned item -- what's done, what's blocked, what's next
3. If something is blocked, unblock it or escalate to the user
4. If ahead of plan, pull the next priority forward
5. Log progress updates to daily notes

## Site Health Check (every heartbeat)
Check that production sites return 200:

```bash
curl -s -o /dev/null -w "%{http_code}" https://itsvoco.com
curl -s -o /dev/null -w "%{http_code}" https://complybyproof.com
curl -s -o /dev/null -w "%{http_code}" https://www.viperbyproof.com
```

If any site is down, alert the user immediately.

## Joy Pipeline Check (every heartbeat)
```bash
python agents/felix-v10/skills/joy-pipeline/scripts/joy-kpis.py --kpis
```
- Flag if hot leads count drops
- Flag if pending approvals > 10
- Flag stale leads (no update in 7+ days)

## Long-Running Process Check (every heartbeat)
1. Read daily notes for any listed active background processes
2. For each listed process: `tasklist | findstr <process_name>`
3. If alive: check recent output/logs
4. If dead: restart it via `Start-Process`
5. If stalled (same output for 2+ heartbeats): kill and restart
6. If finished: report completion and remove from daily notes

## Fact Extraction (every heartbeat)
1. Check for new conversations since last extraction
2. Extract durable facts to relevant entities in `~/life/`
3. Update `memory/YYYY-MM-DD.md` with timeline entries

## Nightly Deep Dive (~3 AM -- run once per day)
1. **Revenue review:** Pull metrics for yesterday (never "today" at 3 AM -- that's empty)
2. **Joy pipeline summary:** Lead counts, conversion rates, pending approvals
3. **Day review:** What got done? What didn't? Why?
4. **Propose tomorrow's plan:** 3-5 concrete actions ranked by expected revenue impact
5. **Send summary** -- revenue numbers, day recap, proposed plan
