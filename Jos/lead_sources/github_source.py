"""GitHub lead discovery — search repos, then extract leads from stargazers/contributors.

Free tier: 5,000 requests/hour (authenticated).
Env: GITHUB_TOKEN
"""
from __future__ import annotations

import os
import re

import requests

import ledger
from db import get_source_cache, set_source_cache
from lead_sources.base import BaseSource

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_API = "https://api.github.com"


class GitHubSource(BaseSource):
    name = "github"

    def is_configured(self) -> bool:
        return bool(GITHUB_TOKEN)

    def discover_leads(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search GitHub repos by keyword, then pull stargazers/contributors."""
        if not self.is_configured():
            return []

        cache_key = f"github:search:{keyword}:{limit}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}

            # Step 1: find top repos matching keyword
            resp = requests.get(
                f"{GH_API}/search/repositories",
                params={"q": keyword, "sort": "stars", "per_page": 5},
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                ledger.log(f"GitHub repo search HTTP {resp.status_code}")
                return []

            repos = resp.json().get("items", [])[:5]

            # Step 2: for each repo, get stargazers (cheaper than contributors)
            leads: list[dict] = []
            seen_logins: set[str] = set()
            per_repo = max(limit // max(len(repos), 1), 5)

            for repo in repos:
                full_name = repo.get("full_name", "")
                sg_resp = requests.get(
                    f"{GH_API}/repos/{full_name}/stargazers",
                    params={"per_page": per_repo},
                    headers=headers,
                    timeout=15,
                )
                if sg_resp.status_code != 200:
                    continue

                for user in sg_resp.json():
                    login = user.get("login", "")
                    if login in seen_logins or not login:
                        continue
                    seen_logins.add(login)

                    # Step 3: get user profile for bio / company
                    profile = self._get_user_profile(login, headers)
                    if profile:
                        leads.append(profile)
                    if len(leads) >= limit:
                        break
                if len(leads) >= limit:
                    break

            set_source_cache(cache_key, self.name, leads)
            return leads

        except Exception as e:
            ledger.log(f"GitHub discover error: {e}")
            return []

    def enrich_lead(self, lead: dict) -> dict:
        """Enrich with GitHub profile data if x_username or name match."""
        enriched = dict(lead)
        if not self.is_configured():
            return enriched

        github_url = lead.get("github_url", "")
        if not github_url:
            return enriched

        login = github_url.rstrip("/").split("/")[-1]
        if not login:
            return enriched

        cache_key = f"github:enrich:{login}"
        cached = get_source_cache(cache_key)
        if cached:
            enriched.update(cached)
            return enriched

        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            resp = requests.get(
                f"{GH_API}/users/{login}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return enriched

            user = resp.json()
            updates = {}
            if user.get("email") and not enriched.get("email"):
                updates["email"] = user["email"]
            if user.get("company") and not enriched.get("company"):
                updates["company"] = user["company"].lstrip("@")
            if user.get("twitter_username") and not enriched.get("x_username"):
                updates["x_username"] = user["twitter_username"]
            if user.get("blog") and "linkedin.com" in (user.get("blog") or ""):
                updates["linkedin_url"] = user["blog"]

            set_source_cache(cache_key, self.name, updates)
            enriched.update(updates)
            return enriched

        except Exception as e:
            ledger.log(f"GitHub enrich error: {e}")
            return enriched

    def _get_user_profile(self, login: str, headers: dict) -> dict | None:
        """Fetch a GitHub user profile and convert to lead dict."""
        cache_key = f"github:user:{login}"
        cached = get_source_cache(cache_key)
        if cached:
            return cached

        try:
            resp = requests.get(
                f"{GH_API}/users/{login}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            user = resp.json()
            name = user.get("name") or login
            bio = user.get("bio") or ""
            company = (user.get("company") or "").lstrip("@")

            # Parse bio for title
            title = self._extract_title(bio)

            lead = self._make_lead(
                name=name,
                title=title,
                company=company,
                email=user.get("email") or "",
                x_username=user.get("twitter_username") or "",
                source="github",
                source_url=user.get("html_url", ""),
                source_confidence=0.5,
                raw_data=user,
                github_url=user.get("html_url", ""),
            )
            set_source_cache(cache_key, self.name, lead)
            return lead

        except Exception:
            return None

    @staticmethod
    def _extract_title(bio: str) -> str:
        """Pull a job title from a GitHub bio."""
        if not bio:
            return ""
        pattern = re.compile(
            r'\b(CEO|CTO|COO|CFO|VP|(?:Co-)?Founder|'
            r'Head of \w+|Director|Engineering Manager|'
            r'Staff Engineer|Principal Engineer|Tech Lead)\b',
            re.IGNORECASE,
        )
        m = pattern.search(bio)
        return m.group(0) if m else ""
