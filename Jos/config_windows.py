"""
Windows-specific configuration for Jos Sales Automation
Optimized for development/testing on Windows hardware
"""

import os
from pathlib import Path

# Platform detection
WINDOWS_MODE = True
MAC_MODE = False
PLATFORM = "windows"

# Paths (Windows-specific)
BASE_DIR = Path(r"C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos")
DATABASE_PATH = Path(r"C:\Users\autre\.openclaw\jos_db.sqlite")
LOG_PATH = Path(r"C:\Users\autre\.openclaw\jos_logs")
CACHE_PATH = Path(r"C:\Users\autre\.openclaw\jos_cache")

# Create directories if they don't exist
for path in [DATABASE_PATH.parent, LOG_PATH, CACHE_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# API Keys (from environment variables)
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
GMAIL_API_KEY = os.getenv("GMAIL_API_KEY", "")
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "")

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789"
OPENCLAW_GATEWAY_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")

# Dashboard
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 5000
DASHBOARD_DEBUG = True

# Database
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
DATABASE_POOL_SIZE = 5
DATABASE_MAX_OVERFLOW = 10

# Scheduler (Windows - development mode)
SCHEDULER_TIMEZONE = "US/Eastern"
SCHEDULER_JOBS = {
    "scan_x": {
        "trigger": "interval",
        "hours": 1,
        "enabled": True,
        "description": "Scan X for voice-coding complaints"
    },
    "follow_up": {
        "trigger": "cron",
        "hour": "9,17",
        "minute": "0",
        "enabled": True,
        "description": "Send follow-up messages (day 3/7)"
    },
    "dashboard_sync": {
        "trigger": "interval",
        "minutes": 5,
        "enabled": True,
        "description": "Sync dashboard metrics"
    }
}

# Logging
LOG_LEVEL = "DEBUG"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOG_PATH / "jos_windows.log"

# LangGraph Configuration
LANGGRAPH_TIMEOUT = 30
LANGGRAPH_MAX_RETRIES = 3
LANGGRAPH_WORKERS = 4

# X/Twitter Configuration
X_KEYWORDS = [
    "voice cutoff",
    "Windsurf timeout",
    "Cursor voice limit",
    "Wispr Flow frustration",
    "voice to code",
    "voice coding",
    "voice assistant"
]

X_SEARCH_LIMIT = 50
X_RATE_LIMIT_DELAY = 2

# Outreach Configuration
OUTREACH_DM_TEMPLATE = """
Hi {name},

I noticed you mentioned {pain_point} — sounds frustrating. 

We're launching Voco V2 beta at $39/mo (only 10 founding seats left, rising to $59 soon). It's built for technical founders who want voice-to-code without the cutoffs.

Want to chat? Happy to show you a quick demo.

— Queen B
"""

OUTREACH_FOLLOW_UP_DAYS = [3, 7]
OUTREACH_BATCH_SIZE = 5

# Lead Scoring
LEAD_SCORE_THRESHOLD = 0.6
LEAD_TIERS = {
    "hot": 0.8,
    "warm": 0.6,
    "cold": 0.0
}

# Email Configuration
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_SENDER = GMAIL_SENDER
EMAIL_REPORT_RECIPIENTS = [GMAIL_SENDER]
EMAIL_REPORT_SCHEDULE = "daily"

# Reporting
REPORT_METRICS = [
    "leads_found",
    "outreach_sent",
    "responses_received",
    "response_rate",
    "hot_leads",
    "meetings_booked"
]

REPORT_FREQUENCY = "daily"
REPORT_TIME = "18:00"  # 6 PM ET

# Windows-specific optimizations
WINDOWS_OPTIMIZATIONS = {
    "use_thread_pool": True,
    "thread_pool_size": 4,
    "cache_enabled": True,
    "cache_ttl": 3600,
    "batch_processing": True,
    "batch_size": 10
}

# Feature flags
FEATURES = {
    "x_monitoring": True,
    "email_outreach": True,
    "follow_up_automation": True,
    "lead_scoring": True,
    "dashboard": True,
    "peekaboo_ui_automation": False,  # macOS only
    "things_integration": False,  # macOS only
    "imsg_integration": False  # macOS only
}
