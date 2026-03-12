"""Follow-Up Architect - track leads and send timed follow-ups.

Uses local LLM (MLX) for step-aware follow-up generation with template fallback.
Combines: message sending + follow-up scheduling + tracking.
Email: tries SMTP first, falls back to Gmail API if SMTP fails.
"""
from __future__ import annotations

import base64
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

import ledger
from config import SMTP, FOLLOW_UP_DAYS, PRODUCT
from llm import (
    generate_with_fallback, build_follow_up_prompt,
    parse_email_output, SYSTEM_FOLLOW_UP,
)

logger = logging.getLogger("joy.followup")


# ---------- Message Sending ----------

def send_message(lead: dict, message: dict, channel: str = "email") -> dict:
    """Send a message via the specified channel."""
    if channel == "linkedin":
        return send_linkedin(lead, message)
    return send_email(lead, message)


def send_email(lead: dict, message: dict) -> dict:
    """Send email via SMTP, falling back to Gmail API if SMTP fails."""
    msg = MIMEMultipart()
    msg["From"] = SMTP["from_email"]
    msg["To"] = lead["email"]
    msg["Subject"] = message["subject"]
    msg.attach(MIMEText(message["body"], "plain"))

    smtp_err = None

    # --- Try SMTP first ---
    try:
        with smtplib.SMTP(SMTP["host"], SMTP["port"]) as server:
            if SMTP.get("username"):
                server.starttls()
                server.login(SMTP["username"], SMTP["password"])
            server.send_message(msg)

        ledger.log(f"Email sent to {lead['email']} via SMTP")
        return {
            "status": "sent",
            "channel": "email",
            "method": "smtp",
            "recipient": lead["email"],
        }
    except Exception as e:
        smtp_err = e
        logger.warning("SMTP failed for %s: %s — trying Gmail API", lead.get("email"), e)

    # --- Fallback: Gmail API with OAuth2 ---
    try:
        _send_via_gmail_api(msg)
        ledger.log(f"Email sent to {lead['email']} via Gmail API")
        return {
            "status": "sent",
            "channel": "email",
            "method": "gmail_api",
            "recipient": lead["email"],
        }
    except Exception as api_err:
        ledger.log(f"Email failed to {lead.get('email', '?')}: SMTP and Gmail API both failed")
        return {
            "status": "failed",
            "channel": "email",
            "error": f"SMTP: {smtp_err} | Gmail API: {api_err}",
        }


def _send_via_gmail_api(mime_message: MIMEMultipart) -> dict:
    """Send a MIMEMultipart message using the Gmail API + OAuth2 refresh token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"),
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )

    service = build("gmail", "v1", credentials=creds)
    raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
    return service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()


def send_linkedin(lead: dict, message: dict) -> dict:
    """Queue LinkedIn DM (manual send for V1)."""
    ledger.log(f"LinkedIn DM queued for {lead['name']} ({lead.get('linkedin_url', 'no URL')})")

    return {
        "status": "queued",
        "channel": "linkedin",
        "recipient": lead.get("linkedin_url", ""),
        "note": "Manual send required for V1 - LinkedIn API integration in V2",
    }


# ---------- Follow-Up Scheduling ----------

def schedule_follow_up(lead: dict, tier: str) -> dict:
    """Create a follow-up entry for a lead."""
    due_date = datetime.now() + timedelta(days=FOLLOW_UP_DAYS[0])
    entry = {
        "lead": lead,
        "tier": tier,
        "step": 1,
        "due_date": due_date,
    }
    ledger.log(f"Follow-up scheduled for {lead['name']} (step 1, due {due_date.strftime('%Y-%m-%d')})")
    return entry


def advance_follow_up(entry: dict) -> dict | None:
    """Move follow-up to next step. Returns None if sequence complete."""
    current_step = entry["step"]

    if current_step >= len(FOLLOW_UP_DAYS):
        ledger.log(f"Follow-up sequence complete for {entry['lead']['name']}")
        return None

    next_step = current_step + 1
    due_date = datetime.now() + timedelta(days=FOLLOW_UP_DAYS[next_step - 1])

    new_entry = {
        "lead": entry["lead"],
        "tier": entry["tier"],
        "step": next_step,
        "due_date": due_date,
    }
    ledger.log(f"Follow-up advanced for {entry['lead']['name']} (step {next_step})")
    return new_entry


def get_due_follow_ups(queue: list[dict]) -> list[dict]:
    """Filter follow-up queue for entries that are due now."""
    now = datetime.now()
    return [entry for entry in queue if entry["due_date"] <= now]


def generate_follow_up_message(lead: dict, step: int, tier: str) -> dict:
    """Generate follow-up message using LLM with step-aware template fallback.

    Returns:
        Dict with subject and body (follow_up_text)
    """
    first_name = lead["name"].split()[0] if lead.get("name") else "there"
    company = lead.get("company", "your team")

    # Template fallback (original step-based logic)
    if step == 1:
        fb_subject = f"Following up - {PRODUCT['name']} for {company}"
        fb_body = (
            f"Hi {first_name},\n\n"
            f"Just wanted to follow up on my previous message about {PRODUCT['name']}. "
            f"I think it could be a great fit for what {company} is building.\n\n"
            f"Would you be open to a quick chat this week?\n\n"
            f"Best,\nJoy\nVoco V2 Team"
        )
    elif step == 2:
        fb_subject = f"{first_name}, one more thought about {company}"
        fb_body = (
            f"Hi {first_name},\n\n"
            f"I know you're busy, so I'll keep this brief. "
            f"Teams similar to {company} have cut their voice feature development time in half "
            f"with {PRODUCT['name']}.\n\n"
            f"Happy to share a quick case study if useful.\n\n"
            f"Best,\nJoy\nVoco V2 Team"
        )
    else:
        fb_subject = f"Closing the loop - {first_name}"
        fb_body = (
            f"Hi {first_name},\n\n"
            f"This is my last note on this. I don't want to be a pest.\n\n"
            f"If {PRODUCT['name']} isn't the right fit for {company} right now, "
            f"no worries at all. But if timing changes, I'm here.\n\n"
            f"Wishing you and the {company} team all the best.\n\n"
            f"Best,\nJoy\nVoco V2 Team"
        )

    fallback = f"Subject: {fb_subject}\n\n{fb_body}"

    # LLM generation
    prompt = build_follow_up_prompt(lead, step, tier)
    raw = generate_with_fallback(prompt, SYSTEM_FOLLOW_UP, fallback)

    parsed = parse_email_output(raw)
    subject = parsed["subject"] or fb_subject
    body = parsed["body"] or fb_body

    logger.debug("Follow-up step %d for %s: LLM=%s", step, lead.get("name"), raw != fallback)
    return {"subject": subject, "body": body}


# ---------- Full Follow-Up Pipeline ----------

def architect_follow_up(lead: dict, tier: str, step: int = 1) -> dict:
    """Full follow-up architect pipeline: schedule + generate + optionally send.

    Returns:
        Dict with follow_up entry, message, and follow_up_text
    """
    entry = schedule_follow_up(lead, tier)
    msg = generate_follow_up_message(lead, step=step, tier=tier)

    return {
        "entry": entry,
        "message": msg,
        "follow_up_text": msg["body"],
        "step": step,
    }
