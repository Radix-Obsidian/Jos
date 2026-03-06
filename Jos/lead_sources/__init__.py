"""Lead-source registry, unified discovery, deduplication, and cascading enrichment."""
from __future__ import annotations

from lead_sources.base import BaseSource
from lead_sources.apollo_source import ApolloSource
from lead_sources.github_source import GitHubSource
from lead_sources.producthunt_source import ProductHuntSource
from lead_sources.crunchbase_source import CrunchbaseSource
from lead_sources.pdl_source import PDLSource

import ledger

ALL_SOURCES: list[BaseSource] = [
    ApolloSource(),
    GitHubSource(),
    ProductHuntSource(),
    CrunchbaseSource(),
    PDLSource(),
]


def get_configured_sources() -> list[BaseSource]:
    """Return only sources whose API keys are present."""
    return [s for s in ALL_SOURCES if s.is_configured()]


def discover_all(keyword: str, limit_per_source: int = 20) -> list[dict]:
    """Fan out discovery to every configured source, then deduplicate."""
    raw: list[dict] = []
    sources = get_configured_sources()
    if not sources:
        ledger.log("No lead sources configured — skipping discovery")
        return []

    for src in sources:
        try:
            leads = src.discover_leads(keyword, limit=limit_per_source)
            raw.extend(leads)
            ledger.log(f"{src.name}: discovered {len(leads)} leads for '{keyword}'")
        except Exception as e:
            ledger.log(f"{src.name} discover error: {e}")

    deduped = deduplicate_leads(raw)
    ledger.log(f"Discovery total: {len(raw)} raw → {len(deduped)} deduped")
    return deduped


def deduplicate_leads(leads: list[dict]) -> list[dict]:
    """Merge leads by email > x_username > name+company.

    When two leads match, the one with the higher source_confidence wins;
    the loser's source is appended to sources_json.
    """
    buckets: dict[str, dict] = {}

    for lead in leads:
        key = _dedup_key(lead)
        if not key:
            # No usable key — keep as-is
            buckets[id(lead)] = lead
            continue

        if key in buckets:
            existing = buckets[key]
            # Merge: higher confidence wins as primary
            if lead.get("source_confidence", 0) > existing.get("source_confidence", 0):
                _merge_into(target=lead, donor=existing)
                buckets[key] = lead
            else:
                _merge_into(target=existing, donor=lead)
        else:
            buckets[key] = lead

    return list(buckets.values())


def cascading_enrich(lead: dict) -> dict:
    """Try enrichment from each configured source until we have an email."""
    enriched = dict(lead)
    for src in get_configured_sources():
        try:
            enriched = src.enrich_lead(enriched)
        except Exception as e:
            ledger.log(f"{src.name} enrich error: {e}")
        # Stop once we have a verified email
        if enriched.get("email"):
            break
    return enriched


# ---------- internals ----------

def _dedup_key(lead: dict) -> str:
    """Generate a dedup key: email > x_username > name+company."""
    email = lead.get("email", "").strip().lower()
    if email:
        return f"email:{email}"
    x = lead.get("x_username", "").strip().lower()
    if x:
        return f"x:{x}"
    name = lead.get("name", "").strip().lower()
    company = lead.get("company", "").strip().lower()
    if name and company:
        return f"nc:{name}|{company}"
    return ""


def _merge_into(target: dict, donor: dict):
    """Copy non-empty fields from *donor* into *target*, track sources."""
    for field in ("email", "linkedin_url", "x_username", "title", "company"):
        if not target.get(field) and donor.get(field):
            target[field] = donor[field]

    # Build sources list
    existing_sources = set()
    if target.get("source"):
        existing_sources.add(target["source"])
    if donor.get("source"):
        existing_sources.add(donor["source"])
    target["sources_json"] = sorted(existing_sources)
