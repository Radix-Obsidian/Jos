---
name: x-posting
description: Post tweets, read mentions, reply, like, retweet, and search on X/Twitter using the official v2 API via the xpost CLI.
---

# X/Twitter — xpost CLI

All X/Twitter interactions go through the `xpost` CLI.

## Setup

1. Install: `npm install -g xpost-cli`
2. Store your X API keys at `~/.config/x-api/keys.env`:

```
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...
X_USER_ID=...
```

Get these from https://developer.x.com/en/portal/dashboard (Basic tier: $200/mo).

## Commands

```bash
# Post a tweet
xpost post "Your tweet text here"

# Reply to a tweet
xpost reply <tweet_id> "Your reply text"

# Quote tweet
xpost quote <tweet_id> "Your quote text"

# Get mentions
xpost mentions [--count 20]

# Search recent tweets
xpost search "query string" [--count 10]

# Like a tweet
xpost like <tweet_id>

# Retweet
xpost retweet <tweet_id>

# Delete a tweet
xpost delete <tweet_id>

# Get a single tweet
xpost get <tweet_id>

# Home timeline
xpost home [--count 20]
```

## Rate Limits (Basic Tier)
- POST tweets: 100/15min, 10,000/24hrs
- GET mentions: 300/15min
- GET timeline: 900/15min
- Search recent: 300/15min
- Likes: 50/15min, 1,000/24hrs

## Scheduling Tweets via OpenClaw Cron

Spread tweets throughout the day using one-shot cron jobs:

```json
{
  "name": "scheduled-tweet-1",
  "schedule": {"kind": "at", "at": "2026-03-09T14:00:00Z"},
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "Post this tweet via xpost post \"Your tweet text here\"",
    "timeoutSeconds": 30
  },
  "delivery": {"mode": "none"},
  "enabled": true
}
```

## Tips
- Always use `xpost` — never use browser automation for X
- Output is JSON by default; use `--pretty` for formatted or `--text` for plain
- For engagement: reply to mentions promptly, quote-tweet interesting content with your take
