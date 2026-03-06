"""
Mac-specific configuration for Jos Sales Automation
Optimized for production/24-7 operation on Mac hardware
"""

import os
from pathlib import Path

# Platform detection
WINDOWS_MODE = False
MAC_MODE = True
PLATFORM = "mac"

# Paths (Mac-specific)
BASE_DIR = Path.home() / "openclaw-projects" / "Jos"
DATABASE_PATH = Path.home() / ".openclaw" / "jos_db.sqlite"
LOG_PATH = Path.home() / ".openclaw" / "jos_logs"
CACHE_PATH = Path.home() / ".openclaw" / "jos_cache"

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
DASHBOARD_DEBUG = False

# Database
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
DATABASE_POOL_SIZE = 10
DATABASE_MAX_OVERFLOW = 20

# Scheduler (Mac - production mode, 24/7)
SCHEDULER_TIMEZONE = "US/Eastern"
SCHEDULER_JOBS = {
    "scan_x": {
        "trigger": "interval",
        "minutes": 30,  # More frequent on Mac
        "enabled": True,
        "description": "Scan X for voice-coding complaints"
    },
    "follow_up": {
        "trigger": "cron",
        "hour": "9,13,17",  # More frequent follow-ups
        "minute": "0",
        "enabled": True,
        "description": "Send follow-up messages (day 3/7)"
    },
    "dashboard_sync": {
        "trigger": "interval",
        "minutes": 2,  # More frequent sync
        "enabled": True,
        "description": "Sync dashboard metrics"
    },
    "report_summary": {
        "trigger": "cron",
        "hour": "*",  # Every hour
        "minute": "0",
        "enabled": True,
        "description": "Email summary reports"
    },
    "lead_enrichment": {
        "trigger": "interval",
        "minutes": 15,
        "enabled": True,
        "description": "Enrich lead data with additional context"
    }
}

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOG_PATH / "jos_mac.log"

# LangGraph Configuration
LANGGRAPH_TIMEOUT = 60
LANGGRAPH_MAX_RETRIES = 5
LANGGRAPH_WORKERS = 8

# X/Twitter Configuration
X_KEYWORDS = [
    "voice cutoff",
    "Windsurf timeout",
    "Cursor voice limit",
    "Wispr Flow frustration",
    "voice to code",
    "voice coding",
    "voice assistant",
    "coding assistant",
    "AI coding"
]

X_SEARCH_LIMIT = 100
X_RATE_LIMIT_DELAY = 1

# Outreach Configuration
OUTREACH_DM_TEMPLATE = """
Hi {name},

I noticed you mentioned {pain_point} — sounds frustrating. 

We're launching Voco V2 beta at $39/mo (only 10 founding seats left, rising to $59 soon). It's built for technical founders who want voice-to-code without the cutoffs.

Want to chat? Happy to show you a quick demo.

— Queen B
"""

OUTREACH_FOLLOW_UP_DAYS = [3, 7]
OUTREACH_BATCH_SIZE = 10

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
EMAIL_REPORT_SCHEDULE = "hourly"

# Reporting
REPORT_METRICS = [
    "leads_found",
    "outreach_sent",
    "responses_received",
    "response_rate",
    "hot_leads",
    "meetings_booked",
    "conversion_rate",
    "avg_response_time"
]

REPORT_FREQUENCY = "hourly"
REPORT_TIME = "*:00"  # Every hour

# Mac-specific optimizations
MAC_OPTIMIZATIONS = {
    "use_async": True,
    "use_multiprocessing": True,
    "process_pool_size": 8,
    "cache_enabled": True,
    "cache_ttl": 1800,
    "batch_processing": True,
    "batch_size": 20,
    "memory_optimization": True
}

# macOS-specific integrations
PEEKABOO_ENABLED = True
PEEKABOO_CONFIG = {
    "capture_screenshots": True,
    "ui_automation": True,
    "gesture_support": True
}

THINGS_ENABLED = True
THINGS_CONFIG = {
    "sync_leads_to_tasks": True,
    "create_follow_up_tasks": True,
    "project_name": "Voco Sales"
}

IMSG_ENABLED = True
IMSG_CONFIG = {
    "send_follow_ups": False,  # Use email instead
    "monitor_responses": False
}

# Feature flags
FEATURES = {
    "x_monitoring": True,
    "email_outreach": True,
    "follow_up_automation": True,
    "lead_scoring": True,
    "dashboard": True,
    "peekaboo_ui_automation": True,  # macOS enabled
    "things_integration": True,  # macOS enabled
    "imsg_integration": True,  # macOS enabled
    "advanced_analytics": True,
    "predictive_scoring": True,
    "24_7_operation": True
}

# Production settings
PRODUCTION_MODE = True
ENABLE_MONITORING = True
ENABLE_ALERTING = True
ALERT_THRESHOLD = 0.5  # Alert if response rate drops below 50%
