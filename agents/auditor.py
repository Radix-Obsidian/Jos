"""Auditor - track KPIs and suggest improvements.

Tracks: response rate, close rate, delivery stats, pipeline health.
"""
from __future__ import annotations

import ledger


def audit_pipeline(state: dict) -> dict:
    """Audit the current pipeline state and generate KPI entries.

    Args:
        state: Current SalesState dict

    Returns:
        Dict with kpi_summary and suggestions
    """
    lead = state.get("current_lead", {})
    tier = state.get("lead_tier", "unknown")
    status = state.get("lead_status", "cold")
    score = state.get("lead_score", 0.0)
    send_result = state.get("send_result", {})

    kpi_entries = []

    # Track lead qualification
    kpi_entries.append(f"LEAD: {lead.get('name', 'Unknown')} | tier={tier} score={score:.2f} status={status}")

    # Track outreach delivery
    if send_result:
        send_status = send_result.get("status", "unknown")
        channel = send_result.get("channel", "unknown")
        kpi_entries.append(f"OUTREACH: {channel} -> {send_status}")

    # Track close attempts
    close_action = state.get("close_action", "")
    if close_action:
        close_result = state.get("close_result", {})
        close_status = close_result.get("status", "unknown")
        kpi_entries.append(f"CLOSE: {close_action} -> {close_status}")

    # Generate suggestions
    suggestions = generate_suggestions(tier, status, score, send_result)
    if suggestions:
        kpi_entries.append(f"SUGGESTION: {suggestions}")

    for entry in kpi_entries:
        ledger.log(f"[AUDIT] {entry}")

    return {
        "kpi_entries": kpi_entries,
        "suggestions": suggestions,
        "lead_status": determine_post_audit_status(status, send_result),
    }


def generate_suggestions(tier: str, status: str, score: float,
                         send_result: dict) -> str:
    """Generate improvement suggestions based on pipeline data.

    Returns:
        Suggestion string (empty if none)
    """
    suggestions = []

    if tier == "nurture" and score >= 0.35:
        suggestions.append("Lead close to self_serve threshold - consider personal touch")

    if send_result.get("status") == "failed":
        suggestions.append("Delivery failed - try alternate channel")

    if status == "cold" and tier in ("enterprise", "self_serve"):
        suggestions.append("Qualified but cold - prioritize follow-up")

    return "; ".join(suggestions)


def determine_post_audit_status(current_status: str, send_result: dict) -> str:
    """Determine lead status after audit.

    - If outreach was sent successfully and lead was cold -> still cold (await response)
    - If send failed -> cold
    - hot/responded stay as-is
    """
    if current_status in ("hot", "responded"):
        return current_status

    if send_result.get("status") == "sent":
        return "cold"  # Awaiting response

    return current_status


def calculate_batch_kpis(states: list[dict]) -> dict:
    """Calculate aggregate KPIs across a batch of processed leads.

    Args:
        states: List of final pipeline states

    Returns:
        Dict with aggregate KPIs
    """
    total = len(states)
    if total == 0:
        return {
            "total_processed": 0,
            "hot_leads": 0,
            "cold_leads": 0,
            "responded": 0,
            "delivery_rate": 0.0,
            "close_rate": 0.0,
        }

    hot = sum(1 for s in states if s.get("lead_status") == "hot")
    cold = sum(1 for s in states if s.get("lead_status") == "cold")
    responded = sum(1 for s in states if s.get("lead_status") == "responded")
    sent = sum(1 for s in states if s.get("send_result", {}).get("status") == "sent")
    closed = sum(1 for s in states if s.get("close_action") in ("book_demo", "payment_link")
                 and s.get("close_result", {}).get("status") in ("booked", "sent"))

    return {
        "total_processed": total,
        "hot_leads": hot,
        "cold_leads": cold,
        "responded": responded,
        "delivery_rate": sent / total if total > 0 else 0.0,
        "close_rate": closed / total if total > 0 else 0.0,
    }
