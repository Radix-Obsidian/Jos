"""Joy V1 Sales Rep — Web Dashboard (Production).

Features:
- Pipeline result caching (no reprocessing on every page load)
- Bearer token auth on API routes via DASHBOARD_API_KEY
- Approve → actually sends email / queues LinkedIn DM
- Approve engagement → dispatches via x_poster / linkedin_poster
- KPI snapshots persisted to DB after each pipeline run
- Simple in-memory rate limiter on API endpoints
- Full graph invoke on /api/discover (not just hunt)
"""
from __future__ import annotations

import atexit
import asyncio
import functools
import json
import logging
import time
import threading
from collections import defaultdict
from datetime import datetime

from flask import Flask, render_template_string, request, jsonify, abort

from agents.outreach_hunter import hunt
from agents.follow_up_architect import (
    architect_follow_up, send_message, generate_follow_up_message,
)
from agents.closer_manager import close_deal, is_hot_lead
from agents.auditor import audit_pipeline, calculate_batch_kpis
from db import (
    get_connection, upsert_lead, log_outreach, save_kpi_snapshot, get_kpi_counts,
    queue_for_approval, approve_item, reject_item,
    get_pending_approvals, get_approval_counts,
    queue_engagement, get_pending_engagements, get_engagement_stats,
    log_engagement,
)
from config import DASHBOARD_API_KEY
from scheduler import scheduler, get_next_runs
import ledger

logger = logging.getLogger("joy.dashboard")

app = Flask(__name__)

# ---------- Scheduler (background thread) ----------
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))

# ---------- Pipeline Cache ----------
# Cached results from the last pipeline run — page loads use this instead of
# re-running the full pipeline on every request.
_pipeline_cache = {
    "results": None,
    "kpis": None,
    "tier_counts": None,
    "route_counts": None,
    "accuracy": None,
    "elapsed": 0,
    "timestamp": 0,        # monotonic time of last run
    "running": False,
}
_cache_lock = threading.Lock()
CACHE_TTL = 300  # 5 minutes

# ---------- Rate Limiter ----------
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT = 10          # max requests
RATE_WINDOW = 60          # per N seconds


def _is_rate_limited(key: str) -> bool:
    """Check if endpoint is rate-limited (10 req/min sliding window)."""
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[key]
        # Evict old entries
        _rate_buckets[key] = [t for t in bucket if now - t < RATE_WINDOW]
        if len(_rate_buckets[key]) >= RATE_LIMIT:
            return True
        _rate_buckets[key].append(now)
    return False


# ---------- Auth ----------

def require_auth(f):
    """Decorator: require Bearer token if DASHBOARD_API_KEY is set."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if DASHBOARD_API_KEY:
            auth = request.headers.get("Authorization", "")
            # Support both header auth and query param for dashboard page
            token = request.args.get("key", "")
            if auth == f"Bearer {DASHBOARD_API_KEY}" or token == DASHBOARD_API_KEY:
                return f(*args, **kwargs)
            # Allow cookie-based auth for browser
            if request.cookies.get("joy_auth") == DASHBOARD_API_KEY:
                return f(*args, **kwargs)
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------- Test Leads ----------

TEST_LEADS = [
    # --- Strong enterprise targets (8) ---
    {"name": "Scott Stephenson",  "title": "CEO",          "company": "Deepgram",    "email": "scott@deepgram.com",    "linkedin_url": "https://linkedin.com/in/scott-stephenson",    "expected_tier": "enterprise"},
    {"name": "Jordan Dearsley",   "title": "CEO",          "company": "Vapi",        "email": "jordan@vapi.ai",        "linkedin_url": "https://linkedin.com/in/jordandearsley",      "x_username": "jordan_dearsley", "x_post_text": "Voice AI agents that actually understand context are replacing IVRs. We're just getting started.", "expected_tier": "enterprise"},
    {"name": "Karan Goel",        "title": "CEO",          "company": "Cartesia",    "email": "karan@cartesia.ai",     "linkedin_url": "https://linkedin.com/in/krandiash",           "x_username": "krandiash",       "x_post_text": "Sub-100ms voice synthesis is table stakes now. The next frontier is zero-latency conversations.", "expected_tier": "enterprise"},
    {"name": "Russ d'Sa",         "title": "CEO",          "company": "LiveKit",     "email": "russ@livekit.io",       "linkedin_url": "",                                            "expected_tier": "enterprise"},
    {"name": "Isaiah Granet",     "title": "CEO",          "company": "Bland AI",    "email": "isaiah@bland.ai",       "linkedin_url": "",                                            "expected_tier": "enterprise"},
    {"name": "Guillermo Rauch",   "title": "CEO",          "company": "Vercel",      "email": "guillermo@vercel.com",  "linkedin_url": "https://linkedin.com/in/rauchg",              "x_username": "rauchg",          "x_post_text": "The best developer tools disappear. You think about the product, not deployment.", "expected_tier": "enterprise"},
    {"name": "Paul Copplestone",  "title": "CEO",          "company": "Supabase",    "email": "paul@supabase.io",      "linkedin_url": "https://linkedin.com/in/paulcopplestone",     "expected_tier": "enterprise"},
    {"name": "James Hawkins",     "title": "Co-CEO",       "company": "PostHog",     "email": "james@posthog.com",     "linkedin_url": "",                                            "expected_tier": "enterprise"},
    # --- Medium targets (5) ---
    {"name": "Zeno Rocha",        "title": "CEO",          "company": "Resend",      "email": "zeno@resend.com",       "linkedin_url": "https://linkedin.com/in/zenorocha",           "company_size": 6,    "expected_tier": "self_serve"},
    {"name": "Jake Cooper",       "title": "CEO",          "company": "Railway",     "email": "jake@railway.com",      "linkedin_url": "https://linkedin.com/in/thejakecooper",       "company_size": 30,   "expected_tier": "self_serve"},
    {"name": "Will Williams",     "title": "CTO",          "company": "Speechmatics","email": "will@speechmatics.com", "linkedin_url": "",                                            "company_size": 150,  "expected_tier": "self_serve"},
    {"name": "Karri Saarinen",    "title": "CEO",          "company": "Linear",      "email": "karri@linear.app",      "linkedin_url": "https://linkedin.com/in/karrisaarinen",       "x_username": "karrisaarinen",   "x_post_text": "Software quality is a feature. Developer tools should be fast and crafted, not bloated.", "company_size": 120, "expected_tier": "self_serve"},
    {"name": "Katy Wigdahl",      "title": "CEO",          "company": "Speechmatics","email": "katy@speechmatics.com", "linkedin_url": "",                                            "company_size": 150,  "expected_tier": "self_serve"},
    # --- Weak/nurture targets (4) ---
    {"name": "Celeste Amadon",    "title": "Co-Founder",   "company": "Known",       "email": "celeste@known.app",     "linkedin_url": "",                                            "company_size": 10,   "expected_tier": "nurture"},
    {"name": "Neville Letzerich", "title": "CMO",          "company": "Talkdesk",    "email": "neville@talkdesk.com",  "linkedin_url": "",                                            "company_size": 1400, "expected_tier": "nurture"},
    {"name": "Bu Kinoshita",      "title": "CTO",          "company": "Resend",      "email": "bu@resend.com",         "linkedin_url": "",                                            "company_size": 6,    "expected_tier": "nurture"},
    {"name": "Sobhan Nejad",      "title": "Co-Founder & COO", "company": "Bland AI","email": "sobhan@bland.ai",       "linkedin_url": "",                                            "expected_tier": "nurture"},
    # --- Should-be-disqualified (3) ---
    {"name": "Tiago Paiva",       "title": "CEO",          "company": "Talkdesk",    "email": "tiago@talkdesk.com",    "linkedin_url": "",                                            "company_size": 1400, "expected_tier": "disqualified"},
    {"name": "Mati Staniszewski", "title": "CEO",          "company": "ElevenLabs",  "email": "mati@elevenlabs.io",    "linkedin_url": "",                                            "expected_tier": "disqualified"},
    {"name": "Michael Truell",    "title": "CEO",          "company": "Anysphere",   "email": "michael@anysphere.inc", "linkedin_url": "",                                            "expected_tier": "disqualified"},
]

# ---------- HTML Template ----------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Joy — Voco V2 Sales</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif; background:#08080f; color:#e0e0e0; min-height:100vh; }

  /* ---- Header ---- */
  .header { background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%); padding:20px 28px 16px; border-bottom:1px solid #2a2a4a; display:flex; align-items:flex-start; gap:16px; flex-wrap:wrap; }
  .header-left { flex:1; min-width:240px; }
  .header h1 { font-size:20px; font-weight:700; color:#fff; }
  .header .sub { font-size:12px; color:#8888aa; margin-top:3px; }
  .agents { display:flex; gap:6px; margin-top:10px; flex-wrap:wrap; }
  .agents span { background:#2a2a4a; color:#aab; padding:3px 9px; border-radius:10px; font-size:11px; font-weight:500; }
  .agents span.on { background:#1db95420; color:#1db954; border:1px solid #1db95440; }
  .header-right { display:flex; flex-direction:column; align-items:flex-end; gap:6px; padding-top:2px; }
  .inbox-badge { background:#f59e0b20; color:#fbbf24; border:1px solid #f59e0b44; border-radius:8px; padding:5px 12px; font-size:12px; font-weight:600; cursor:pointer; white-space:nowrap; }
  .inbox-badge:hover { background:#f59e0b33; }
  .inbox-badge .count { background:#f59e0b; color:#000; border-radius:10px; padding:1px 6px; margin-left:5px; font-size:11px; }
  .next-scan { font-size:11px; color:#666; }
  .next-scan span { color:#aab; }
  .btn-run { background:#3b82f6; color:#fff; border:none; border-radius:7px; padding:6px 14px; font-size:11px; font-weight:600; cursor:pointer; margin-top:4px; }
  .btn-run:hover { background:#2563eb; }
  .btn-run:disabled { opacity:0.5; cursor:not-allowed; }

  /* ---- Tabs ---- */
  .tabs { display:flex; gap:0; border-bottom:1px solid #1a1a2e; background:#0d0d1a; padding:0 28px; }
  .tab { padding:11px 20px; font-size:13px; font-weight:500; color:#666; cursor:pointer; border-bottom:2px solid transparent; transition:all 0.15s; }
  .tab:hover { color:#aab; }
  .tab.active { color:#fff; border-bottom-color:#1db954; }
  .tab .badge { background:#f59e0b; color:#000; border-radius:8px; padding:1px 5px; font-size:10px; margin-left:5px; }

  /* ---- Content ---- */
  .tab-content { display:none; padding:24px 28px; }
  .tab-content.active { display:block; }

  /* ---- Approval Cards ---- */
  .inbox-empty { text-align:center; padding:60px 20px; color:#555; }
  .inbox-empty .icon { font-size:40px; margin-bottom:12px; }
  .inbox-empty p { font-size:14px; }
  .approval-card { background:#111122; border:1px solid #2a2a4a; border-radius:10px; padding:18px; margin-bottom:14px; transition:border-color 0.2s,opacity 0.3s; }
  .approval-card:hover { border-color:#3a3a6a; }
  .approval-card.fading { opacity:0; transform:scale(0.98); transition:all 0.3s; }
  .ac-header { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .ac-name { font-weight:600; font-size:15px; color:#fff; }
  .ac-meta { font-size:12px; color:#666; }
  .ac-tags { display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; }
  .ac-draft-label { font-size:10px; color:#aab; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; margin-top:12px; margin-bottom:4px; }
  .ac-draft { background:#0d0d1a; border:1px solid #1e1e3a; border-radius:6px; padding:12px; font-size:12px; color:#c0c0d0; line-height:1.6; white-space:pre-wrap; max-height:200px; overflow-y:auto; }
  .ac-followup { background:#0a150a; border:1px solid #1a3a1a; border-left:3px solid #22c55e; border-radius:6px; padding:10px 12px; font-size:12px; color:#7a9a7a; line-height:1.5; white-space:pre-wrap; max-height:100px; overflow-y:auto; }
  .ac-actions { display:flex; gap:8px; margin-top:14px; }
  .btn-approve { background:#22c55e; color:#000; border:none; border-radius:7px; padding:8px 20px; font-size:13px; font-weight:600; cursor:pointer; transition:background 0.15s; }
  .btn-approve:hover { background:#16a34a; }
  .btn-reject { background:#1a1a2e; color:#f87171; border:1px solid #ef444444; border-radius:7px; padding:8px 16px; font-size:13px; font-weight:500; cursor:pointer; transition:all 0.15s; }
  .btn-reject:hover { background:#2a0a0a; border-color:#ef4444; }
  .btn-loading { opacity:0.5; cursor:not-allowed; }

  /* ---- Lead Cards (Pipeline tab) ---- */
  .tier-section { margin-bottom:24px; }
  .tier-label { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:10px; display:flex; align-items:center; gap:8px; }
  .tier-label .tl-line { flex:1; height:1px; background:#1a1a2e; }
  .lead-cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:10px; }
  .lead-card { background:#111122; border:1px solid #1e1e3a; border-radius:8px; padding:14px; transition:border-color 0.2s; }
  .lead-card:hover { border-color:#3a3a6a; }
  .lead-card.hot-lead { border-color:#22c55e44; box-shadow:0 0 0 1px #22c55e22; animation:pulse-border 2s ease-in-out infinite; }
  @keyframes pulse-border { 0%,100% { box-shadow:0 0 0 1px #22c55e22; } 50% { box-shadow:0 0 0 3px #22c55e33; } }
  .lead-name { font-weight:600; font-size:14px; color:#fff; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
  .lead-meta { font-size:12px; color:#666; margin-top:3px; }
  .lead-tags { display:flex; gap:5px; margin-top:8px; flex-wrap:wrap; }
  .tag { padding:2px 8px; border-radius:5px; font-size:11px; font-weight:600; }
  .tag-enterprise { background:#22c55e1a; color:#22c55e; border:1px solid #22c55e33; }
  .tag-self_serve  { background:#3b82f61a; color:#60a5fa; border:1px solid #3b82f633; }
  .tag-nurture     { background:#f59e0b1a; color:#fbbf24; border:1px solid #f59e0b33; }
  .tag-disqualified{ background:#6b728022; color:#9ca3af; border:1px solid #6b728033; }
  .tag-hot  { background:#22c55e33; color:#4ade80; border:1px solid #22c55e66; }
  .tag-cold { background:#1e1e3a; color:#8888aa; border:1px solid #2a2a4a; }
  .tag-score{ background:#1a1a2e; color:#8888aa; border:1px solid #2a2a4a; }
  .acc-ok { color:#22c55e; font-size:12px; font-weight:700; }
  .acc-bad { color:#f87171; font-size:11px; }
  .route-label { font-size:11px; color:#8888aa; margin-top:5px; }
  .route-label.followup  { color:#fbbf24; }
  .route-label.closing   { color:#22c55e; }
  .route-label.disq      { color:#6b7280; }
  .dm-wrap { margin-top:8px; }
  .dm-preview { background:#0d0d1a; border:1px solid #1e1e3a; border-radius:5px; padding:9px; font-size:12px; color:#8888aa; line-height:1.5; white-space:pre-wrap; max-height:80px; overflow:hidden; }
  .dm-expand { font-size:10px; color:#555; cursor:pointer; margin-top:3px; display:block; }
  .dm-expand:hover { color:#aab; }
  .dm-expanded { max-height:none !important; }
  .follow-up-preview { background:#0a150a; border:1px solid #1a3a1a; border-left:3px solid #22c55e; border-radius:5px; padding:9px; margin-top:8px; font-size:12px; color:#5a7a5a; line-height:1.5; white-space:pre-wrap; max-height:60px; overflow:hidden; }
  .fup-label { font-size:10px; color:#22c55e; font-weight:600; margin-top:8px; text-transform:uppercase; letter-spacing:0.5px; }
  .suggestion-box { background:#1a1800; border:1px solid #3a3a1a; border-radius:5px; padding:8px; margin-top:8px; font-size:11px; color:#cca; }
  .x-post { background:#0a1628; border-left:3px solid #1d9bf0; border-radius:4px; padding:7px 9px; margin-top:7px; font-size:11px; color:#7799bb; line-height:1.4; }
  .badge-v { background:#22c55e1a; color:#22c55e; border:1px solid #22c55e33; border-radius:5px; padding:1px 6px; font-size:10px; }
  .badge-u { background:#f871711a; color:#f87171; border:1px solid #f8717133; border-radius:5px; padding:1px 6px; font-size:10px; }

  /* Accuracy panel */
  .acc-panel { background:#111122; border:1px solid #1e1e3a; border-radius:10px; padding:20px; margin-bottom:24px; }
  .acc-big { font-size:48px; font-weight:800; text-align:center; }
  .acc-big.green { color:#22c55e; } .acc-big.yellow { color:#fbbf24; } .acc-big.red { color:#f87171; }
  .mismatch-row { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #1a1a2e; font-size:12px; }
  .mismatch-name { color:#ccc; min-width:150px; }

  /* ---- Analytics Tab ---- */
  .kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:20px; }
  .kpi-card { background:#111122; border:1px solid #1e1e3a; border-radius:8px; padding:16px; text-align:center; }
  .kpi-value { font-size:30px; font-weight:700; }
  .kpi-value.g { color:#22c55e; } .kpi-value.b { color:#60a5fa; } .kpi-value.y { color:#fbbf24; }
  .kpi-label { font-size:10px; color:#555; margin-top:4px; text-transform:uppercase; letter-spacing:0.5px; }
  .section-title { font-size:12px; font-weight:600; color:#888; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:10px; }
  .two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  .analytics-box { background:#111122; border:1px solid #1e1e3a; border-radius:8px; padding:16px; }
  .schedule-item { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1a1a2e; font-size:12px; }
  .schedule-item:last-child { border:none; }
  .schedule-name { color:#8888aa; }
  .schedule-time { color:#fbbf24; font-weight:600; }
  .log-entry { font-family:'SF Mono','Fira Code',monospace; font-size:10px; color:#555; padding:2px 0; border-bottom:1px solid #0d0d0d; }
  .log-entry .audit { color:#22c55e; }
  .log-entry .sug { color:#fbbf24; }
  .closing-card { background:#0d0d1a; border:1px solid #1e1e3a; border-radius:7px; padding:12px; margin-bottom:10px; }
  .closing-name { font-weight:600; font-size:13px; color:#fff; margin-bottom:6px; }
  .closing-body { font-size:11px; color:#8888aa; white-space:pre-wrap; line-height:1.5; }
  details summary { cursor:pointer; font-size:12px; color:#666; padding:8px 0; }
  details summary:hover { color:#aab; }

  .acc-sub { text-align:center; font-size:11px; color:#555; margin-top:4px; margin-bottom:16px; text-transform:uppercase; letter-spacing:0.5px; }
  .acc-counts { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin:12px 0 16px; }
  .acc-count-card { background:#0d0d1a; border:1px solid #1e1e3a; border-radius:6px; padding:10px; text-align:center; }
  .acc-count-val { font-size:22px; font-weight:700; }

  /* Status toast */
  .toast { position:fixed; bottom:24px; right:24px; background:#22c55e; color:#000; padding:12px 20px; border-radius:8px; font-size:13px; font-weight:600; z-index:1000; opacity:0; transition:opacity 0.3s; }
  .toast.show { opacity:1; }
  .toast.error { background:#ef4444; color:#fff; }
</style>
</head>
<body>

<!-- ===== Header ===== -->
<div class="header">
  <div class="header-left">
    <h1>Joy V1 Sales Rep</h1>
    <div class="sub">Voco V2 &mdash; Outreach Hunter &bull; Auditor &bull; Closer Manager &bull; Follow-Up Architect &mdash; {{ leads|length }} leads &mdash; {% if elapsed %}async {{ elapsed }}s{% else %}cached{% endif %}</div>
    <div class="agents">
      <span class="on">Outreach Hunter</span>
      <span class="on">Auditor</span>
      <span class="on">Closer Manager</span>
      <span class="on">Follow-Up Architect</span>
    </div>
  </div>
  <div class="header-right">
    <div class="inbox-badge" onclick="showTab('inbox')">
      Inbox<span class="count" id="inbox-count">{{ pending_count }}</span>
    </div>
    <div class="next-scan">Next scan: <span id="next-scan-text">{{ next_scan }}</span></div>
    <button class="btn-run" id="btn-run-pipeline" onclick="runPipeline()">Run Pipeline</button>
  </div>
</div>

<!-- ===== Tabs ===== -->
<div class="tabs">
  <div class="tab active" id="tab-inbox"    onclick="showTab('inbox')">
    Inbox <span class="badge" id="tab-inbox-badge">{{ pending_count }}</span>
  </div>
  <div class="tab"        id="tab-engage"   onclick="showTab('engage')">Engage</div>
  <div class="tab"        id="tab-pipeline" onclick="showTab('pipeline')">Pipeline</div>
  <div class="tab"        id="tab-analytics"onclick="showTab('analytics')">Analytics</div>
</div>

<!-- ===== TAB 1: Inbox ===== -->
<div class="tab-content active" id="content-inbox">
  <div id="inbox-container">
    {% if pending_items %}
      {% for item in pending_items %}
      <div class="approval-card" id="card-{{ item.id }}">
        <div class="ac-header">
          <span class="ac-name">{{ item.lead_name }}</span>
          <span class="tag tag-{{ item.lead_tier }}">{{ item.lead_tier }}</span>
          <span class="tag tag-score">{{ "%.2f"|format(item.lead_score) }}</span>
          <span class="tag" style="background:#1a1a2e;color:#aab;border:1px solid #2a2a4a;">{{ item.channel }}</span>
        </div>
        <div class="ac-meta">{{ item.lead_email }}{% if item.source == 'cron' %} &bull; scheduled{% endif %}</div>
        <div class="ac-draft-label">Outreach Draft</div>
        <div class="ac-draft">{{ item.outreach_draft }}</div>
        {% if item.follow_up_draft %}
        <div class="ac-draft-label" style="color:#22c55e">Follow-Up Step 1</div>
        <div class="ac-followup">{{ item.follow_up_draft }}</div>
        {% endif %}
        <div class="ac-actions">
          <button class="btn-approve" onclick="approveAndSend({{ item.id }})">Approve &amp; Send</button>
          <button class="btn-reject"  onclick="reviewItem({{ item.id }}, 'reject')">Reject</button>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <div class="inbox-empty">
        <div class="icon">No leads pending</div>
        <p>No leads pending review — Joy is watching for new signals.</p>
        <p style="margin-top:8px;font-size:12px;color:#444;">Next scheduled scan: {{ next_scan }}</p>
      </div>
    {% endif %}
  </div>
</div>

<!-- ===== TAB 2: Engage ===== -->
<div class="tab-content" id="content-engage">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
    <div class="section-title" style="margin:0;">Engagement Queue</div>
    <button onclick="discoverLeads()" style="background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:8px 16px;font-size:12px;font-weight:600;cursor:pointer;">Discover Leads</button>
  </div>
  {% if engage_items %}
    {% for item in engage_items %}
    <div class="approval-card" id="engage-card-{{ item.id }}">
      <div class="ac-header">
        <span class="ac-name">{{ item.lead_name or 'Unknown' }}</span>
        <span class="tag" style="background:#1d9bf020;color:#1d9bf0;border:1px solid #1d9bf044;">{{ item.action_type }}</span>
        <span class="tag" style="background:#1a1a2e;color:#aab;border:1px solid #2a2a4a;">{{ item.platform }}</span>
      </div>
      {% if item.target_post_text %}
      <div class="x-post" style="margin-top:8px;">{{ item.target_post_text[:300] }}</div>
      {% endif %}
      {% if item.target_post_url %}
      <div class="ac-meta" style="margin-top:4px;"><a href="{{ item.target_post_url }}" target="_blank" style="color:#1d9bf0;font-size:11px;">{{ item.target_post_url }}</a></div>
      {% endif %}
      <div class="ac-draft-label">Draft Response</div>
      <div class="ac-draft">{{ item.outreach_draft }}</div>
      <div class="ac-actions">
        <button class="btn-approve" onclick="executeEngagement({{ item.id }})">Send</button>
        <button class="btn-reject" onclick="reviewItem({{ item.id }}, 'reject')">Reject</button>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="inbox-empty">
      <div class="icon">No drafts</div>
      <p>No engagement drafts pending — Joy will scan for ICP posts on schedule.</p>
    </div>
  {% endif %}

  {% if engagement_stats %}
  <div style="margin-top:24px;">
    <div class="section-title">Engagement History</div>
    <div class="kpi-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr));">
      {% for key, val in engagement_stats.items() %}
      <div class="kpi-card">
        <div class="kpi-value b">{{ val.total }}</div>
        <div class="kpi-label">{{ key.replace('_',' ') }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}
</div>

<!-- ===== TAB 3: Pipeline ===== -->
<div class="tab-content" id="content-pipeline">

  <!-- Accuracy panel -->
  <div class="acc-panel">
    <div class="acc-big {% if accuracy.pct >= 80 %}green{% elif accuracy.pct >= 60 %}yellow{% else %}red{% endif %}">{{ accuracy.pct }}%</div>
    <div class="acc-sub">Tier Accuracy</div>
    <div class="acc-counts">
      <div class="acc-count-card"><div class="acc-count-val" style="color:#22c55e">{{ accuracy.correct }}</div><div class="kpi-label">Correct</div></div>
      <div class="acc-count-card"><div class="acc-count-val" style="color:#f87171">{{ accuracy.mismatches|length }}</div><div class="kpi-label">Mismatches</div></div>
      <div class="acc-count-card"><div class="acc-count-val">{{ accuracy.total }}</div><div class="kpi-label">Tested</div></div>
    </div>
    {% if accuracy.mismatches %}
    <details>
      <summary>Show {{ accuracy.mismatches|length }} mismatches</summary>
      <div style="margin-top:8px;">
        {% for m in accuracy.mismatches %}
        <div class="mismatch-row">
          <span class="mismatch-name">{{ m.name }}</span>
          <span class="tag tag-{{ m.expected }}">{{ m.expected }}</span>
          <span style="color:#444">&rarr;</span>
          <span class="tag tag-{{ m.actual }}">{{ m.actual }}</span>
          <span style="color:#444;font-size:11px;">({{ "%.2f"|format(m.score) }})</span>
        </div>
        {% endfor %}
      </div>
    </details>
    {% endif %}
  </div>

  <!-- Enterprise -->
  {% set enterprise_leads = leads | selectattr('tier', 'equalto', 'enterprise') | list %}
  {% if enterprise_leads %}
  <div class="tier-section">
    <div class="tier-label" style="color:#22c55e">Enterprise ({{ enterprise_leads|length }}) <div class="tl-line"></div></div>
    <div class="lead-cards">
      {% for lead in enterprise_leads %}
      <div class="lead-card {% if lead.status == 'hot' %}hot-lead{% endif %}">
        <div class="lead-name">
          {{ lead.name }}
          {% if lead.x_username %}<span style="color:#1d9bf0;font-size:11px;">@{{ lead.x_username }}</span>{% endif %}
          {% if lead.email_confidence >= 80 %}<span class="badge-v">verified</span>{% endif %}
          {% if lead.expected_tier %}{% if lead.tier_match %}<span class="acc-ok">OK</span>{% else %}<span class="acc-bad">{{ lead.expected_tier }}</span>{% endif %}{% endif %}
        </div>
        <div class="lead-meta">{{ lead.title }} at {{ lead.company }}{% if lead.email %} &mdash; {{ lead.email }}{% endif %}</div>
        <div class="lead-tags">
          <span class="tag tag-{{ lead.status }}">{{ lead.status }}</span>
          <span class="tag tag-score">{{ "%.2f"|format(lead.score) }}</span>
          {% if lead.channel %}<span class="tag tag-score">{{ lead.channel }}</span>{% endif %}
        </div>
        {% if lead.status == 'hot' %}<div class="route-label closing">Routing to Closer</div>
        {% else %}<div class="route-label followup">Queued for Follow-Up</div>{% endif %}
        {% if lead.x_post_text %}<div class="x-post">{{ lead.x_post_text }}</div>{% endif %}
        {% if lead.dm_preview %}
        <div class="dm-wrap">
          <div class="dm-preview" id="dm-{{ loop.index }}-e">{{ lead.dm_preview }}</div>
          <span class="dm-expand" onclick="expandDm('dm-{{ loop.index }}-e',this)">expand</span>
        </div>
        {% endif %}
        {% if lead.follow_up_preview %}
        <div class="fup-label">Follow-Up Step 1</div>
        <div class="follow-up-preview">{{ lead.follow_up_preview }}</div>
        {% endif %}
        {% if lead.suggestion %}<div class="suggestion-box">{{ lead.suggestion }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- Self-serve -->
  {% set self_serve_leads = leads | selectattr('tier', 'equalto', 'self_serve') | list %}
  {% if self_serve_leads %}
  <div class="tier-section">
    <div class="tier-label" style="color:#60a5fa">Self-Serve ({{ self_serve_leads|length }}) <div class="tl-line"></div></div>
    <div class="lead-cards">
      {% for lead in self_serve_leads %}
      <div class="lead-card">
        <div class="lead-name">
          {{ lead.name }}
          {% if lead.x_username %}<span style="color:#1d9bf0;font-size:11px;">@{{ lead.x_username }}</span>{% endif %}
          {% if lead.email_confidence >= 80 %}<span class="badge-v">verified</span>{% endif %}
          {% if lead.expected_tier %}{% if lead.tier_match %}<span class="acc-ok">OK</span>{% else %}<span class="acc-bad">{{ lead.expected_tier }}</span>{% endif %}{% endif %}
        </div>
        <div class="lead-meta">{{ lead.title }} at {{ lead.company }}{% if lead.email %} &mdash; {{ lead.email }}{% endif %}</div>
        <div class="lead-tags">
          <span class="tag tag-{{ lead.status }}">{{ lead.status }}</span>
          <span class="tag tag-score">{{ "%.2f"|format(lead.score) }}</span>
          {% if lead.channel %}<span class="tag tag-score">{{ lead.channel }}</span>{% endif %}
        </div>
        <div class="route-label followup">Queued for Follow-Up</div>
        {% if lead.dm_preview %}
        <div class="dm-wrap">
          <div class="dm-preview" id="dm-{{ loop.index }}-s">{{ lead.dm_preview }}</div>
          <span class="dm-expand" onclick="expandDm('dm-{{ loop.index }}-s',this)">expand</span>
        </div>
        {% endif %}
        {% if lead.follow_up_preview %}
        <div class="fup-label">Follow-Up Step 1</div>
        <div class="follow-up-preview">{{ lead.follow_up_preview }}</div>
        {% endif %}
        {% if lead.suggestion %}<div class="suggestion-box">{{ lead.suggestion }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- Nurture -->
  {% set nurture_leads = leads | selectattr('tier', 'equalto', 'nurture') | list %}
  {% if nurture_leads %}
  <div class="tier-section">
    <div class="tier-label" style="color:#fbbf24">Nurture ({{ nurture_leads|length }}) <div class="tl-line"></div></div>
    <div class="lead-cards">
      {% for lead in nurture_leads %}
      <div class="lead-card">
        <div class="lead-name">{{ lead.name }}
          {% if lead.expected_tier %}{% if lead.tier_match %}<span class="acc-ok">OK</span>{% else %}<span class="acc-bad">{{ lead.expected_tier }}</span>{% endif %}{% endif %}
        </div>
        <div class="lead-meta">{{ lead.title }} at {{ lead.company }}</div>
        <div class="lead-tags">
          <span class="tag tag-score">{{ "%.2f"|format(lead.score) }}</span>
          {% if lead.channel %}<span class="tag tag-score">{{ lead.channel }}</span>{% endif %}
        </div>
        <div class="route-label followup">In nurture sequence</div>
        {% if lead.dm_preview %}<div class="dm-preview" style="margin-top:8px;">{{ lead.dm_preview }}</div>{% endif %}
        {% if lead.suggestion %}<div class="suggestion-box">{{ lead.suggestion }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- Disqualified (collapsed) -->
  {% set disq_leads = leads | selectattr('tier', 'equalto', 'disqualified') | list %}
  {% if disq_leads %}
  <details>
    <summary style="color:#6b7280;font-size:13px;padding:10px 0;cursor:pointer;">Show {{ disq_leads|length }} disqualified leads</summary>
    <div class="lead-cards" style="margin-top:10px;">
      {% for lead in disq_leads %}
      <div class="lead-card" style="opacity:0.5;">
        <div class="lead-name" style="color:#9ca3af;">{{ lead.name }}
          {% if lead.expected_tier %}{% if lead.tier_match %}<span class="acc-ok">OK</span>{% else %}<span class="acc-bad">{{ lead.expected_tier }}</span>{% endif %}{% endif %}
        </div>
        <div class="lead-meta">{{ lead.title }} at {{ lead.company }}</div>
        <div class="lead-tags"><span class="tag tag-score">{{ "%.2f"|format(lead.score) }}</span></div>
      </div>
      {% endfor %}
    </div>
  </details>
  {% endif %}
</div>

<!-- ===== TAB 4: Analytics ===== -->
<div class="tab-content" id="content-analytics">
  <!-- KPIs -->
  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-value">{{ kpis.total_processed }}</div><div class="kpi-label">Total Processed</div></div>
    <div class="kpi-card"><div class="kpi-value g">{{ kpis.hot_leads }}</div><div class="kpi-label">Hot Leads</div></div>
    <div class="kpi-card"><div class="kpi-value b">{{ kpis.cold_leads }}</div><div class="kpi-label">Cold Leads</div></div>
    <div class="kpi-card"><div class="kpi-value y">{{ "%.0f"|format(kpis.delivery_rate * 100) }}%</div><div class="kpi-label">Delivery Rate</div></div>
    <div class="kpi-card"><div class="kpi-value g">{{ "%.0f"|format(kpis.close_rate * 100) }}%</div><div class="kpi-label">Close Rate</div></div>
    <div class="kpi-card"><div class="kpi-value">{{ kpis.responded }}</div><div class="kpi-label">Responded</div></div>
  </div>

  <div class="two-col">
    <!-- Tier Breakdown -->
    <div class="analytics-box">
      <div class="section-title">Tier Breakdown</div>
      {% for tier, count in tier_counts.items() %}
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span class="tag tag-{{ tier }}" style="min-width:100px;text-align:center;">{{ tier }}</span>
        <div style="flex:1;height:18px;background:#0d0d1a;border-radius:3px;overflow:hidden;">
          <div style="height:100%;width:{{ (count / leads|length * 100)|int }}%;background:{% if tier=='enterprise' %}#22c55e{% elif tier=='self_serve' %}#3b82f6{% elif tier=='nurture' %}#f59e0b{% else %}#6b7280{% endif %};border-radius:3px;"></div>
        </div>
        <span style="font-size:13px;color:#aab;min-width:18px;">{{ count }}</span>
      </div>
      {% endfor %}

      <div style="margin-top:16px;">
        <div class="section-title">Route Decisions</div>
        {% for route, count in route_counts.items() %}
        <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1a1a2e;font-size:12px;">
          <span style="color:#8888aa;">{{ route }}</span><span style="color:#fff;font-weight:600;">{{ count }}</span>
        </div>
        {% endfor %}
      </div>
    </div>

    <!-- Scheduled Scans -->
    <div class="analytics-box">
      <div class="section-title">Scheduled Scans (Pacific Time)</div>
      {% for job in schedule %}
      <div class="schedule-item">
        <span class="schedule-name">{{ job.name }}</span>
        <span class="schedule-time">{{ job.next_run_pt }}</span>
      </div>
      {% endfor %}
      {% if not schedule %}
      <div style="font-size:12px;color:#555;padding:8px 0;">Scheduler starting...</div>
      {% endif %}

      <div style="margin-top:16px;">
        <div class="section-title">Approval Queue</div>
        <div style="display:flex;gap:10px;">
          <div style="flex:1;text-align:center;background:#0d0d1a;border-radius:6px;padding:10px;">
            <div style="font-size:20px;font-weight:700;color:#fbbf24;">{{ approval_counts.pending }}</div>
            <div class="kpi-label">Pending</div>
          </div>
          <div style="flex:1;text-align:center;background:#0d0d1a;border-radius:6px;padding:10px;">
            <div style="font-size:20px;font-weight:700;color:#22c55e;">{{ approval_counts.approved }}</div>
            <div class="kpi-label">Approved</div>
          </div>
          <div style="flex:1;text-align:center;background:#0d0d1a;border-radius:6px;padding:10px;">
            <div style="font-size:20px;font-weight:700;color:#6b7280;">{{ approval_counts.rejected }}</div>
            <div class="kpi-label">Rejected</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Closing Scripts -->
  {% if leads | selectattr('closing_script') | list %}
  <div style="margin-top:20px;">
    <div class="section-title">Closing Scripts (Hot Leads)</div>
    {% for lead in leads %}{% if lead.closing_script %}
    <div class="closing-card">
      <div class="closing-name">{{ lead.name }} &mdash; <span style="color:#22c55e;">{{ lead.close_action }}</span></div>
      <div class="closing-body">{{ lead.closing_script }}</div>
    </div>
    {% endif %}{% endfor %}
  </div>
  {% endif %}

  <!-- Execution Ledger -->
  <div style="margin-top:20px;">
    <div class="section-title">Execution Ledger ({{ log|length }} entries)</div>
    <div class="analytics-box" style="max-height:300px;overflow-y:auto;">
      {% for entry in log %}
      <div class="log-entry">
        {% if '[AUDIT]' in entry %}<span class="audit">{{ entry }}</span>
        {% elif 'SUGGESTION' in entry or 'Suggestion' in entry %}<span class="sug">{{ entry }}</span>
        {% else %}{{ entry }}{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<!-- Toast notification -->
<div class="toast" id="toast"></div>

<script>
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.getElementById('content-' + name).classList.add('active');
}

function expandDm(id, el) {
  const el2 = document.getElementById(id);
  el2.classList.toggle('dm-expanded');
  el.textContent = el2.classList.contains('dm-expanded') ? 'collapse' : 'expand';
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  setTimeout(() => t.className = 'toast', 3000);
}

async function reviewItem(id, action) {
  const card = document.getElementById('card-' + id);
  const btns = card.querySelectorAll('button');
  btns.forEach(b => b.classList.add('btn-loading'));

  const resp = await fetch('/' + action + '/' + id, {method:'POST'});
  const data = await resp.json();

  if (data.status === action + 'd' || data.status === 'rejected') {
    card.classList.add('fading');
    setTimeout(() => {
      card.remove();
      updateInboxCount(-1);
      if (!document.querySelector('.approval-card')) {
        document.getElementById('inbox-container').innerHTML =
          '<div class="inbox-empty"><div class="icon">All caught up</div><p>Joy will surface new leads on the next scan.</p></div>';
      }
    }, 320);
    showToast('Item ' + action + 'd', false);
  }
}

async function approveAndSend(id) {
  const card = document.getElementById('card-' + id);
  const btns = card.querySelectorAll('button');
  btns.forEach(b => b.classList.add('btn-loading'));

  const resp = await fetch('/approve-send/' + id, {method:'POST'});
  const data = await resp.json();

  if (data.status === 'sent' || data.status === 'queued' || data.status === 'approved') {
    card.classList.add('fading');
    setTimeout(() => {
      card.remove();
      updateInboxCount(-1);
      if (!document.querySelector('.approval-card')) {
        document.getElementById('inbox-container').innerHTML =
          '<div class="inbox-empty"><div class="icon">All caught up</div><p>Joy will surface new leads on the next scan.</p></div>';
      }
    }, 320);
    showToast('Approved & ' + (data.send_status || 'sent'), false);
  } else {
    btns.forEach(b => b.classList.remove('btn-loading'));
    showToast('Error: ' + (data.error || 'unknown'), true);
  }
}

function updateInboxCount(delta) {
  const badge = document.getElementById('inbox-count');
  const tabBadge = document.getElementById('tab-inbox-badge');
  let n = parseInt(badge.textContent) + delta;
  if (n < 0) n = 0;
  badge.textContent = n;
  tabBadge.textContent = n;
}

async function executeEngagement(id) {
  const card = document.getElementById('engage-card-' + id);
  const btns = card.querySelectorAll('button');
  btns.forEach(b => b.classList.add('btn-loading'));
  const resp = await fetch('/execute/' + id, {method:'POST'});
  const data = await resp.json();
  if (data.status === 'executed' || data.status === 'approved') {
    card.classList.add('fading');
    setTimeout(() => card.remove(), 320);
    showToast('Engagement sent', false);
  } else {
    btns.forEach(b => b.classList.remove('btn-loading'));
    showToast('Failed: ' + (data.error || 'unknown'), true);
  }
}

async function discoverLeads() {
  const btn = event.target;
  btn.textContent = 'Scanning...';
  btn.disabled = true;
  const resp = await fetch('/api/discover', {method:'POST'});
  const data = await resp.json();
  btn.textContent = 'Discover Leads';
  btn.disabled = false;
  showToast('Discovered ' + (data.count || 0) + ' leads from ' + (data.sources || 0) + ' sources', false);
  setTimeout(() => location.reload(), 1000);
}

async function runPipeline() {
  const btn = document.getElementById('btn-run-pipeline');
  btn.textContent = 'Running...';
  btn.disabled = true;
  const resp = await fetch('/api/run-pipeline', {method:'POST'});
  const data = await resp.json();
  btn.textContent = 'Run Pipeline';
  btn.disabled = false;
  if (data.status === 'ok') {
    showToast('Pipeline complete (' + data.elapsed + 's, ' + data.total + ' leads)', false);
    setTimeout(() => location.reload(), 1000);
  } else {
    showToast('Error: ' + (data.error || 'unknown'), true);
  }
}
</script>
</body>
</html>"""


# ---------- Pipeline Processing ----------

async def process_lead(lead: dict) -> dict:
    """Async agent: one coroutine per lead — hunt -> audit -> route -> queue for approval."""
    hunt_result = await asyncio.to_thread(hunt, lead)
    tier = hunt_result["tier"]
    status = hunt_result["status"]
    score = hunt_result["score"]

    state = {
        "current_lead": lead,
        "lead_tier": tier,
        "lead_status": status,
        "lead_score": score,
        "send_result": {"status": "sent", "channel": hunt_result.get("channel", "")} if hunt_result.get("outreach") else {},
    }
    audit = await asyncio.to_thread(audit_pipeline, state)

    closing_script = ""
    close_action = ""
    follow_up_preview = ""

    if is_hot_lead(lead, score, status):
        route = "closer_manager"
        close = await asyncio.to_thread(close_deal, lead, tier)
        closing_script = close.get("closing_script", "")
        close_action = close.get("action", "")
        state["close_action"] = close_action
        state["close_result"] = close
    elif tier in ("enterprise", "self_serve", "nurture"):
        route = "follow_up_architect"
        fu = await asyncio.to_thread(architect_follow_up, lead, tier, 1)
        fu_body = fu.get("follow_up_text", "")
        follow_up_preview = fu_body[:300] + "..." if len(fu_body) > 300 else fu_body
    else:
        route = "END"

    # Queue to approval_queue (deduped by email)
    enriched = hunt_result.get("lead", lead)
    outreach_dm = hunt_result.get("personalized_dm", "")
    if tier != "disqualified" and outreach_dm:
        queue_for_approval({
            "lead_name": enriched.get("name", lead["name"]),
            "lead_email": enriched.get("email", lead.get("email", "")),
            "lead_tier": tier,
            "lead_score": score,
            "channel": hunt_result.get("channel", ""),
            "outreach_draft": outreach_dm,
            "follow_up_draft": follow_up_preview,
            "closing_script": closing_script,
            "source": "manual",
        })

    dm_preview = outreach_dm

    expected = lead.get("expected_tier", "")
    tier_match = (tier == expected) if expected else None

    batch_state = {
        "lead_status": status,
        "send_result": state.get("send_result", {}),
        "close_action": close_action,
        "close_result": state.get("close_result", {}),
    }

    return {
        "name": enriched.get("name", lead["name"]),
        "title": enriched.get("title", lead.get("title", "")),
        "company": enriched.get("company", lead.get("company", "")),
        "email": enriched.get("email", lead.get("email", "")),
        "x_username": enriched.get("x_username", lead.get("x_username", "")),
        "x_post_text": enriched.get("x_post_text", lead.get("x_post_text", "")),
        "email_confidence": enriched.get("email_confidence", lead.get("email_confidence", 0)),
        "tier": tier,
        "expected_tier": expected,
        "tier_match": tier_match,
        "status": status,
        "score": score,
        "channel": hunt_result.get("channel", ""),
        "route": route,
        "dm_preview": dm_preview,
        "follow_up_preview": follow_up_preview,
        "closing_script": closing_script,
        "close_action": close_action,
        "suggestion": audit.get("suggestions", ""),
        "_batch_state": batch_state,
    }


async def run_pipeline_async():
    """Spawn one async agent per lead — all run concurrently via asyncio.gather()."""
    ledger.clear()
    t0 = time.monotonic()
    raw_results = await asyncio.gather(*[process_lead(lead) for lead in TEST_LEADS])
    elapsed = time.monotonic() - t0

    results = list(raw_results)
    batch_states = [r.pop("_batch_state") for r in results]
    kpis = calculate_batch_kpis(batch_states)

    tier_counts = {}
    route_counts = {}
    for r in results:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
        route_counts[r["route"]] = route_counts.get(r["route"], 0) + 1

    tested = [r for r in results if r["expected_tier"]]
    correct = [r for r in tested if r["tier_match"]]
    mismatches = [r for r in tested if not r["tier_match"]]
    accuracy = {
        "total": len(tested),
        "correct": len(correct),
        "pct": round(len(correct) / len(tested) * 100) if tested else 0,
        "mismatches": [{"name": r["name"], "expected": r["expected_tier"],
                        "actual": r["tier"], "score": r["score"]} for r in mismatches],
    }

    # Persist KPI snapshot to DB
    try:
        conn = get_connection()
        db_kpis = get_kpi_counts(conn)
        save_kpi_snapshot(conn, db_kpis)
    except Exception as e:
        logger.warning("Failed to persist KPI snapshot: %s", e)

    return results, kpis, tier_counts, route_counts, accuracy, round(elapsed, 2)


def _get_cached_or_run():
    """Return cached pipeline results, or run if cache is stale/empty.

    First page load triggers a run. Subsequent loads use cache for CACHE_TTL seconds.
    """
    with _cache_lock:
        if _pipeline_cache["results"] is not None and _pipeline_cache["running"] is False:
            age = time.monotonic() - _pipeline_cache["timestamp"]
            if age < CACHE_TTL:
                return (
                    _pipeline_cache["results"],
                    _pipeline_cache["kpis"],
                    _pipeline_cache["tier_counts"],
                    _pipeline_cache["route_counts"],
                    _pipeline_cache["accuracy"],
                    _pipeline_cache["elapsed"],
                )

    # Cache miss — run pipeline
    results, kpis, tier_counts, route_counts, accuracy, elapsed = asyncio.run(run_pipeline_async())

    with _cache_lock:
        _pipeline_cache["results"] = results
        _pipeline_cache["kpis"] = kpis
        _pipeline_cache["tier_counts"] = tier_counts
        _pipeline_cache["route_counts"] = route_counts
        _pipeline_cache["accuracy"] = accuracy
        _pipeline_cache["elapsed"] = elapsed
        _pipeline_cache["timestamp"] = time.monotonic()
        _pipeline_cache["running"] = False

    return results, kpis, tier_counts, route_counts, accuracy, elapsed


# ---------- Flask Routes ----------

@app.route("/")
def dashboard():
    results, kpis, tier_counts, route_counts, accuracy, elapsed = _get_cached_or_run()
    log = ledger.get_log()

    # Approval queue data
    pending_items = get_pending_approvals()
    approval_counts = get_approval_counts()
    pending_count = approval_counts["pending"]

    # Engagement data
    engage_items = get_pending_engagements()
    engagement_stats = get_engagement_stats()

    # Next scheduled scan
    next_runs = get_next_runs(scheduler, n=10)
    next_scan = next_runs[0]["next_run_pt"] if next_runs else "Not scheduled"

    resp = render_template_string(
        HTML,
        leads=results,
        kpis=kpis,
        tier_counts=tier_counts,
        route_counts=route_counts,
        accuracy=accuracy,
        elapsed=elapsed,
        log=log,
        pending_items=pending_items,
        pending_count=pending_count,
        approval_counts=approval_counts,
        schedule=next_runs,
        next_scan=next_scan,
        engage_items=engage_items,
        engagement_stats=engagement_stats,
    )

    # Set auth cookie if key provided via query param
    if DASHBOARD_API_KEY and request.args.get("key") == DASHBOARD_API_KEY:
        from flask import make_response
        r = make_response(resp)
        r.set_cookie("joy_auth", DASHBOARD_API_KEY, httponly=True, samesite="Lax", max_age=86400)
        return r

    return resp


@app.route("/approve-send/<int:item_id>", methods=["POST"])
@require_auth
def approve_and_send(item_id):
    """Approve outreach and actually send the email / queue LinkedIn DM.

    This is the key Phase 3 wiring: approve -> send_message -> log_outreach -> update DB.
    """
    if _is_rate_limited("approve-send"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429

    conn = get_connection()
    row = conn.execute("SELECT * FROM approval_queue WHERE id=?", (item_id,)).fetchone()
    if not row:
        return jsonify({"status": "error", "error": "Item not found"}), 404

    item = dict(row)

    # Mark as approved in DB
    approve_item(item_id)

    # Build lead and message for sending
    lead = {
        "name": item["lead_name"],
        "email": item["lead_email"],
        "linkedin_url": "",  # Will use email channel primarily
    }
    message = {
        "subject": f"Quick note for {item['lead_name'].split()[0] if item['lead_name'] else 'you'}",
        "body": item["outreach_draft"],
    }

    # Parse subject from draft if present (drafts may include "Subject: ...")
    draft = item["outreach_draft"]
    if draft.startswith("Subject:"):
        lines = draft.split("\n", 1)
        message["subject"] = lines[0].replace("Subject:", "").strip()
        if len(lines) > 1:
            message["body"] = lines[1].strip()

    channel = item.get("channel", "email") or "email"

    # Actually send
    send_result = send_message(lead, message, channel=channel)

    # Persist to outreach_log
    try:
        lead_id = upsert_lead(conn, lead, score=item.get("lead_score", 0.0),
                              tier=item.get("lead_tier", "unknown"))
        log_outreach(conn, lead_id, channel, "outreach", send_result.get("status", "unknown"))
    except Exception as e:
        logger.warning("Failed to log outreach: %s", e)

    return jsonify({
        "status": send_result.get("status", "sent"),
        "send_status": send_result.get("status", "sent"),
        "channel": channel,
        "id": item_id,
    })


@app.route("/approve/<int:item_id>", methods=["POST"])
@require_auth
def approve(item_id):
    """Mark as approved without sending (legacy endpoint)."""
    if _is_rate_limited("approve"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429
    approve_item(item_id)
    return jsonify({"status": "approved", "id": item_id})


@app.route("/reject/<int:item_id>", methods=["POST"])
@require_auth
def reject(item_id):
    if _is_rate_limited("reject"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429
    reject_item(item_id)
    return jsonify({"status": "rejected", "id": item_id})


@app.route("/api/pending")
@require_auth
def api_pending():
    if _is_rate_limited("api-pending"):
        return jsonify({"error": "Rate limited"}), 429
    return jsonify(get_pending_approvals())


@app.route("/api/schedule")
@require_auth
def api_schedule():
    if _is_rate_limited("api-schedule"):
        return jsonify({"error": "Rate limited"}), 429
    return jsonify(get_next_runs(scheduler, n=10))


@app.route("/api/run-pipeline", methods=["POST"])
@require_auth
def api_run_pipeline():
    """Explicit trigger to re-run the full pipeline (refreshes cache)."""
    if _is_rate_limited("run-pipeline"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429

    try:
        with _cache_lock:
            _pipeline_cache["running"] = True

        results, kpis, tier_counts, route_counts, accuracy, elapsed = asyncio.run(run_pipeline_async())

        with _cache_lock:
            _pipeline_cache["results"] = results
            _pipeline_cache["kpis"] = kpis
            _pipeline_cache["tier_counts"] = tier_counts
            _pipeline_cache["route_counts"] = route_counts
            _pipeline_cache["accuracy"] = accuracy
            _pipeline_cache["elapsed"] = elapsed
            _pipeline_cache["timestamp"] = time.monotonic()
            _pipeline_cache["running"] = False

        return jsonify({
            "status": "ok",
            "total": len(results),
            "elapsed": elapsed,
        })
    except Exception as e:
        with _cache_lock:
            _pipeline_cache["running"] = False
        return jsonify({"status": "error", "error": str(e)})


@app.route("/execute/<int:item_id>", methods=["POST"])
@require_auth
def execute_engagement(item_id):
    """Approve an engagement item and dispatch it via the appropriate poster."""
    if _is_rate_limited("execute"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429

    conn = get_connection()
    row = conn.execute("SELECT * FROM approval_queue WHERE id=?", (item_id,)).fetchone()
    if not row:
        return jsonify({"status": "error", "error": "Item not found"}), 404

    item = dict(row)
    action_type = item.get("action_type", "")
    text = item.get("outreach_draft", "")
    target_id = item.get("target_post_id", "")
    platform = item.get("platform", "")

    # Approve first
    approve_item(item_id)

    result = {"status": "executed", "post_id": ""}
    try:
        if action_type == "x_reply":
            from x_poster import reply_to_tweet
            r = reply_to_tweet(target_id, text)
            result["post_id"] = r.get("reply_id", "")
        elif action_type == "x_tweet":
            from x_poster import post_tweet
            r = post_tweet(text)
            result["post_id"] = r.get("tweet_id", "")
        elif action_type == "x_quote":
            from x_poster import quote_tweet
            r = quote_tweet(target_id, text)
            result["post_id"] = r.get("tweet_id", "")
        elif action_type == "li_comment":
            from linkedin_poster import comment_on_post
            r = comment_on_post(target_id, text)
            result["post_id"] = r.get("comment_urn", "")
        elif action_type == "li_post":
            from linkedin_poster import post_update
            r = post_update(text)
            result["post_id"] = r.get("post_urn", "")
        else:
            result = {"status": "approved", "post_id": ""}
            return jsonify(result)

        log_engagement(
            platform=platform,
            action_type=action_type,
            target_post_id=target_id,
            our_post_id=result["post_id"],
            our_post_text=text,
            lead_name=item.get("lead_name", ""),
            status=r.get("status", "sent"),
        )
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    return jsonify(result)


@app.route("/api/discover", methods=["POST"])
@require_auth
def api_discover():
    """On-demand multi-source lead discovery scan.

    Fixed: runs discovered leads through full graph pipeline (not just hunt).
    """
    if _is_rate_limited("discover"):
        return jsonify({"status": "error", "error": "Rate limited"}), 429

    try:
        from lead_sources import get_configured_sources, discover_all
        from config import ICP_KEYWORDS

        keyword = ICP_KEYWORDS[0] if ICP_KEYWORDS else "voice AI"
        sources = get_configured_sources()
        leads = discover_all(keyword, limit_per_source=20) if sources else []

        # Run discovered leads through the full graph pipeline
        from graph import sales_graph
        queued = 0

        for lead in leads:
            if not lead.get("name") or not (lead.get("email") or lead.get("x_username")):
                continue

            try:
                # Full graph: outreach_hunter -> auditor -> closer/follow-up
                state = {
                    "current_lead": lead,
                    "lead_tier": "",
                    "lead_status": "cold",
                    "lead_score": 0.0,
                    "error": None,
                }
                final_state = sales_graph.invoke(state)

                # Queue for approval if not disqualified
                tier = final_state.get("lead_tier", "disqualified")
                dm = final_state.get("personalized_dm", "")
                if tier != "disqualified" and dm:
                    enriched = final_state.get("current_lead", lead)
                    queue_for_approval({
                        "lead_name": enriched.get("name", lead.get("name", "")),
                        "lead_email": enriched.get("email", lead.get("email", "")),
                        "lead_tier": tier,
                        "lead_score": final_state.get("lead_score", 0.0),
                        "channel": final_state.get("channel", ""),
                        "outreach_draft": dm,
                        "source": lead.get("source", "discovery"),
                    })
                    queued += 1
            except Exception as e:
                logger.warning("Failed to process discovered lead %s: %s", lead.get("name"), e)

        return jsonify({
            "status": "ok",
            "count": len(leads),
            "queued": queued,
            "sources": len(sources),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "count": 0, "sources": 0})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "scheduler": scheduler.running})


if __name__ == "__main__":
    from config import validate_config
    warnings = validate_config()
    for w in warnings:
        logger.warning("Config: %s", w)
    app.run(host="0.0.0.0", port=5001, debug=False)
