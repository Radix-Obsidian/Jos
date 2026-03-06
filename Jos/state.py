"""Sales pipeline state schema for LangGraph orchestration - V2 Architecture."""
from __future__ import annotations

from typing import TypedDict, List, Optional


class SalesState(TypedDict, total=False):
    """State that flows through every node in the sales pipeline.

    Agents: outreach_hunter, follow_up_architect, closer_manager, auditor.
    """

    # Lead data
    raw_leads: List[dict]
    current_lead: dict
    lead_text: str              # raw text/description about the lead
    lead_score: float
    lead_tier: str              # "enterprise" | "self_serve" | "nurture" | "disqualified"
    lead_status: str            # "hot" | "cold" | "responded"

    # Outreach (from outreach_hunter)
    personalized_dm: str        # generated DM text
    outreach_message: dict      # full message dict {"subject": ..., "body": ...}
    channel: str                # "email" | "linkedin"
    send_result: dict

    # Follow-up (from follow_up_architect)
    follow_up_text: str         # generated follow-up text
    follow_up_queue: List[dict]
    follow_up_step: int         # 1, 2, or 3

    # Closing (from closer_manager)
    closing_script: str         # generated closing message
    close_action: str           # "book_demo" | "payment_link" | "none"
    close_result: dict

    # X/Twitter enrichment
    x_post_text: str            # original tweet that triggered the lead
    verified_email: str         # Hunter.io verified email
    email_confidence: int       # Hunter.io confidence score (0-100)

    # Tracking (from auditor)
    kpi_log: List[str]          # KPI tracking entries
    ledger_log: List[str]
    error: Optional[str]
