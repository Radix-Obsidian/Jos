"""People Data Labs (PDL) lead discovery + enrichment.

Free tier: 1,000 calls/month.
Env: PDL_API_KEY
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

PDL_API_KEY = os.getenv("PDL_API_KEY", "")
PDL_BASE = "https://api.peopledatalabs.com/v5"


class PDLSource(BaseSource):
    name = "pdl"

    def is_configured(self) -> bool:
        return bool(PDL_API_KEY)

    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search PDL for people matching keyword + ICP titles."""
        if not self.is_configured():
            return []

        cache_key = f"pdl:search:{keyword}:{limit}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        try:
            # PDL uses Elasticsearch DSL
            es_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"job_company_industry": keyword}},
                        ],
                        "should": [
                            {"match": {"job_title": "CTO"}},
                            {"match": {"job_title": "VP Engineering"}},
                            {"match": {"job_title": "Founder"}},
                            {"match": {"job_title": "CEO"}},
                            {"match": {"job_title": "Head of Product"}},
                        ],
                        "minimum_should_match": 1,
                    }
                }
            }

            resp = requests.post(
                f"{PDL_BASE}/person/search",
                json={
                    "query": es_query,
                    "size": min(limit, 25),
                },
                headers={"x-api-key": PDL_API_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                ledger.log(f"PDL search HTTP {resp.status_code}")
                return []

            people = resp.json().get("data", []) or []
            leads = [self._person_to_lead(p) for p in people]
            set_source_cache(cache_key, self.name, leads)
            return leads

        except Exception as e:
            ledger.log(f"PDL discover error: {e}")
            return []

    def enrich_lead(self, lead: dict) -> dict:
        """Enrich a lead with PDL person data."""
        enriched = dict(lead)
        if not self.is_configured():
            return enriched

        email = lead.get("email", "")
        name = lead.get("name", "")
        company = lead.get("company", "")
        if not (email or (name and company)):
            return enriched

        cache_key = f"pdl:enrich:{email or name + '|' + company}"
        cached = get_source_cache(cache_key)
        if cached:
            enriched.update(cached)
            return enriched

        try:
            params = {"pretty": True}
            if email:
                params["email"] = email
            else:
                parts = name.split()
                params["first_name"] = parts[0] if parts else ""
                params["last_name"] = parts[-1] if len(parts) > 1 else ""
                params["company"] = company

            resp = requests.get(
                f"{PDL_BASE}/person/enrich",
                params=params,
                headers={"x-api-key": PDL_API_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                return enriched

            person = resp.json()
            updates = {}
            if person.get("work_email") and not enriched.get("email"):
                updates["email"] = person["work_email"]
            elif person.get("recommended_personal_email") and not enriched.get("email"):
                updates["email"] = person["recommended_personal_email"]
            if person.get("job_title") and not enriched.get("title"):
                updates["title"] = person["job_title"]
            if person.get("linkedin_url") and not enriched.get("linkedin_url"):
                updates["linkedin_url"] = person["linkedin_url"]
            if person.get("twitter_url") and not enriched.get("x_username"):
                url = person["twitter_url"]
                updates["x_username"] = url.rstrip("/").split("/")[-1]
            if person.get("github_url") and not enriched.get("github_url"):
                updates["github_url"] = person["github_url"]
            if person.get("job_company_size") and not enriched.get("company_size"):
                updates["company_size"] = self._parse_size(person["job_company_size"])

            set_source_cache(cache_key, self.name, updates)
            enriched.update(updates)
            return enriched

        except Exception as e:
            ledger.log(f"PDL enrich error: {e}")
            return enriched

    def _person_to_lead(self, person: dict) -> dict:
        name = person.get("full_name") or ""
        if not name:
            first = person.get("first_name") or ""
            last = person.get("last_name") or ""
            name = f"{first} {last}".strip()

        return self._make_lead(
            name=name,
            title=person.get("job_title", ""),
            company=person.get("job_company_name", ""),
            email=person.get("work_email") or person.get("recommended_personal_email") or "",
            linkedin_url=person.get("linkedin_url", ""),
            x_username=(person.get("twitter_url") or "").rstrip("/").split("/")[-1] if person.get("twitter_url") else "",
            source="pdl",
            source_url=person.get("linkedin_url", ""),
            source_confidence=0.7,
            raw_data=person,
            github_url=person.get("github_url") or "",
            company_size=self._parse_size(person.get("job_company_size")),
        )

    @staticmethod
    def _parse_size(size_str) -> int:
        """Convert PDL company size range like '51-200' to midpoint."""
        if not size_str:
            return 0
        s = str(size_str)
        if "-" in s:
            parts = s.split("-")
            try:
                return (int(parts[0]) + int(parts[1])) // 2
            except (ValueError, IndexError):
                return 0
        try:
            return int(s)
        except ValueError:
            return 0
