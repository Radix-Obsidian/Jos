"""LinkedIn engagement — post, comment, and connect as the authenticated user.

Uses linkedin-api (unofficial) for V1. All actions queue for approval first.
Gracefully degrades if library not installed or credentials missing.
"""
from __future__ import annotations

import os

import ledger

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from linkedin_api import Linkedin
    HAS_LINKEDIN = True
except ImportError:
    HAS_LINKEDIN = False

LI_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LI_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

_client = None


def get_client() -> object | None:
    """Get authenticated LinkedIn client (singleton, lazy init)."""
    global _client
    if not HAS_LINKEDIN:
        ledger.log("linkedin-api not installed — LinkedIn posting disabled")
        return None
    if not LI_EMAIL or not LI_PASSWORD:
        return None
    if _client is None:
        try:
            _client = Linkedin(LI_EMAIL, LI_PASSWORD)
            ledger.log("LinkedIn client authenticated")
        except Exception as e:
            ledger.log(f"LinkedIn auth failed: {e}")
            return None
    return _client


def post_update(text: str) -> dict:
    """Post a LinkedIn update. Returns {status, post_urn, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "post_urn": "", "error": "LinkedIn client not configured"}
    try:
        result = client.post(text)
        post_urn = str(result) if result else ""
        ledger.log(f"Posted LinkedIn update: {post_urn}")
        return {"status": "sent", "post_urn": post_urn, "error": ""}
    except Exception as e:
        ledger.log(f"LinkedIn post failed: {e}")
        return {"status": "failed", "post_urn": "", "error": str(e)}


def comment_on_post(post_urn: str, text: str) -> dict:
    """Comment on a LinkedIn post. Returns {status, comment_urn, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "comment_urn": "", "error": "LinkedIn client not configured"}
    try:
        result = client.comment(post_urn, text)
        comment_urn = str(result) if result else ""
        ledger.log(f"Commented on LinkedIn post {post_urn}")
        return {"status": "sent", "comment_urn": comment_urn, "error": ""}
    except Exception as e:
        ledger.log(f"LinkedIn comment failed: {e}")
        return {"status": "failed", "comment_urn": "", "error": str(e)}


def send_connection_request(profile_id: str, message: str = "") -> dict:
    """Send a connection request. Returns {status, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "error": "LinkedIn client not configured"}
    try:
        client.add_connection(profile_id, message=message)
        ledger.log(f"Sent connection request to {profile_id}")
        return {"status": "sent", "error": ""}
    except Exception as e:
        ledger.log(f"LinkedIn connect failed: {e}")
        return {"status": "failed", "error": str(e)}


def get_profile(profile_id: str) -> dict:
    """Get a LinkedIn profile for enrichment. Returns profile dict or empty."""
    client = get_client()
    if not client:
        return {}
    try:
        profile = client.get_profile(profile_id)
        return profile or {}
    except Exception as e:
        ledger.log(f"LinkedIn profile fetch failed: {e}")
        return {}
