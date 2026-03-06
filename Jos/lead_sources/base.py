"""Abstract base class for all lead discovery sources."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSource(ABC):
    """Every lead source implements this interface.

    Subclasses provide:
      - name: human-readable source identifier
      - discover_leads(): search for ICP-matching leads
      - enrich_lead(): add source-specific data to a lead dict
      - is_configured(): True when required API keys are present
    """

    name: str = "base"

    @abstractmethod
    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search this source for leads matching *keyword*.

        Returns list of standardised lead dicts::

            {"name", "title", "company", "email", "linkedin_url",
             "x_username", "source", "source_url", "source_confidence",
             "raw_data"}
        """

    @abstractmethod
    def enrich_lead(self, lead: dict) -> dict:
        """Add source-specific enrichment fields to an existing lead dict."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the required API key / token is present."""

    # ---------- helpers ----------

    @staticmethod
    def _make_lead(
        name: str = "",
        title: str = "",
        company: str = "",
        email: str = "",
        linkedin_url: str = "",
        x_username: str = "",
        source: str = "",
        source_url: str = "",
        source_confidence: float = 0.0,
        raw_data: dict | None = None,
        **extra,
    ) -> dict:
        """Build a standardised lead dict with sane defaults."""
        lead = {
            "name": name,
            "title": title,
            "company": company,
            "email": email,
            "linkedin_url": linkedin_url,
            "x_username": x_username,
            "source": source,
            "source_url": source_url,
            "source_confidence": source_confidence,
            "raw_data": raw_data or {},
        }
        lead.update(extra)
        return lead
