"""Apollo.io People Search + Company Enrichment.

Free tier: 50 credits/month.  Each people-search costs 1 credit.
Env: APOLLO_API_KEY
"""
from __future__ import annotations

import os

import requests

import ledger
from db import get_source_cache, set_source_cache
from lead_sources.base import BaseSource

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
APOLLO_BASE = "https://api.apollo.io/v1"


class ApolloSource(BaseSource):
    name = "apollo"

    def is_configured(self) -> bool:
        return bool(APOLLO_API_KEY)

    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search Apollo People API for ICP-matching leads."""
        if not self.is_configured():
            return []

        cache_key = f"apollo:search:{keyword}:{limit}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        try:
            resp = requests.post(
                f"{APOLLO_BASE}/mixed_people/search",
                json={
                    "q_keywords": keyword,
                    "page": 1,
                    "per_page": min(limit, 25),
                    "person_titles": [
                        "CTO", "VP Engineering", "Head of Product",
                        "Founder", "CEO", "Engineering Manager",
                    ],
                },
                headers={"x-api-key": APOLLO_API_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                ledger.log(f"Apollo search HTTP {resp.status_code}")
                return []

            people = resp.json().get("people", []) or []
            leads = [self._person_to_lead(p) for p in people]
            set_source_cache(cache_key, self.name, leads)
            return leads

        except Exception as e:
            ledger.log(f"Apollo search error: {e}")
            return []

    def enrich_lead(self, lead: dict) -> dict:
        """Enrich with Apollo person match (email, title, company)."""
        enriched = dict(lead)
        if not self.is_configured():
            return enriched

        email = lead.get("email", "")
        name = lead.get("name", "")
        company = lead.get("company", "")
        if not (email or (name and company)):
            return enriched

        cache_key = f"apollo:enrich:{email or name + '|' + company}"
        cached = get_source_cache(cache_key)
        if cached:
            enriched.update(cached)
            return enriched

        try:
            params = {}
            if email:
                params["email"] = email
            else:
                parts = name.split()
                params["first_name"] = parts[0] if parts else ""
                params["last_name"] = parts[-1] if len(parts) > 1 else ""
                params["organization_name"] = company

            resp = requests.post(
                f"{APOLLO_BASE}/people/match",
                json=params,
                headers={"x-api-key": APOLLO_API_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                return enriched

            person = resp.json().get("person") or {}
            updates = {}
            if person.get("email") and not enriched.get("email"):
                updates["email"] = person["email"]
            if person.get("title") and not enriched.get("title"):
                updates["title"] = person["title"]
            if person.get("linkedin_url") and not enriched.get("linkedin_url"):
                updates["linkedin_url"] = person["linkedin_url"]
            org = person.get("organization") or {}
            if org.get("funding_stage"):
                updates["funding_stage"] = org["funding_stage"]
            if org.get("estimated_num_employees"):
                updates["company_size"] = org["estimated_num_employees"]

            set_source_cache(cache_key, self.name, updates)
            enriched.update(updates)
            return enriched

        except Exception as e:
            ledger.log(f"Apollo enrich error: {e}")
            return enriched

    def _person_to_lead(self, person: dict) -> dict:
        org = person.get("organization") or {}
        return self._make_lead(
            name=person.get("name", ""),
            title=person.get("title", ""),
            company=org.get("name", ""),
            email=person.get("email", ""),
            linkedin_url=person.get("linkedin_url", ""),
            source="apollo",
            source_url=person.get("linkedin_url", ""),
            source_confidence=0.9,
            raw_data=person,
            funding_stage=org.get("funding_stage", ""),
            company_size=org.get("estimated_num_employees", 0),
        )
