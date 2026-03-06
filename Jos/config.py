"""Voco V2 product config, ICP, and outreach templates.

User will replace placeholders with real product details.
"""
from __future__ import annotations

import os
import logging

# --- Product Info (PLACEHOLDER - user will fill in) ---
PRODUCT = {
    "name": "Voco V2",
    "tagline": "AI-powered voice platform for teams",
    "price_self_serve": "$49/mo",
    "price_enterprise": "Custom",
    "url": "https://itsvoco.com",
    "demo_url": "https://calendly.com/voco-demo",
    "payment_url": "https://buy.stripe.com/voco-v2",
}

# --- Ideal Customer Profile ---
ICP = {
    "titles": [
        "CTO", "VP Engineering", "Head of Product", "Engineering Manager",
        "Director of Engineering", "Technical Lead", "CEO", "Founder",
    ],
    "industries": [
        "SaaS", "AI/ML", "Developer Tools", "Fintech", "Healthcare Tech",
        "E-commerce", "Cybersecurity", "Cloud Infrastructure",
    ],
    "company_size_min": 10,
    "company_size_max": 500,
    "signals": [
        "recently raised funding",
        "hiring engineers",
        "using competitor tools",
        "posted about AI adoption",
    ],
}

# --- Pain Signal Keywords (X/social leads) ---
# Leads from X who mention these get a score boost even without company/title data
PAIN_SIGNALS = [
    "cancelled", "canceled", "unsubscribed", "dropped", "switched from",
    "moved to", "frustrat", "disappoint", "broken", "doesn't work",
    "voice coding", "voice command", "tool calling", "diminishing returns",
]
PAIN_SIGNAL_BOOST = 0.35  # Enough to push into self_serve tier minimum

# --- Outreach Templates ---
EMAIL_TEMPLATE = """Subject: {subject}

Hi {first_name},

{opening_line}

{value_prop}

{cta}

Best,
Joy
Voco V2 Team
"""

LINKEDIN_TEMPLATE = """Hi {first_name},

{opening_line}

{value_prop}

{cta}
"""

X_DM_TEMPLATE = """Hey {first_name} — {opening_line}

{value_prop}

{cta}
"""

# --- Follow-Up Schedule ---
FOLLOW_UP_DAYS = [3, 7, 14]  # Days after initial outreach

# --- Scoring Thresholds ---
SCORE_ENTERPRISE = 0.65
SCORE_SELF_SERVE = 0.4
SCORE_NURTURE = 0.2

# --- Competitor Companies (score near-zero → disqualified) ---
COMPETITORS = ["elevenlabs"]

# --- ICP Keywords for multi-source discovery + engagement scanning ---
ICP_KEYWORDS = [
    "voice AI", "speech recognition", "voice coding",
    "AI voice agent", "text to speech", "voice platform",
    "conversational AI", "voice assistant SDK",
]

# --- SMTP Config (PLACEHOLDER) ---
SMTP = {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": os.getenv("SMTP_USERNAME", ""),
    "password": os.getenv("SMTP_PASSWORD", ""),
    "from_email": os.getenv("SMTP_FROM", "joy@voco.ai"),
}

# --- LLM Config ---
LLM_MODEL = os.getenv("LLM_MODEL", "mlx-community/Llama-3.2-3B-Instruct-4bit")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "350"))

# --- Dashboard Auth ---
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def validate_config() -> list[str]:
    """Check config completeness. Returns list of warnings."""
    warnings = []
    if not SMTP["username"]:
        warnings.append("SMTP_USERNAME not set — email sending will fail")
    if not DASHBOARD_API_KEY:
        warnings.append("DASHBOARD_API_KEY not set — dashboard has no auth")
    return warnings
