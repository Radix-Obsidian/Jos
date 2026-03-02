"""ProductHunt lead discovery — find makers of trending products.

Free developer token at api.producthunt.com.
Env: PRODUCTHUNT_TOKEN
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

PRODUCTHUNT_TOKEN = os.getenv("PRODUCTHUNT_TOKEN", "")
PH_GRAPHQL = "https://api.producthunt.com/v2/api/graphql"


class ProductHuntSource(BaseSource):
    name = "producthunt"

    def is_configured(self) -> bool:
        return bool(PRODUCTHUNT_TOKEN)

    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search ProductHunt for products, then extract makers."""
        if not self.is_configured():
            return []

        cache_key = f"ph:search:{keyword}:{limit}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        query = """
        query($query: String!, $first: Int!) {
            posts(order: RANKING, search: $query, first: $first) {
                edges {
                    node {
                        id
                        name
                        tagline
                        url
                        makers {
                            id
                            name
                            headline
                            twitterUsername
                            websiteUrl
                        }
                    }
                }
            }
        }
        """

        try:
            resp = requests.post(
                PH_GRAPHQL,
                json={"query": query, "variables": {"query": keyword, "first": min(limit, 20)}},
                headers={
                    "Authorization": f"Bearer {PRODUCTHUNT_TOKEN}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                ledger.log(f"ProductHunt HTTP {resp.status_code}")
                return []

            edges = (resp.json().get("data", {}).get("posts", {}).get("edges", []))
            leads: list[dict] = []
            seen_names: set[str] = set()

            for edge in edges:
                node = edge.get("node", {})
                product_url = node.get("url", "")
                for maker in node.get("makers", []):
                    name = maker.get("name", "")
                    if name in seen_names or not name:
                        continue
                    seen_names.add(name)

                    leads.append(self._make_lead(
                        name=name,
                        title=maker.get("headline", ""),
                        company=node.get("name", ""),
                        x_username=maker.get("twitterUsername") or "",
                        source="producthunt",
                        source_url=product_url,
                        source_confidence=0.6,
                        raw_data=maker,
                        producthunt_url=product_url,
                    ))
                    if len(leads) >= limit:
                        break
                if len(leads) >= limit:
                    break

            set_source_cache(cache_key, self.name, leads)
            return leads

        except Exception as e:
            ledger.log(f"ProductHunt discover error: {e}")
            return []

    def enrich_lead(self, lead: dict) -> dict:
        """ProductHunt doesn't offer a person-enrich API — passthrough."""
        return dict(lead)
