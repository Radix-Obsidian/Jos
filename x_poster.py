"""X/Twitter engagement — post, reply, like, quote as the authenticated user.

All engagement drafts flow through the approval queue before execution.
Uses tweepy v4.x with OAuth 1.0a User Context for posting.
"""
from __future__ import annotations

import os

import ledger

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import tweepy
    HAS_TWEEPY = True
except ImportError:
    HAS_TWEEPY = False

X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")


def get_client() -> object | None:
    """Build authenticated tweepy Client. Returns None if keys missing."""
    if not HAS_TWEEPY:
        ledger.log("tweepy not installed — X posting disabled")
        return None
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        return None
    return tweepy.Client(
        bearer_token=X_BEARER_TOKEN or None,
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )


def post_tweet(text: str) -> dict:
    """Post a new tweet. Returns {status, tweet_id, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "tweet_id": "", "error": "X client not configured"}
    try:
        resp = client.create_tweet(text=text)
        tweet_id = str(resp.data["id"])
        ledger.log(f"Posted tweet {tweet_id}")
        return {"status": "sent", "tweet_id": tweet_id, "error": ""}
    except Exception as e:
        ledger.log(f"X post_tweet failed: {e}")
        return {"status": "failed", "tweet_id": "", "error": str(e)}


def reply_to_tweet(tweet_id: str, text: str) -> dict:
    """Reply to a specific tweet. Returns {status, reply_id, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "reply_id": "", "error": "X client not configured"}
    try:
        resp = client.create_tweet(text=text, in_reply_to_tweet_id=tweet_id)
        reply_id = str(resp.data["id"])
        ledger.log(f"Replied to {tweet_id} with {reply_id}")
        return {"status": "sent", "reply_id": reply_id, "error": ""}
    except Exception as e:
        ledger.log(f"X reply failed: {e}")
        return {"status": "failed", "reply_id": "", "error": str(e)}


def like_tweet(tweet_id: str) -> dict:
    """Like a tweet. Returns {status, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "error": "X client not configured"}
    try:
        client.like(tweet_id)
        ledger.log(f"Liked tweet {tweet_id}")
        return {"status": "sent", "error": ""}
    except Exception as e:
        ledger.log(f"X like failed: {e}")
        return {"status": "failed", "error": str(e)}


def quote_tweet(tweet_id: str, text: str) -> dict:
    """Quote tweet with comment. Returns {status, tweet_id, error}."""
    client = get_client()
    if not client:
        return {"status": "error", "tweet_id": "", "error": "X client not configured"}
    try:
        resp = client.create_tweet(text=text, quote_tweet_id=tweet_id)
        new_id = str(resp.data["id"])
        ledger.log(f"Quote-tweeted {tweet_id} as {new_id}")
        return {"status": "sent", "tweet_id": new_id, "error": ""}
    except Exception as e:
        ledger.log(f"X quote failed: {e}")
        return {"status": "failed", "tweet_id": "", "error": str(e)}


def search_icp_posts(keywords: list[str], max_results: int = 20) -> list[dict]:
    """Search X for ICP-relevant posts to engage with.

    Returns simplified tweet dicts with id, text, author, url.
    Uses bearer token for search (read-only endpoint).
    """
    client = get_client()
    if not client:
        return []
    try:
        query = " OR ".join(keywords) + " -is:retweet"
        resp = client.search_recent_tweets(
            query=query,
            max_results=min(max_results, 100),
            tweet_fields=["author_id", "created_at", "public_metrics"],
            user_fields=["name", "username", "description"],
            expansions=["author_id"],
        )
        if not resp.data:
            return []

        users = {u.id: u for u in (resp.includes.get("users", []) or [])}
        posts = []
        for tweet in resp.data:
            author = users.get(tweet.author_id)
            posts.append({
                "id": str(tweet.id),
                "text": tweet.text,
                "author_name": author.name if author else "",
                "author_username": author.username if author else "",
                "author_bio": author.description if author else "",
                "url": f"https://x.com/{author.username}/status/{tweet.id}" if author else "",
                "likes": tweet.public_metrics.get("like_count", 0) if tweet.public_metrics else 0,
                "replies": tweet.public_metrics.get("reply_count", 0) if tweet.public_metrics else 0,
            })
        ledger.log(f"X ICP search: found {len(posts)} posts")
        return posts
    except Exception as e:
        ledger.log(f"X ICP search failed: {e}")
        return []
