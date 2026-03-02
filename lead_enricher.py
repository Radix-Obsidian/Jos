"""Hunter.io email enrichment — find and verify lead emails.

Uses the Hunter.io Email Finder and Email Verifier APIs to:
1. Find professional emails from name + company domain
2. Verify email deliverability and get confidence scores

Domain enrichment results are cached in two layers:
- Process-level in-memory dict (fastest, cleared on restart)
- SQLite domain_cache table (persists across restarts)

This means each unique company domain hits Hunter's API at most once,
even if the pipeline runs 20x per page refresh.
"""
from __future__ import annotations

import os
import re

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import get_domain_cache, set_domain_cache

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
HUNTER_BASE = "https://api.hunter.io/v2"
VERIFICATION_THRESHOLD = 80

# Process-level in-memory cache: domain → {industry, employees}
# Avoids repeated SQLite lookups within a single pipeline run
_DOMAIN_CACHE: dict[str, dict] = {}


# ---------- Domain Search ----------

def domain_search(domain: str) -> dict:
    """Get company industry and employee count from Hunter.io domain search.

    Args:
        domain: Company domain (e.g. 'railway.app')

    Returns:
        {"industry": str, "employees": int}
    """
    if not domain or not HUNTER_API_KEY:
        return {"industry": "", "employees": 0}

    try:
        resp = requests.get(
            f"{HUNTER_BASE}/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"industry": "", "employees": 0}

        data = resp.json().get("data", {})
        return {
            "industry": data.get("industry") or "",
            "employees": data.get("employees") or 0,
        }
    except Exception:
        return {"industry": "", "employees": 0}


# ---------- Domain Extraction ----------

def _extract_domain(company: str) -> str:
    """Guess a company's domain from its name.

    'TechStartup' -> 'techstartup.com'
    'Acme Corp' -> 'acmecorp.com'
    'example.com' -> 'example.com'
    """
    if not company:
        return ""

    # Already a domain
    if "." in company and " " not in company:
        return company.lower()

    # Strip common legal suffixes (only when preceded by comma/space at end)
    cleaned = re.sub(r',?\s+(Inc|LLC|Ltd|GmbH|SA)\.?$', '', company, flags=re.IGNORECASE)
    domain = re.sub(r'[^a-zA-Z0-9]', '', cleaned).lower()
    return f"{domain}.com" if domain else ""


# ---------- Email Finder ----------

def find_email(domain: str, first_name: str, last_name: str) -> dict:
    """Find a professional email using Hunter.io Email Finder.

    Args:
        domain: Company domain (e.g. 'voiceflow.com')
        first_name: Lead's first name
        last_name: Lead's last name

    Returns:
        {"email": str, "score": int}
    """
    try:
        resp = requests.get(
            f"{HUNTER_BASE}/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": HUNTER_API_KEY,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            return {"email": "", "score": 0}

        data = resp.json().get("data", {})
        email = data.get("email") or ""
        score = data.get("score") or 0

        return {"email": email, "score": score}

    except Exception:
        return {"email": "", "score": 0}


# ---------- Email Verifier ----------

def verify_email(email: str) -> dict:
    """Verify an email address using Hunter.io Email Verifier.

    Args:
        email: Email address to verify

    Returns:
        {"score": int, "status": str}
    """
    try:
        resp = requests.get(
            f"{HUNTER_BASE}/email-verifier",
            params={
                "email": email,
                "api_key": HUNTER_API_KEY,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            return {"score": 0, "status": "error"}

        data = resp.json().get("data", {})
        return {
            "score": data.get("score", 0),
            "status": data.get("status", "unknown"),
        }

    except Exception:
        return {"score": 0, "status": "error"}


# ---------- Threshold ----------

def is_email_verified(score: int) -> bool:
    """Check if an email score meets the verification threshold (>= 80)."""
    return score >= VERIFICATION_THRESHOLD


# ---------- Full Enrichment ----------

def enrich_lead(lead: dict) -> dict:
    """Enrich a lead with Hunter.io email data.

    Flow:
    1. If lead already has email -> verify it
    2. If no email but has company -> find email via Hunter, then verify
    3. If no company -> skip

    Returns:
        Lead dict with email, email_confidence, verified_email added/updated
    """
    enriched = dict(lead)
    enriched.setdefault("email_confidence", 0)
    enriched.setdefault("verified_email", "")

    existing_email = lead.get("email", "")
    company = lead.get("company", "")

    # Case 1: Already have an email — just verify it
    if existing_email:
        result = verify_email(existing_email)
        enriched["email_confidence"] = result["score"]
        if is_email_verified(result["score"]):
            enriched["verified_email"] = existing_email
        return enriched

    # Case 2: No email but have company — find + verify
    if company:
        domain = _extract_domain(company)
        if not domain:
            return enriched

        name_parts = lead.get("name", "").split()
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[-1] if len(name_parts) > 1 else ""

        found = find_email(domain, first_name, last_name)
        if found["email"]:
            enriched["email"] = found["email"]
            # Now verify
            verification = verify_email(found["email"])
            enriched["email_confidence"] = verification["score"]
            if is_email_verified(verification["score"]):
                enriched["verified_email"] = found["email"]

        return enriched

    # Case 3: No company — can't enrich
    return enriched


def enrich_lead_with_domain(lead: dict, db_path: str = None) -> dict:
    """Enrich a lead with real industry and company size via Hunter domain search.

    Lookup order (stops at first hit to protect Hunter quota):
      1. Process-level in-memory dict (_DOMAIN_CACHE) — fastest
      2. SQLite domain_cache table — persists across restarts
      3. Hunter /domain-search API — consumes monthly quota

    Only fetches if industry or company_size not already set on the lead.

    Returns:
        Lead dict with industry and company_size populated if found
    """
    enriched = dict(lead)

    if enriched.get("industry") and enriched.get("company_size"):
        return enriched  # Already have both — skip everything

    company = enriched.get("company", "")
    if not company:
        return enriched

    domain = _extract_domain(company)
    if not domain:
        return enriched

    # Layer 1: in-memory cache (zero latency)
    if domain in _DOMAIN_CACHE:
        result = _DOMAIN_CACHE[domain]
    else:
        # Layer 2: SQLite persistent cache
        result = get_domain_cache(domain, db_path)
        if result is None:
            # Layer 3: Hunter API (consumes quota — last resort)
            result = domain_search(domain)
            # Persist so future runs skip the API call
            set_domain_cache(domain, result["industry"], result["employees"], db_path)
        # Populate in-memory cache regardless of source
        _DOMAIN_CACHE[domain] = result

    if result.get("industry") and not enriched.get("industry"):
        enriched["industry"] = result["industry"]
    if result.get("employees") and not enriched.get("company_size"):
        enriched["company_size"] = result["employees"]

    return enriched
