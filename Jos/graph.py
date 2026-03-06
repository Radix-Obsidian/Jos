"""LangGraph sales pipeline orchestrator - V2 Architecture.

Flow: outreach_hunter → auditor → [conditional] → closer_manager | follow_up_architect | END
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from state import SalesState
from agents.outreach_hunter import hunt, scan_leads, qualify_lead, generate_outreach
from agents.follow_up_architect import (
    send_message, schedule_follow_up, generate_follow_up_message,
)
from agents.closer_manager import close_deal, is_hot_lead
from agents.auditor import audit_pipeline
import ledger


# ---------- Nodes ----------

def outreach_hunter_node(state: SalesState) -> SalesState:
    """Outreach Hunter: scan, qualify, and generate personalized DM."""
    try:
        lead = state.get("current_lead", {})
        if not lead or not lead.get("name"):
            # Try scanning for leads first
            keyword = lead.get("keyword", "AI SaaS startups")
            leads = scan_leads(keyword)
            if not leads:
                state["error"] = "No leads found"
                return state
            lead = leads[0]
            state["raw_leads"] = leads

        result = hunt(lead)
        enriched_lead = result["lead"]
        state["current_lead"] = enriched_lead
        state["lead_score"] = result["score"]
        state["lead_tier"] = result["tier"]
        state["lead_status"] = result["status"]
        state["personalized_dm"] = result.get("personalized_dm", "")

        # Persist X/enrichment fields
        if enriched_lead.get("x_post_text"):
            state["x_post_text"] = enriched_lead["x_post_text"]
        if enriched_lead.get("verified_email"):
            state["verified_email"] = enriched_lead["verified_email"]
        if enriched_lead.get("email_confidence"):
            state["email_confidence"] = enriched_lead["email_confidence"]

        if result.get("outreach"):
            state["outreach_message"] = result["outreach"]["message"]
            state["channel"] = result.get("channel", "email")

            # Send the message
            send_result = send_message(
                result["lead"], result["outreach"]["message"],
                channel=result.get("channel", "email")
            )
            state["send_result"] = send_result
            state["lead_text"] = (
                f"{lead.get('name', '')} | {lead.get('title', '')} | "
                f"{lead.get('company', '')} | score={result['score']:.2f}"
            )

        ledger.log(f"Hunter done: {lead.get('name', '?')} -> {result['tier']} ({result['status']})")
    except Exception as e:
        state["error"] = f"Outreach hunter failed: {e}"
    return state


def auditor_node(state: SalesState) -> SalesState:
    """Auditor: track KPIs and determine routing."""
    try:
        audit = audit_pipeline(state)

        kpi_log = state.get("kpi_log", [])
        kpi_log.extend(audit["kpi_entries"])
        state["kpi_log"] = kpi_log

        # Auditor can update lead_status based on analysis
        state["lead_status"] = audit["lead_status"]

        ledger.log(f"Audit complete: {len(audit['kpi_entries'])} KPI entries")
        if audit["suggestions"]:
            ledger.log(f"Suggestions: {audit['suggestions']}")
    except Exception as e:
        state["error"] = f"Audit failed: {e}"
    return state


def follow_up_architect_node(state: SalesState) -> SalesState:
    """Follow-Up Architect: schedule and generate follow-ups for cold leads."""
    try:
        lead = state.get("current_lead", {})
        tier = state.get("lead_tier", "nurture")
        step = state.get("follow_up_step", 1)

        entry = schedule_follow_up(lead, tier)
        msg = generate_follow_up_message(lead, step=step, tier=tier)
        state["outreach_message"] = msg
        state["follow_up_text"] = msg["body"]

        queue = state.get("follow_up_queue", [])
        queue.append(entry)
        state["follow_up_queue"] = queue

        ledger.log(f"Follow-up step {step} queued for {lead.get('name', '?')}")
    except Exception as e:
        state["error"] = f"Follow-up failed: {e}"
    return state


def closer_manager_node(state: SalesState) -> SalesState:
    """Closer Manager: close deals for hot leads."""
    try:
        lead = state.get("current_lead", {})
        tier = state.get("lead_tier", "self_serve")

        result = close_deal(lead, tier)
        state["close_action"] = result["action"]
        state["close_result"] = result
        state["closing_script"] = result.get("closing_script", "")
        ledger.log(f"Close: {result['action']} for {lead.get('name', '?')} -> {result.get('status')}")
    except Exception as e:
        state["error"] = f"Close failed: {e}"
    return state


# ---------- Conditional Edges ----------

def route_after_hunter(state: SalesState) -> str:
    """Route based on lead status after auditor review.

    - hot -> closer_manager
    - cold -> follow_up_architect
    - disqualified/error -> END
    """
    if state.get("error"):
        return END

    tier = state.get("lead_tier", "disqualified")
    status = state.get("lead_status", "cold")
    score = state.get("lead_score", 0.0)

    # Check if lead is hot (ready to close)
    lead = state.get("current_lead", {})
    if is_hot_lead(lead, score, status):
        return "closer_manager"

    # Qualified but cold -> follow up
    if tier in ("enterprise", "self_serve", "nurture"):
        return "follow_up_architect"

    # Disqualified -> end
    ledger.log(f"Lead disqualified, ending pipeline")
    return END


# ---------- Build Graph ----------

def build_sales_graph():
    """Construct the V2 sales pipeline graph.

    Flow: outreach_hunter → auditor → [conditional] → closer_manager | follow_up_architect | END
    """
    graph = StateGraph(SalesState)

    # Add nodes
    graph.add_node("outreach_hunter", outreach_hunter_node)
    graph.add_node("auditor", auditor_node)
    graph.add_node("follow_up_architect", follow_up_architect_node)
    graph.add_node("closer_manager", closer_manager_node)

    # Entry
    graph.set_entry_point("outreach_hunter")

    # Always audit after hunting
    graph.add_edge("outreach_hunter", "auditor")

    # Conditional: auditor -> closer_manager | follow_up_architect | END
    graph.add_conditional_edges(
        "auditor",
        route_after_hunter,
        {
            "closer_manager": "closer_manager",
            "follow_up_architect": "follow_up_architect",
            END: END,
        },
    )

    # Terminal edges
    graph.add_edge("follow_up_architect", END)
    graph.add_edge("closer_manager", END)

    return graph.compile()


# Singleton
sales_graph = build_sales_graph()
