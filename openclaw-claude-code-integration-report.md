# OpenClaw x Claude Code Subscription Integration Report

**Author:** AJ, Founder — Voco, Proof Inc (Viper, Comply, Antidote)
**Date:** March 5, 2026
**Assisted by:** Claude Code (Opus 4.6)

---

## Executive Summary

Successfully reconfigured OpenClaw (v2026.3.2) to authenticate using a $100/month Claude Code subscription instead of requiring a separate Anthropic API key. This eliminates the need for pay-per-token API billing and lets OpenClaw — a self-hosted autonomous agent gateway — ride on an existing flat-rate subscription. The result: a fully operational AI agent ("Berma") running Claude Sonnet 4.5 with extended thinking, connected to Discord, Telegram, and iMessage, all powered by a subscription you're already paying for.

---

## The Problem

OpenClaw's default onboarding wizard stores credentials in `openclaw.json` under `auth.profiles` using a field called `apiKey`. As of v2026.3.2, this field is **not recognized by the config schema**. The wizard creates a broken config on first run.

Beyond that, OpenClaw expects a standalone Anthropic API key (`sk-ant-api03-...`) — a pay-per-token credential from console.anthropic.com. If you're already paying $100/month for a Claude Code subscription (which includes inference via OAuth tokens), there's no obvious way to use it. The onboarding doesn't offer this path.

**Symptoms encountered:**
- `Invalid config: Unrecognized key "apiKey"` on every gateway start
- `HTTP 401 authentication_error: Invalid bearer token` when sending messages
- `HTTP 404 not_found_error: model: claude-3-5-sonnet-20241022` — deprecated model ID
- Health status showing offline after every gateway restart
- Gateway token lost on every browser refresh

---

## The Root Cause (What We Discovered)

OpenClaw has a **two-layer credential system** that is not documented in any obvious place:

| Layer | File | Purpose |
|-------|------|---------|
| Config | `~/.openclaw/openclaw.json` | Declares provider name + auth mode only (no secrets) |
| Credentials | `~/.openclaw/agents/main/agent/auth-profiles.json` | Stores actual tokens, keys, OAuth credentials |

The wizard was writing the API key into the wrong layer (config JSON), which the schema validator rejects. Meanwhile, `auth-profiles.json` held a placeholder token that was never valid.

**The key insight:** Claude Code stores live OAuth credentials at `~/.claude/.credentials.json` with:
- An access token (`sk-ant-oat01-...`) — short-lived, used for API calls
- A refresh token (`sk-ant-ort01-...`) — long-lived, used to mint new access tokens
- An expiry timestamp
- Scope: `user:inference` — meaning it's authorized for model inference

OpenClaw's source code already has an `oauth` credential type in `auth-profiles.json` that accepts `access`, `refresh`, and `expires` fields — and it has built-in token refresh logic. It just doesn't expose this as a setup option.

---

## The Fix (Step by Step)

### 1. Credential Sync — Claude Code to OpenClaw

Read the live OAuth credentials from Claude Code:

```
~/.claude/.credentials.json
```

Write them into OpenClaw's credential store as an OAuth profile:

```json
// ~/.openclaw/agents/main/agent/auth-profiles.json
{
  "version": 1,
  "profiles": {
    "anthropic:default": {
      "type": "oauth",
      "provider": "anthropic",
      "access": "<access_token_from_claude_code>",
      "refresh": "<refresh_token_from_claude_code>",
      "expires": <expiry_timestamp>
    }
  }
}
```

### 2. Config Fix — Set Auth Mode to OAuth

```json
// ~/.openclaw/openclaw.json (auth section)
"auth": {
  "profiles": {
    "anthropic:default": {
      "provider": "anthropic",
      "mode": "oauth"
    }
  }
}
```

### 3. Model Update — Use Current Model IDs

The default model `claude-3-5-sonnet-20241022` is deprecated. OpenClaw uses simplified IDs:

```json
"agents": {
  "defaults": {
    "model": {
      "primary": "claude-sonnet-4-5"
    },
    "models": {
      "claude-sonnet-4-5": {
        "params": {
          "thinking": "low"
        }
      }
    }
  }
}
```

Valid model aliases in OpenClaw v2026.3.2:
- `claude-sonnet-4-5` / `claude-sonnet-4-6`
- `claude-opus-4-5` / `claude-opus-4-6`
- Short forms: `sonnet-4.5`, `opus-4.6`, etc.

### 4. Auto-Fix Script — Never Do This Manually Again

Created `~/.openclaw/auto-fix.ps1` that:
1. Reads fresh OAuth tokens from `~/.claude/.credentials.json`
2. Writes them to `auth-profiles.json`
3. Validates and repairs `openclaw.json`
4. Restarts the gateway
5. Health-checks with retry loop until connected

Registered to run automatically via:
- **Windows Scheduled Task:** `OpenClaw AutoFix` (triggers on login)
- **Startup folder shortcut** (backup trigger)

---

## Cost Analysis

| Approach | Monthly Cost | Billing Model | Token Limits |
|----------|-------------|---------------|--------------|
| Anthropic API Key | Variable ($50-500+) | Pay per token | None (pay what you use) |
| Claude Code Subscription | $100 flat | Fixed monthly | Subscription tier limits |
| **This Integration** | **$0 incremental** | Rides on existing sub | Same as Claude Code |

If you're already paying for Claude Code, this integration costs nothing extra. You're reusing credentials you already have for a capability (autonomous agents via OpenClaw) that would otherwise require a separate API account and unpredictable per-token billing.

---

## Final Result

OpenClaw dashboard showing:
- **Health:** OK (green)
- **Version:** 2026.3.2
- **Agent:** "Berma" — first-principles thinking CTO advisor
- **Model:** Claude Sonnet 4.5 with extended thinking
- **Channels:** Discord, Telegram, iMessage enabled
- **Identity files configured:** IDENTITY.md, USER.md, SOUL.md
- **Personality:** Jargon-free, first principles, Zero to One + Customer Centric Selling + Alex Hormozi playbooks

The agent is live, responding, and asking intelligent follow-up questions about business structure — all running on the Claude Code subscription.

---

## Files Modified

| File | Change |
|------|--------|
| `~/.openclaw/openclaw.json` | Fixed auth mode (`token` -> `oauth`), updated model (`claude-3-5-sonnet-20241022` -> `claude-sonnet-4-5`) |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | Replaced placeholder with live OAuth credentials from Claude Code |
| `~/.openclaw/auto-fix.ps1` | **Created** — auto-sync + restart + health check script |
| `~/.openclaw/auto-fix.cmd` | **Created** — CMD wrapper for scheduled task |
| Windows Scheduled Task `OpenClaw AutoFix` | **Created** — runs auto-fix on login |
| Startup folder shortcut | **Created** — backup auto-start |

## Key Takeaway

OpenClaw's onboarding assumes you have a standalone API key. It doesn't tell you that you can use your existing Claude Code subscription. But the plumbing is already there — OAuth credential type, token refresh logic, the `anthropic:claude-cli` profile concept — it's just not surfaced in the UI or docs. With a credential sync script and the right config, you get a self-hosted autonomous agent platform for $0 incremental cost on top of a subscription you're already paying for.

---

*Generated with Claude Code (Opus 4.6) during a live debugging and integration session.*
