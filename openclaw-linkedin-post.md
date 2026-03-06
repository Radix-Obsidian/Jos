I just hacked my $100/month Claude Code subscription into a full autonomous agent platform. Zero extra cost.

Here's what happened.

I set up OpenClaw — an open-source self-hosted AI agent gateway that connects to Discord, Telegram, iMessage, and more. Problem: it wants a standalone Anthropic API key. Pay-per-token. Variable billing. No thanks.

I'm already paying $100/month for Claude Code. That subscription includes inference via OAuth tokens. So why can't OpenClaw use those credentials?

Turns out — it can. The plumbing is already there. It's just not documented or surfaced anywhere in the UI.

THE DISCOVERY

OpenClaw has a two-layer credential system:
- openclaw.json = config (provider name + auth mode, no secrets)
- auth-profiles.json = actual credentials (tokens, keys, OAuth)

The onboarding wizard writes your API key into the wrong layer. The config validator rejects it. You get 401 errors. The model ID it defaults to is deprecated. Health goes offline every restart.

Meanwhile, Claude Code quietly stores live OAuth credentials at ~/.claude/.credentials.json — access token, refresh token, expiry. And OpenClaw's source code already has an "oauth" credential type with built-in token refresh logic.

Nobody connected the dots.

THE FIX

1. Read OAuth credentials from Claude Code's credential file
2. Write them into OpenClaw's auth-profiles.json as type "oauth"
3. Set config auth mode to "oauth" instead of "token"
4. Update the model from the deprecated claude-3-5-sonnet to claude-sonnet-4-5 with thinking enabled
5. Built an auto-fix script that syncs fresh tokens on every boot

Total time from broken to working: one session with Claude Code as my pair debugger.

THE RESULT

A fully operational AI agent named "Berma" running Claude Sonnet 4.5 with extended thinking. Connected to Discord, Telegram, and iMessage. Configured as a first-principles thinking CTO advisor using Zero to One, Customer Centric Selling, and Alex Hormozi playbooks.

Running on my existing subscription. $0 incremental.

COST COMPARISON

API Key: $50-500+/month variable
Claude Code Sub: $100/month flat
This integration: $0 extra — rides on what you're already paying

THE TAKEAWAY

Most tools assume you'll pay twice — once for the IDE, once for the API. But if you read the source code, the integration points are already there. The OAuth flow, the token refresh, the credential types — all built in. Just not advertised.

Stop paying per token for things your subscription already covers. Read the source. Connect the dots.

The auto-fix script, full technical breakdown, and every config change are documented in my repo.

#AI #ClaudeCode #OpenClaw #Anthropic #AutonomousAgents #BuildInPublic #StartupLife #FirstPrinciples