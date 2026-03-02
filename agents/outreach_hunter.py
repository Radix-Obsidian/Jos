"""Outreach Hunter - scan leads, qualify, and generate personalized DMs.

Combines: lead scanning + qualification + personalized outreach.
Supports two lead sources: web scraping and X/Twitter.
"""
from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

import ledger
from config import (
    PRODUCT, ICP, EMAIL_TEMPLATE, LINKEDIN_TEMPLATE,
    SCORE_ENTERPRISE, SCORE_SELF_SERVE, SCORE_NURTURE, COMPETITORS,
)
from x_scraper import search_x_leads
from lead_enricher import enrich_lead, enrich_lead_with_domain, is_email_verified


# ---------- Lead Scanning ----------

def scan_leads(keyword: str, url: str = None, source: str = "web") -> list[dict]:
    """Scrape leads matching keyword from web directories or X/Twitter.

    Args:
        keyword: Search term (industry, role, etc.)
        url: Optional specific URL to scrape (web source only)
        source: "web" for Google scraping, "x" for X/Twitter

    Returns:
        List of validated lead dicts
    """
    if source == "x":
        x_leads = search_x_leads(keyword)
        valid = [l for l in x_leads if validate_lead(l)]
        ledger.log(f"X scan: {len(valid)} valid leads for '{keyword}'")
        return valid

    if url is None:
        url = f"https://www.google.com/search?q={keyword}+startup+founders"

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })

        if resp.status_code != 200:
            ledger.log(f"Scan failed: HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        people = soup.find_all("div", class_="person")

        leads = []
        for person in people:
            lead = parse_lead(person)
            if validate_lead(lead):
                leads.append(lead)

        ledger.log(f"Scanned {len(leads)} valid leads for '{keyword}'")
        return leads

    except Exception as e:
        ledger.log(f"Scan error: {e}")
        return []


def parse_lead(element) -> dict:
    """Extract lead fields from a BeautifulSoup element."""
    name = ""
    title = ""
    company = ""
    email = ""
    linkedin_url = ""

    h3 = element.find("h3")
    if h3:
        name = h3.get_text(strip=True)

    title_el = element.find("span", class_="title")
    if title_el:
        title = title_el.get_text(strip=True)

    company_el = element.find("span", class_="company")
    if company_el:
        company = company_el.get_text(strip=True)

    for a in element.find_all("a"):
        href = a.get("href", "")
        if "mailto:" in href:
            email = href.replace("mailto:", "")
        elif "linkedin.com" in href:
            linkedin_url = href

    return {
        "name": name,
        "title": title,
        "company": company,
        "email": email,
        "linkedin_url": linkedin_url,
    }


def validate_lead(lead: dict) -> bool:
    """Check lead has minimum required fields (name + email or x_username)."""
    if not lead.get("name"):
        return False
    return bool(lead.get("email")) or bool(lead.get("x_username"))


# ---------- Lead Qualification ----------

def qualify_lead(lead: dict) -> dict:
    """Score a lead and assign a tier.

    Returns:
        Dict with score, tier, status, and original lead data
    """
    score = score_lead(lead)
    tier = assign_tier(score)
    status = determine_status(score, tier)
    ledger.log(f"Qualified {lead['name']} -> {tier} ({score:.2f}) status={status}")

    return {
        "lead": lead,
        "score": score,
        "tier": tier,
        "status": status,
    }


SOURCE_BONUSES = {
    "apollo": 0.05,
    "crunchbase": 0.05,
    "producthunt": 0.03,
    "github": 0.02,
    "x": 0.02,
    "pdl": 0.03,
}

FUNDING_BOOST_STAGES = {"seed", "series_a", "series_b"}


def score_lead(lead: dict) -> float:
    """Score a lead 0-1 based on ICP match.

    Scoring factors:
    - Competitor check → near-zero immediately
    - Title match (0-0.4), COO/CMO/CFO/CSO capped at 0.15
    - Industry/company signal (0-0.3)
    - Company size penalty: >500 → -0.6; <15 → -0.2
    - Has LinkedIn (0-0.05)
    - Has email (0-0.25)
    - Source quality bonus (0-0.05)
    - Funding signal (+0.1 for seed/A/B)
    - Multi-source bonus (+0.05 per extra source, cap +0.15)
    """
    score = 0.0
    title = lead.get("title", "").lower()
    company = lead.get("company", "").lower()

    # Competitor check — disqualify immediately
    if any(comp in company for comp in COMPETITORS):
        return 0.05

    # Title match (biggest signal)
    # Non-buyer ops/marketing roles capped at 0.15
    NON_BUYER_ROLES = ["coo", "cmo", "cfo", "cso"]
    if any(role in title for role in NON_BUYER_ROLES):
        score += 0.15
    else:
        for icp_title in ICP["titles"]:
            if icp_title.lower() in title:
                score += 0.4
                break
        else:
            if any(kw in title for kw in ["manager", "director", "lead", "head"]):
                score += 0.25
            elif any(kw in title for kw in ["engineer", "developer"]):
                score += 0.15

    # Industry/company signal — real field takes priority over name guessing
    industry = lead.get("industry", "").lower()
    if industry:
        for icp_industry in ICP["industries"]:
            if icp_industry.lower() in industry:
                score += 0.3
                break
        else:
            if any(kw in industry for kw in ["voice", "speech", "audio", "ai", "saas", "cloud", "developer"]):
                score += 0.2
    else:
        # Fallback: regex word-boundary keyword check on company name
        for icp_industry in ICP["industries"]:
            if icp_industry.lower() in company:
                score += 0.3
                break
        else:
            if any(re.search(r'\b' + kw + r'\b', company) for kw in ["ai", "tech", "software", "saas", "cloud", "data", "voice", "speech", "audio"]):
                score += 0.2

    # Company size penalty
    size = lead.get("company_size", 0)
    if size > 500:
        score -= 0.6   # way outside ICP max → pushed to disqualified range
    elif 0 < size < 15:
        score -= 0.2   # tiny company, softer penalty

    # Contact quality (rebalanced: email more important, LinkedIn less decisive)
    if lead.get("linkedin_url"):
        score += 0.05
    if lead.get("email"):
        score += 0.25

    # Source quality bonus
    source = lead.get("source", "")
    score += SOURCE_BONUSES.get(source, 0)

    # Funding signal
    funding = lead.get("funding_stage", "").lower().replace(" ", "_")
    if funding in FUNDING_BOOST_STAGES:
        score += 0.1

    # Multi-source bonus (found on 2+ platforms = higher confidence)
    sources_list = lead.get("sources_json", [])
    if isinstance(sources_list, list) and len(sources_list) > 1:
        score += 0.05 * min(len(sources_list) - 1, 3)  # cap +0.15

    return max(0.0, min(score, 1.0))


def assign_tier(score: float) -> str:
    """Assign lead tier based on score."""
    if score >= SCORE_ENTERPRISE:
        return "enterprise"
    elif score >= SCORE_SELF_SERVE:
        return "self_serve"
    elif score >= SCORE_NURTURE:
        return "nurture"
    else:
        return "disqualified"


def determine_status(score: float, tier: str) -> str:
    """Determine initial lead status (hot/cold).

    - enterprise with score >= 0.8 -> hot
    - qualified (enterprise/self_serve) -> cold (needs outreach first)
    - nurture/disqualified -> cold
    """
    if tier == "enterprise" and score >= 0.8:
        return "hot"
    return "cold"


# ---------- Personalized DM Generation ----------

def generate_outreach(lead: dict, tier: str, channel: str = "email") -> dict:
    """Generate personalized outreach for a lead.

    Returns:
        Dict with channel, message, lead, and tier
    """
    if channel == "linkedin":
        message = write_linkedin(lead, tier)
    else:
        message = write_email(lead, tier)

    personalized_dm = message.get("body", "")
    ledger.log(f"Wrote {channel} outreach for {lead['name']} ({tier})")

    return {
        "channel": channel,
        "message": message,
        "personalized_dm": personalized_dm,
        "lead": lead,
        "tier": tier,
    }


def write_email(lead: dict, tier: str) -> dict:
    """Write personalized email for a lead."""
    first_name = lead["name"].split()[0]
    company = lead.get("company", "your company")

    x_post = lead.get("x_post_text", "")

    if tier == "enterprise":
        subject = f"{first_name}, scaling voice AI at {company}?"
        if x_post:
            opening = f"Saw your post about voice coding — totally agree. {company} is clearly pushing boundaries."
        else:
            opening = f"I noticed {company} is doing impressive work in the AI space."
        value_prop = (
            f"Teams like yours are using {PRODUCT['name']} to ship voice features "
            f"in days instead of months. I'd love to show you how it could accelerate "
            f"what {company} is building."
        )
        cta = "Would you be open to a quick 15-min demo this week?"
    else:
        subject = f"Voice AI for {company} - quick question"
        if x_post:
            opening = f"Hi {first_name}, saw your post about voice coding and thought this might be relevant."
        else:
            opening = f"Hi {first_name}, saw your profile and thought this might be relevant."
        value_prop = (
            f"{PRODUCT['name']} gives engineering teams a complete voice platform "
            f"starting at {PRODUCT['price_self_serve']}. No infrastructure to manage."
        )
        cta = f"You can try it here: {PRODUCT['url']} - happy to answer any questions."

    body = EMAIL_TEMPLATE.format(
        subject=subject,
        first_name=first_name,
        opening_line=opening,
        value_prop=value_prop,
        cta=cta,
    )

    return {"subject": subject, "body": body}


def write_linkedin(lead: dict, tier: str) -> dict:
    """Write personalized LinkedIn DM for a lead."""
    first_name = lead["name"].split()[0]
    company = lead.get("company", "your team")
    x_post = lead.get("x_post_text", "")

    if tier == "enterprise":
        if x_post:
            opening = f"Hi {first_name}, saw your post about voice coding — really resonated."
        else:
            opening = f"Hi {first_name}, really impressed with what {company} is building."
        value_prop = f"{PRODUCT['name']} helps teams like yours ship voice features fast."
        cta = "Open to a quick chat about how it could help?"
    else:
        if x_post:
            opening = f"Hey {first_name}! Saw your thoughts on voice coding — thought you'd find this useful."
        else:
            opening = f"Hey {first_name}! Quick note about something you might find useful."
        value_prop = f"{PRODUCT['name']} - voice platform for dev teams, {PRODUCT['price_self_serve']}."
        cta = f"Check it out: {PRODUCT['url']}"

    body = LINKEDIN_TEMPLATE.format(
        first_name=first_name,
        opening_line=opening,
        value_prop=value_prop,
        cta=cta,
    )

    return {"body": body}


# ---------- Full Hunt Pipeline ----------

def hunt(lead: dict) -> dict:
    """Full outreach hunter pipeline: qualify + enrich + generate DM.

    Args:
        lead: Raw lead dict (from web or X/Twitter source)

    Returns:
        Dict with qualification + enrichment + outreach results
    """
    # Enrich with Hunter.io if X-sourced (has x_username but no email)
    if lead.get("x_username") and not lead.get("email"):
        lead = enrich_lead(lead)
        if lead.get("email"):
            ledger.log(f"Enriched {lead['name']}: found email (confidence={lead.get('email_confidence', 0)})")

    # Domain enrichment: get real industry + company_size if not already set
    if not lead.get("industry") or not lead.get("company_size"):
        lead = enrich_lead_with_domain(lead)

    qual = qualify_lead(lead)
    tier = qual["tier"]
    status = qual["status"]
    score = qual["score"]

    # Boost score if email is verified
    if lead.get("email_confidence", 0) >= 80:
        score = min(score + 0.1, 1.0)
        tier = assign_tier(score)
        status = determine_status(score, tier)

    if tier == "disqualified":
        return {
            "lead": lead,
            "score": score,
            "tier": tier,
            "status": status,
            "outreach": None,
            "personalized_dm": "",
        }

    # Pick channel: use email if verified, else linkedin
    if lead.get("email") and is_email_verified(lead.get("email_confidence", 0)):
        channel = "email"
    elif tier == "enterprise" and lead.get("email"):
        channel = "email"
    else:
        channel = "linkedin"

    outreach = generate_outreach(lead, tier, channel)

    return {
        "lead": lead,
        "score": score,
        "tier": tier,
        "status": status,
        "outreach": outreach,
        "personalized_dm": outreach["personalized_dm"],
        "channel": channel,
    }
