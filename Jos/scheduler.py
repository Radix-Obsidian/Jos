"""APScheduler cron jobs for Joy V1 Sales Rep.

Runs pipeline scans at optimal posting times for X and LinkedIn (Pacific time).
All scan results are queued to the approval_queue — nothing sends without your review.

Best posting times (research-backed):
  LinkedIn: Tue–Thu 9am, 12pm, 5pm PT
  X/Twitter: Mon–Fri 8am, 7pm PT
"""
from __future__ import annotations

import atexit
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger(__name__)
PACIFIC = pytz.timezone("America/Los_Angeles")


def run_scheduled_scan():
    """Cron entry: run pipeline → results queued for your approval.

    Called by APScheduler on the configured schedule.
    Does NOT send any outreach — all drafts go to approval_queue table.
    """
    import asyncio
    try:
        # Import here to avoid circular imports at module load time
        from web_dashboard import run_pipeline_async
        logger.info("[scheduler] Starting scheduled scan...")
        asyncio.run(run_pipeline_async())
        logger.info("[scheduler] Scheduled scan complete — check Inbox for new drafts.")
    except Exception as e:
        logger.error(f"[scheduler] Scan failed: {e}")


def run_engagement_scan():
    """Search X for ICP posts, draft replies, and queue for approval."""
    try:
        from x_poster import search_icp_posts
        from engagement_drafter import draft_x_reply
        from db import queue_engagement
        from config import ICP_KEYWORDS

        logger.info("[scheduler] Starting engagement scan...")
        posts = search_icp_posts(ICP_KEYWORDS, max_results=10)
        queued = 0
        for post in posts:
            lead = {
                "name": post.get("author_name", ""),
                "x_username": post.get("author_username", ""),
                "company": "",
                "email": "",
            }
            draft = draft_x_reply(lead, post["text"], post["id"])
            queue_engagement(draft)
            queued += 1
        logger.info(f"[scheduler] Engagement scan: queued {queued} drafts from {len(posts)} posts.")
    except Exception as e:
        logger.error(f"[scheduler] Engagement scan failed: {e}")


def collect_engagement_metrics():
    """Daily job: log engagement and source feedback metrics."""
    try:
        from feedback_loop import calculate_source_scores, calculate_engagement_scores, get_recommended_actions
        source_scores = calculate_source_scores()
        eng_scores = calculate_engagement_scores()
        insights = get_recommended_actions()
        logger.info(f"[scheduler] Metrics: sources={source_scores}, engagement={eng_scores}")
        for insight in insights:
            logger.info(f"[scheduler] Insight: {insight}")
    except Exception as e:
        logger.error(f"[scheduler] Metrics collection failed: {e}")


def create_scheduler() -> BackgroundScheduler:
    """Build the APScheduler instance with all cron jobs configured."""
    sched = BackgroundScheduler(timezone=PACIFIC)

    # Best LinkedIn times: Tue–Thu at 9am, noon, 5pm Pacific
    for hour in [9, 12, 17]:
        sched.add_job(
            run_scheduled_scan,
            CronTrigger(day_of_week="tue,wed,thu", hour=hour, minute=0, timezone=PACIFIC),
            id=f"linkedin_{hour}h",
            replace_existing=True,
            name=f"LinkedIn scan {hour:02d}:00 PT (Tue–Thu)",
        )

    # Best X/Twitter times: Mon–Fri at 8am and 7pm Pacific
    for hour in [8, 19]:
        sched.add_job(
            run_scheduled_scan,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=0, timezone=PACIFIC),
            id=f"x_{hour}h",
            replace_existing=True,
            name=f"X scan {hour:02d}:00 PT (Mon–Fri)",
        )

    # Engagement scan: Mon–Fri at 10am, 2pm, 6pm Pacific
    for hour in [10, 14, 18]:
        sched.add_job(
            run_engagement_scan,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=0, timezone=PACIFIC),
            id=f"engage_{hour}h",
            replace_existing=True,
            name=f"Engagement scan {hour:02d}:00 PT (Mon–Fri)",
        )

    # Daily metrics collection: 6am Pacific
    sched.add_job(
        collect_engagement_metrics,
        CronTrigger(hour=6, minute=0, timezone=PACIFIC),
        id="daily_metrics",
        replace_existing=True,
        name="Daily metrics 06:00 PT",
    )

    return sched


def get_next_runs(sched: BackgroundScheduler, n: int = 5) -> list[dict]:
    """Return the next N scheduled run times as dicts for the dashboard.

    Returns:
        List of {id, name, next_run_utc, next_run_pt} dicts, sorted by time
    """
    jobs = sched.get_jobs()
    runs = []
    for job in jobs:
        if job.next_run_time:
            next_pt = job.next_run_time.astimezone(PACIFIC)
            runs.append({
                "id": job.id,
                "name": job.name,
                "next_run_pt": next_pt.strftime("%a %#I:%M %p PT") if os.name == "nt" else next_pt.strftime("%a %-I:%M %p PT"),
                "next_run_iso": next_pt.isoformat(),
            })
    runs.sort(key=lambda x: x["next_run_iso"])
    return runs[:n]


# Singleton — imported and started by web_dashboard.py
scheduler = create_scheduler()
