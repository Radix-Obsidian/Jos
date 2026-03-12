"""X/Twitter lead scraping via snscrape.

Searches X for keywords (e.g. 'voice coding', 'Cursor AI') and extracts
potential leads from tweet authors' bios and engagement signals.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import os

import ledger

# Tweepy v2 (primary — uses X API v2 Bearer token, works reliably)
try:
    import tweepy
    HAS_TWEEPY = True
except ImportError:
    HAS_TWEEPY = False

# snscrape (legacy fallback — may break with X API changes)
try:
    import snscrape.modules.twitter as sntwitter
    HAS_SNSCRAPE = True
except (ImportError, AttributeError):
    HAS_SNSCRAPE = False


# ---------- Bio Parsing ----------

def parse_bio(bio: str) -> dict:
    """Extract title and company from an X/Twitter bio.

    Handles patterns like:
      - "CEO at TechStartup"
      - "CTO @CloudSaaS"
      - "Founder of AITools"
      - "Co-Founder & CEO, DataCo"

    Returns:
        {"title": str, "company": str}
    """
    if not bio:
        return {"title": "", "company": ""}

    title = ""
    company = ""

    # Match title patterns: "CEO at Company", "CTO @Company", "Founder of Company"
    title_pattern = re.compile(
        r'\b(CEO|CTO|COO|CFO|CMO|VP|SVP|EVP|'
        r'(?:Co-)?Founder|'
        r'Head of \w+|Director|President|Partner|'
        r'Managing Director|General Manager)\b',
        re.IGNORECASE,
    )

    title_match = title_pattern.search(bio)
    if title_match:
        title = title_match.group(0)

    # Try to extract company after title
    # Pattern: "Title at Company", "Title @Company", "Title of Company", "Title, Company"
    company_pattern = re.compile(
        r'(?:CEO|CTO|COO|CFO|CMO|VP|SVP|EVP|'
        r'(?:Co-)?Founder|Head of \w+|Director|President|Partner|'
        r'Managing Director|General Manager)'
        r'\s*(?:at|@|of|,|&\s*\w+\s*(?:at|@|of|,))\s*'
        r'([A-Z][\w.]+(?:\s+[\w.]+){0,3})',
        re.IGNORECASE,
    )

    company_match = company_pattern.search(bio)
    if company_match:
        company = company_match.group(1).strip().rstrip(".|,|;|:")
    else:
        # Fallback: try "at Company" or "@Company" anywhere
        fallback = re.search(r'(?:at|@)\s+([A-Z][\w.]+(?:\s+[\w.]+){0,2})', bio)
        if fallback:
            company = fallback.group(1).strip().rstrip(".|,|;|:")

    return {"title": title, "company": company}


# ---------- Tweet Filtering ----------

def filter_tweet(tweet, min_followers: int = 50, min_faves: int = 5,
                 max_age_days: int = 7) -> bool:
    """Check if a tweet meets lead quality thresholds.

    Args:
        tweet: snscrape Tweet object (or mock)
        min_followers: Minimum follower count
        min_faves: Minimum like count on the tweet
        max_age_days: Maximum age of tweet in days

    Returns:
        True if tweet passes all filters
    """
    if tweet.user.followersCount < min_followers:
        return False

    if tweet.likeCount < min_faves:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    if tweet.date < cutoff:
        return False

    return True


# ---------- Lead Extraction ----------

def extract_lead_from_tweet(tweet) -> dict:
    """Extract a lead dict from a tweet object.

    Returns:
        Lead dict with name, title, company, email, linkedin_url,
        x_username, and x_post_text fields.
    """
    bio_info = parse_bio(tweet.user.rawDescription or "")

    return {
        "name": tweet.user.displayname,
        "title": bio_info["title"],
        "company": bio_info["company"],
        "email": "",
        "linkedin_url": "",
        "x_username": tweet.user.username,
        "x_post_text": tweet.rawContent,
    }


# ---------- Scraping ----------

class _TweepyTweet:
    """Adapter so Tweepy tweet+user looks like a snscrape tweet object."""
    def __init__(self, tweet, user):
        self.rawContent = tweet.text
        self.likeCount = tweet.public_metrics.get("like_count", 0) if tweet.public_metrics else 0
        self.date = tweet.created_at
        self.user = type("User", (), {
            "displayname": user.name,
            "username": user.username,
            "rawDescription": user.description or "",
            "followersCount": user.public_metrics.get("followers_count", 0) if user.public_metrics else 0,
        })()


def _scrape_tweets_tweepy(keyword: str, limit: int = 50) -> list:
    """Scrape tweets via X API v2 Bearer token (Tweepy)."""
    if not HAS_TWEEPY:
        return []
    bearer = os.getenv("X_BEARER_TOKEN")
    if not bearer:
        ledger.log("X_BEARER_TOKEN not set — skipping Tweepy scrape")
        return []
    try:
        client = tweepy.Client(bearer_token=bearer, wait_on_rate_limit=True)
        response = client.search_recent_tweets(
            query=f"{keyword} -is:retweet lang:en",
            max_results=min(limit, 100),
            tweet_fields=["author_id", "created_at", "text", "public_metrics"],
            expansions=["author_id"],
            user_fields=["name", "username", "description", "public_metrics"],
        )
        if not response.data:
            return []
        users_by_id = {u.id: u for u in (response.includes.get("users") or [])}
        tweets = []
        for tweet in response.data:
            user = users_by_id.get(tweet.author_id)
            if user:
                tweets.append(_TweepyTweet(tweet, user))
        return tweets
    except Exception as exc:
        ledger.log(f"Tweepy scrape error for '{keyword}': {exc}")
        return []


def _scrape_tweets(keyword: str, limit: int = 50) -> list:
    """Scrape tweets matching keyword. Uses Tweepy (primary) then snscrape (fallback).

    This is the function that tests mock to avoid real API calls.
    """
    # Primary: Tweepy + X API v2
    if HAS_TWEEPY:
        results = _scrape_tweets_tweepy(keyword, limit)
        if results:
            return results

    # Legacy fallback: snscrape
    if not HAS_SNSCRAPE:
        ledger.log("Neither Tweepy nor snscrape available — cannot scrape X")
        return []

    scraper = sntwitter.TwitterSearchScraper(keyword)
    tweets = []
    for i, tweet in enumerate(scraper.get_items()):
        if i >= limit:
            break
        tweets.append(tweet)
    return tweets


def search_x_leads(keyword: str, min_followers: int = 50,
                   min_faves: int = 5, max_age_days: int = 7,
                   limit: int = 50) -> list[dict]:
    """Search X for leads matching a keyword.

    Args:
        keyword: Search term (e.g. "voice coding", "Cursor AI")
        min_followers: Minimum follower count filter
        min_faves: Minimum likes filter
        max_age_days: Maximum tweet age filter
        limit: Max tweets to scrape

    Returns:
        List of lead dicts that pass quality filters
    """
    try:
        tweets = _scrape_tweets(keyword, limit=limit)
    except Exception as e:
        ledger.log(f"X scrape error: {e}")
        return []

    leads = []
    seen_usernames = set()

    for tweet in tweets:
        if not filter_tweet(tweet, min_followers, min_faves, max_age_days):
            continue

        username = tweet.user.username
        if username in seen_usernames:
            continue
        seen_usernames.add(username)

        lead = extract_lead_from_tweet(tweet)
        leads.append(lead)

    ledger.log(f"X search '{keyword}': found {len(leads)} leads from {len(tweets)} tweets")
    return leads
