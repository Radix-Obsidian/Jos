"""Closer Manager - detect hot leads, generate closing scripts, book meetings.

Enhanced closer with hot-lead detection and closing script generation.
"""
from __future__ import annotations

import requests as http_requests

import ledger
from config import PRODUCT


def close_deal(lead: dict, tier: str) -> dict:
    """Execute close action based on lead tier.

    Args:
        lead: Qualified lead dict
        tier: "enterprise", "self_serve", or "nurture"

    Returns:
        Dict with action taken, result, and closing_script
    """
    action = decide_close_action(tier)
    closing_script = generate_closing_script(lead, tier, action)

    if action == "book_demo":
        result = book_demo(lead)
        result["action"] = "book_demo"
    elif action == "payment_link":
        result = send_payment_link(lead)
        result["action"] = "payment_link"
    else:
        ledger.log(f"No close action for {lead['name']} ({tier})")
        result = {"action": "none", "status": "skipped"}

    result["closing_script"] = closing_script
    return result


def decide_close_action(tier: str) -> str:
    """Decide close action based on tier."""
    if tier == "enterprise":
        return "book_demo"
    elif tier == "self_serve":
        return "payment_link"
    return "none"


def is_hot_lead(lead: dict, score: float, status: str) -> bool:
    """Detect if a lead is hot (ready to close).

    Hot signals:
    - Enterprise tier with high score (>= 0.8)
    - Status is "responded"
    - Status is already "hot"
    """
    if status in ("hot", "responded"):
        return True
    if score >= 0.8:
        return True
    return False


def generate_closing_script(lead: dict, tier: str, action: str) -> str:
    """Generate a closing script/message for the lead.

    Args:
        lead: Lead dict
        tier: Lead tier
        action: Close action (book_demo/payment_link/none)

    Returns:
        Closing script text
    """
    first_name = lead["name"].split()[0]
    company = lead.get("company", "your team")

    if action == "book_demo":
        script = (
            f"Hi {first_name},\n\n"
            f"I'd love to show you exactly how {PRODUCT['name']} can help "
            f"{company} ship voice features faster.\n\n"
            f"I've set up a 15-min demo slot just for you. "
            f"You can pick a time that works: {PRODUCT['demo_url']}\n\n"
            f"Looking forward to connecting!\n\n"
            f"Best,\nJoy\nVoco V2 Team"
        )
    elif action == "payment_link":
        script = (
            f"Hey {first_name},\n\n"
            f"Ready to get started? {PRODUCT['name']} is available at "
            f"{PRODUCT['price_self_serve']} with everything you need.\n\n"
            f"Get started here: {PRODUCT['payment_url']}\n\n"
            f"Any questions, I'm right here.\n\n"
            f"Best,\nJoy\nVoco V2 Team"
        )
    else:
        script = ""

    if script:
        ledger.log(f"Closing script generated for {lead['name']} ({action})")

    return script


def book_demo(lead: dict) -> dict:
    """Book a demo call via Calendly API."""
    try:
        resp = http_requests.post(
            PRODUCT["demo_url"],
            json={"name": lead["name"], "email": lead["email"]},
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            ledger.log(f"Demo booked for {lead['name']}: {data.get('url', 'N/A')}")
            return {
                "status": "booked",
                "url": data.get("url", PRODUCT["demo_url"]),
                "lead": lead["name"],
            }

        ledger.log(f"Demo booking failed for {lead['name']}: HTTP {resp.status_code}")
        return {"status": "failed", "error": f"HTTP {resp.status_code}"}

    except Exception as e:
        ledger.log(f"Demo booking error for {lead['name']}: {e}")
        return {"status": "failed", "error": str(e)}


def send_payment_link(lead: dict) -> dict:
    """Send Stripe payment link to self-serve lead."""
    payment_url = PRODUCT["payment_url"]
    ledger.log(f"Payment link sent to {lead['name']}: {payment_url}")

    return {
        "status": "sent",
        "url": payment_url,
        "lead": lead["name"],
    }
