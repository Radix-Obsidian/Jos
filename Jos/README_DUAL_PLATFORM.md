# Jos Sales Automation - Dual Platform Setup

**Queen B Revenue Generation Pipeline for Voco V2**

This guide covers setup and operation on both **Windows** (development/testing) and **Mac** (production/24-7).

---

## Quick Start

### Windows (Development)
```powershell
# 1. Copy environment template
copy .env.example .env

# 2. Edit .env with your API keys
notepad .env

# 3. Verify setup
python startup.py

# 4. Start dashboard
python web_dashboard.py

# 5. Start scheduler (in another terminal)
python scheduler.py
```

### Mac (Production)
```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your API keys
nano .env

# 3. Verify setup
python3 startup.py

# 4. Start full pipeline
python3 joy_sales.py

# 5. Monitor dashboard at http://127.0.0.1:5000
```

---

## Platform-Specific Configurations

### Windows Configuration (`config_windows.py`)
- **Purpose:** Development and testing
- **Database:** `C:\Users\autre\.openclaw\jos_db.sqlite`
- **Logs:** `C:\Users\autre\.openclaw\jos_logs\jos_windows.log`
- **Scheduler:** Hourly X scanning, daily follow-ups
- **Workers:** 4 concurrent
- **Features Enabled:**
  - X monitoring
  - Email outreach
  - Follow-up automation
  - Lead scoring
  - Dashboard
- **Features Disabled:**
  - Peekaboo (macOS only)
  - Things integration (macOS only)
  - iMessage integration (macOS only)

### Mac Configuration (`config_mac.py`)
- **Purpose:** Production and 24/7 operation
- **Database:** `~/.openclaw/jos_db.sqlite`
- **Logs:** `~/.openclaw/jos_logs/jos_mac.log`
- **Scheduler:** 30-minute X scanning, 4x daily follow-ups, hourly reports
- **Workers:** 8 concurrent
- **Features Enabled:**
  - All Windows features PLUS:
  - Peekaboo (macOS UI automation)
  - Things 3 integration (task management)
  - iMessage integration
  - Advanced analytics
  - Predictive scoring
  - 24/7 operation mode

---

## Environment Variables

Create `.env` file in Jos directory with these variables:

```bash
# Claude API (Required)
CLAUDE_API_KEY=sk-ant-oat01-your_token_here

# X/Twitter API (Required)
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret

# Gmail API (Required)
GMAIL_API_KEY=your_gmail_api_key
GMAIL_SENDER=your_email@gmail.com

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789
OPENCLAW_GATEWAY_TOKEN=your_gateway_token

# Optional
BRAVE_API_KEY=your_brave_api_key  # For web search

# Platform (auto-detected, but can be overridden)
PLATFORM=windows  # or 'mac'
```

---

## Architecture

### Components

**Outreach Hunter** (`agents/outreach_hunter.py`)
- Scans X for voice-coding complaints
- Identifies target users
- Scores leads

**Follow-Up Architect** (`agents/follow_up_architect.py`)
- Manages 3-touch follow-up sequence
- Tracks response timing
- Escalates hot leads

**Closer Manager** (`agents/closer_manager.py`)
- Prepares closing scripts
- Books demo meetings
- Handles objection handling

**Auditor** (`agents/auditor.py`)
- Validates all interactions
- Tracks KPIs
- Generates reports

### Data Flow

```
X/Twitter API
    |
    v
Outreach Hunter (scan + score)
    |
    v
Lead Database
    |
    v
Follow-Up Architect (day 3/7)
    |
    v
Closer Manager (demo booking)
    |
    v
Dashboard + Email Reports
```

---

## Running the Pipeline

### Windows - Development Mode

**Terminal 1: Dashboard**
```powershell
cd C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos
python web_dashboard.py
# Access at http://127.0.0.1:5000
```

**Terminal 2: Scheduler**
```powershell
cd C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos
python scheduler.py
# Runs X scanning and follow-ups on schedule
```

**Terminal 3: Manual Testing**
```powershell
cd C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos
python x_scraper.py  # Test X scraping
python engagement_drafter.py  # Test message drafting
python lead_enricher.py  # Test lead enrichment
```

### Mac - Production Mode

**Single Command (24/7)**
```bash
cd ~/openclaw-projects/Jos
python3 joy_sales.py
# Runs full pipeline with:
# - X scanning every 30 minutes
# - Follow-ups at 9 AM, 1 PM, 5 PM ET
# - Hourly email reports
# - Dashboard at http://127.0.0.1:5000
```

**Monitor in Background**
```bash
# View logs in real-time
tail -f ~/.openclaw/jos_logs/jos_mac.log

# Check scheduler status
python3 scheduler.py --status

# View database
sqlite3 ~/.openclaw/jos_db.sqlite
```

---

## Queen B Kickoff Prompt

The Queen B agent is configured with this prompt (in `queen_b_kickoff.txt`):

```
Queen B, activate the Hive and start Phase 1 revenue generation.

Priorities:
1. Use the Jos sales A-Team (Outreach Hunter, Follow-Up Architect, Closer Manager, Auditor) as the Marketing department foundation.
2. Scan X live for posts/complaints about 'voice cutoff', 'Windsurf timeout', 'Cursor voice limit', 'Wispr Flow frustration', or general 'voice to code' pains from vibe technical founders.
3. Generate personalized outreach DMs targeting those users, pitching Voco V2 beta at $39/mo (emphasize only 10 founding seats left — rising to $59 soon).
4. Track responses, follow up on day 3/7, detect hot leads, and prepare closing scripts/meeting requests.
5. Log all interactions and KPIs (response rate, leads, etc.) in the dashboard.
6. If any task requires complex reasoning or code tweaks (e.g., customizing DM templates), route to Claude full subscription computer-use mode.

Run this 24/7. Email me summaries every 4 hours or on new lead activity.

Channel my mom's energy — helpful, direct, always closing with warmth.

Begin now.
```

---

## Monitoring & Reporting

### Windows Dashboard
- **URL:** `http://127.0.0.1:5000`
- **Metrics:**
  - Leads found (hourly)
  - Outreach sent
  - Response rate
  - Hot leads
  - Meetings booked

### Mac Reporting
- **Email Reports:** Hourly (to GMAIL_SENDER)
- **Metrics:** Same as Windows + conversion rate, avg response time
- **Log File:** `~/.openclaw/jos_logs/jos_mac.log`

### OpenClaw Dashboard
- **URL:** `http://127.0.0.1:18789`
- **Token:** See `.openclaw/openclaw.json`
- **Features:**
  - Agent status
  - Message history
  - Skill usage
  - Memory search

---

## Troubleshooting

### Windows Issues

**OpenClaw not found in PATH**
```powershell
# Refresh PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
openclaw --version
```

**Gateway service failed to install**
```powershell
# Run PowerShell as Administrator
Start-Process powershell -Verb RunAs
openclaw gateway install --force
```

**Missing API keys**
```powershell
# Check .env file
cat .env

# Verify environment variables
$env:CLAUDE_API_KEY
$env:X_API_KEY
```

### Mac Issues

**Homebrew dependencies missing**
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Go
brew install go

# Re-run onboarding
openclaw onboard
```

**Database locked**
```bash
# Check for running processes
ps aux | grep jos

# Kill if needed
kill -9 <PID>

# Restart
python3 joy_sales.py
```

**Email reports not sending**
```bash
# Check Gmail API key
echo $GMAIL_API_KEY

# Verify sender address
echo $GMAIL_SENDER

# Check logs
tail -f ~/.openclaw/jos_logs/jos_mac.log | grep -i email
```

---

## Performance Tuning

### Windows (Development)
- **Workers:** 4 (adjust in `config_windows.py`)
- **Batch Size:** 10 leads per batch
- **Cache TTL:** 1 hour
- **Good for:** Testing, debugging, iterating

### Mac (Production)
- **Workers:** 8 (adjust in `config_mac.py`)
- **Batch Size:** 20 leads per batch
- **Cache TTL:** 30 minutes
- **Memory Optimization:** Enabled
- **Good for:** 24/7 operation, high volume

---

## Deployment Checklist

### Windows Setup
- [ ] Clone Jos repo
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in all API keys
- [ ] Run `python startup.py` (verify all checks pass)
- [ ] Start dashboard: `python web_dashboard.py`
- [ ] Start scheduler: `python scheduler.py`
- [ ] Test X scraping: `python x_scraper.py`
- [ ] Access dashboard at `http://127.0.0.1:5000`

### Mac Setup
- [ ] Install Homebrew
- [ ] Install Go: `brew install go`
- [ ] Install Node.js: `brew install node@22`
- [ ] Install OpenClaw: `npm install -g openclaw`
- [ ] Run `openclaw onboard` (install all 48 skills)
- [ ] Copy Jos repo to `~/openclaw-projects/Jos`
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in all API keys
- [ ] Run `python3 startup.py` (verify all checks pass)
- [ ] Start pipeline: `python3 joy_sales.py`
- [ ] Monitor logs: `tail -f ~/.openclaw/jos_logs/jos_mac.log`
- [ ] Access dashboard at `http://127.0.0.1:5000`

---

## Support & Documentation

- **OpenClaw Docs:** https://docs.openclaw.ai
- **LangGraph Docs:** https://langchain-ai.github.io/langgraph
- **X API Docs:** https://developer.twitter.com/en/docs
- **Claude API Docs:** https://docs.anthropic.com

---

## Next Steps

1. **Set up environment variables** (`.env` file)
2. **Choose your platform** (Windows for testing, Mac for production)
3. **Run startup verification** (`python startup.py`)
4. **Start the pipeline** (dashboard + scheduler on Windows, `joy_sales.py` on Mac)
5. **Monitor dashboard** at `http://127.0.0.1:5000`
6. **Check reports** (Windows: dashboard, Mac: email + logs)

---

**Ready to activate Queen B and start Phase 1 revenue generation!** 🚀
