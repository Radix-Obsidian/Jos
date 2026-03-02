"""Joy V1 Sales Rep - Main entry point (V2 Architecture)."""

import sys
from graph import sales_graph
from state import SalesState
import ledger


# 5 test leads (per revised spec)
TEST_LEADS = [
    {"name": "Sarah Chen", "title": "CTO", "company": "DataFlow AI", "email": "sarah@dataflow.ai", "linkedin_url": "https://linkedin.com/in/sarahchen"},
    {"name": "James Wu", "title": "VP Engineering", "company": "CloudSaaS", "email": "james@cloudsaas.com", "linkedin_url": "https://linkedin.com/in/jameswu"},
    {"name": "Emily Park", "title": "Founder", "company": "AI Startup", "email": "emily@aistartup.com", "linkedin_url": ""},
    {"name": "David Kim", "title": "Engineering Manager", "company": "TechCorp", "email": "david@techcorp.com", "linkedin_url": ""},
    {"name": "Mike Intern", "title": "Marketing Intern", "company": "RandomCo", "email": "mike@random.com", "linkedin_url": ""},
]


def run(dry_run: bool = False):
    """Execute the full sales pipeline.

    Args:
        dry_run: If True, use mock data and don't send real messages
    """
    print("\n" + "=" * 60)
    print("JOY V1 SALES REP - Voco V2 (V2 Architecture)")
    print("Agents: Outreach Hunter | Auditor | Closer Manager | Follow-Up Architect")
    print("=" * 60 + "\n")

    ledger.clear()

    if dry_run:
        print("[DRY RUN] Processing 5 test leads\n")

    leads = TEST_LEADS if dry_run else []

    for i, lead in enumerate(leads):
        print(f"\n--- Lead {i+1}/{len(leads)}: {lead['name']} ---")

        initial_state: SalesState = {
            "raw_leads": [],
            "current_lead": lead,
            "lead_text": "",
            "lead_score": 0.0,
            "lead_tier": "",
            "lead_status": "cold",
            "personalized_dm": "",
            "outreach_message": {},
            "channel": "",
            "send_result": {},
            "follow_up_text": "",
            "follow_up_queue": [],
            "follow_up_step": 1,
            "closing_script": "",
            "close_action": "",
            "close_result": {},
            "kpi_log": [],
            "ledger_log": [],
            "error": None,
        }

        try:
            result = sales_graph.invoke(initial_state)

            if result.get("error"):
                print(f"  Error: {result['error']}")
            else:
                print(f"  Tier: {result.get('lead_tier', 'N/A')}")
                print(f"  Status: {result.get('lead_status', 'N/A')}")
                print(f"  Close: {result.get('close_action', 'N/A')}")
                if result.get("closing_script"):
                    print(f"  Script: {result['closing_script'][:80]}...")

        except Exception as e:
            print(f"  Fatal error: {e}")

    print("\n")
    ledger.print_all()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
