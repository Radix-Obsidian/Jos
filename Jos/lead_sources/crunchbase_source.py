"""Crunchbase lead discovery — find founders of recently funded companies.

Free tier: 250 calls/month.
Env: CRUNCHBASE_API_KEY
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

CRUNCHBASE_API_KEY = os.getenv("CRUNCHBASE_API_KEY", "")
CB_BASE = "https://api.crunchbase.com/api/v4"


class CrunchbaseSource(BaseSource):
    name = "crunchbase"

    def is_configured(self) -> bool:
        return bool(CRUNCHBASE_API_KEY)

    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search Crunchbase for companies, then extract founders."""
        if not self.is_configured():
            return []

        cache_key = f"cb:search:{keyword}:{limit}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        try:
            resp = requests.get(
                f"{CB_BASE}/searches/organizations",
                params={
                    "user_key": CRUNCHBASE_API_KEY,
                    "query": keyword,
                    "limit": min(limit, 25),
                },
                timeout=15,
            )
            if resp.status_code != 200:
                ledger.log(f"Crunchbase search HTTP {resp.status_code}")
                return []

            entities = resp.json().get("entities", [])
            leads: list[dict] = []

            for ent in entities:
                props = ent.get("properties", {})
                company_name = props.get("name", "")
                funding_stage = props.get("funding_stage", "")
                funding_total = props.get("funding_total", {})
                funding_amount = str(funding_total.get("value_usd", "")) if funding_total else ""
                cb_url = props.get("web_path", "")
                num_employees = props.get("num_employees_enum", "")

                # Extract founder from the entity's founder_identifiers
                founders = props.get("founder_identifiers", []) or []
                for founder in founders:
                    name = founder.get("value", "")
                    if not name:
                        continue
                    leads.append(self._make_lead(
                        name=name,
                        title="Founder",
                        company=company_name,
                        source="crunchbase",
                        source_url=f"https://www.crunchbase.com/{cb_url}" if cb_url else "",
                        source_confidence=0.8,
                        raw_data=props,
                        funding_stage=funding_stage,
                        funding_amount=funding_amount,
                        company_size=self._parse_employees(num_employees),
                    ))
                    if len(leads) >= limit:
                        break
                if len(leads) >= limit:
                    break

            set_source_cache(cache_key, self.name, leads)
            return leads

        except Exception as e:
            ledger.log(f"Crunchbase discover error: {e}")
            return []

    def enrich_lead(self, lead: dict) -> dict:
        """Enrich with Crunchbase org data if company is known."""
        enriched = dict(lead)
        if not self.is_configured():
            return enriched

        company = lead.get("company", "")
        if not company:
            return enriched

        cache_key = f"cb:enrich:{company.lower()}"
        cached = get_source_cache(cache_key)
        if cached:
            enriched.update(cached)
            return enriched

        try:
            permalink = company.lower().replace(" ", "-")
            resp = requests.get(
                f"{CB_BASE}/entities/organizations/{permalink}",
                params={"user_key": CRUNCHBASE_API_KEY},
                timeout=15,
            )
            if resp.status_code != 200:
                return enriched

            props = resp.json().get("properties", {})
            updates = {}
            funding_stage = props.get("funding_stage", "")
            if funding_stage and not enriched.get("funding_stage"):
                updates["funding_stage"] = funding_stage
            funding_total = props.get("funding_total", {})
            if funding_total and not enriched.get("funding_amount"):
                updates["funding_amount"] = str(funding_total.get("value_usd", ""))
            num_emp = props.get("num_employees_enum", "")
            if num_emp and not enriched.get("company_size"):
                updates["company_size"] = self._parse_employees(num_emp)

            set_source_cache(cache_key, self.name, updates)
            enriched.update(updates)
            return enriched

        except Exception as e:
            ledger.log(f"Crunchbase enrich error: {e}")
            return enriched

    @staticmethod
    def _parse_employees(enum_str: str) -> int:
        """Convert Crunchbase num_employees_enum like 'c_0051_0100' to midpoint int."""
        if not enum_str:
            return 0
        # Format: c_XXXX_YYYY
        parts = enum_str.replace("c_", "").split("_")
        try:
            low = int(parts[0])
            high = int(parts[1]) if len(parts) > 1 else low
            return (low + high) // 2
        except (ValueError, IndexError):
            return 0
