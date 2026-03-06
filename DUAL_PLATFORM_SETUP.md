# Dual-Platform OpenClaw + Jos Setup (Windows & Mac)

## Overview
This setup configures OpenClaw and Jos for both Windows (development/testing) and Mac (production) with hardware-optimized configurations.

---

## WINDOWS SETUP (Development/Testing)

### ✓ Already Completed
- OpenClaw v2026.3.2 installed globally
- Jos repo cloned: `C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos`
- Queen B kickoff prompt created: `Jos/queen_b_kickoff.txt`
- Claude API token generated
- OpenClaw onboarding completed (6/48 skills ready)

### Gateway Service Install (Admin Required)

**Step 1: Open PowerShell as Administrator**
1. Press `Win + X`
2. Select "Windows PowerShell (Admin)" or "Terminal (Admin)"
3. Run:
```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
openclaw gateway install --force
```

**Step 2: Verify Gateway Service**
```powershell
openclaw gateway status
openclaw doctor
```

### Windows Hardware Optimization
Create `C:\Users\autre\.openclaw\openclaw.json` with Windows-optimized settings:

```json
{
  "gateway": {
    "bind": "127.0.0.1",
    "port": 18789,
    "workers": 4,
    "timeout": 30000
  },
  "agents": {
    "defaults": {
      "model": "claude-3-5-sonnet-20241022",
      "temperature": 0.7,
      "maxTokens": 4096,
      "memorySearch": {
        "enabled": true,
        "provider": "openai"
      }
    }
  },
  "skills": {
    "enabled": [
      "coding-agent",
      "healthcheck",
      "model-usage",
      "nano-banana-pro",
      "skill-creator",
      "weather",
      "github",
      "slack",
      "discord"
    ]
  }
}
```

### Windows Jos Configuration
Edit `Jos/config.py` for Windows environment:

```python
# Windows-specific settings
WINDOWS_MODE = True
DASHBOARD_PORT = 5000
DATABASE_PATH = r"C:\Users\autre\.openclaw\jos_db.sqlite"
LOG_PATH = r"C:\Users\autre\.openclaw\jos_logs"

# API Keys (set via environment variables)
import os
X_API_KEY = os.getenv("X_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
GMAIL_API_KEY = os.getenv("GMAIL_API_KEY")

# Scheduler settings for Windows
SCHEDULER_TIMEZONE = "US/Eastern"
SCHEDULER_JOBS = {
    "scan_x": {"trigger": "interval", "hours": 1},
    "follow_up": {"trigger": "cron", "hour": "9,17", "minute": "0"},
    "dashboard_sync": {"trigger": "interval", "minutes": 5}
}
```

---

## MAC SETUP (Production)

### Prerequisites
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install node@22 go python@3.11 sqlite3
brew link node@22

# Verify installations
node --version  # v22+
go version      # go1.22+
python3 --version  # 3.11+
```

### OpenClaw Installation
```bash
# Install OpenClaw via npm
npm install -g openclaw

# Or via direct script
iwr -useb https://openclaw.ai/install.ps1 | iex
```

### Run Full Onboarding
```bash
openclaw onboard
```
This will install all 48 skills including:
- Homebrew-dependent: 1password, blogwatcher, blucli, camsnap, openai-whisper, video-frames
- macOS-specific: peekaboo, things-mac, imsg, apple-notes, apple-reminders
- Cloud integrations: slack, discord, github, gemini, openai-image-gen

### Mac Hardware Optimization
Create `~/.openclaw/openclaw.json` with Mac-optimized settings:

```json
{
  "gateway": {
    "bind": "127.0.0.1",
    "port": 18789,
    "workers": 8,
    "timeout": 60000,
    "enableUds": true
  },
  "agents": {
    "defaults": {
      "model": "claude-3-5-sonnet-20241022",
      "temperature": 0.7,
      "maxTokens": 8192,
      "memorySearch": {
        "enabled": true,
        "provider": "openai",
        "embeddingModel": "text-embedding-3-small"
      }
    }
  },
  "skills": {
    "enabled": [
      "coding-agent",
      "healthcheck",
      "model-usage",
      "nano-banana-pro",
      "skill-creator",
      "weather",
      "github",
      "slack",
      "discord",
      "peekaboo",
      "things-mac",
      "imsg",
      "1password",
      "openai-whisper",
      "video-frames",
      "xurl"
    ]
  }
}
```

### Mac Jos Configuration
Edit `Jos/config.py` for Mac environment:

```python
# Mac-specific settings
WINDOWS_MODE = False
MAC_MODE = True
DASHBOARD_PORT = 5000
DATABASE_PATH = os.path.expanduser("~/.openclaw/jos_db.sqlite")
LOG_PATH = os.path.expanduser("~/.openclaw/jos_logs")

# API Keys (set via environment variables)
import os
X_API_KEY = os.getenv("X_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
GMAIL_API_KEY = os.getenv("GMAIL_API_KEY")

# Scheduler settings for Mac (24/7 production)
SCHEDULER_TIMEZONE = "US/Eastern"
SCHEDULER_JOBS = {
    "scan_x": {"trigger": "interval", "minutes": 30},  # More frequent on Mac
    "follow_up": {"trigger": "cron", "hour": "9,13,17", "minute": "0"},
    "dashboard_sync": {"trigger": "interval", "minutes": 2},
    "report_summary": {"trigger": "cron", "hour": "*", "minute": "0"}  # Hourly reports
}

# Mac-specific integrations
PEEKABOO_ENABLED = True  # macOS UI automation
THINGS_ENABLED = True    # Things 3 task management
IMSG_ENABLED = True      # iMessage integration
```

---

## Environment Variables (Both Platforms)

Create `.env` file in Jos directory:

```bash
# Claude API
CLAUDE_API_KEY=sk-ant-oat01-oHSMX7iDb_y5W4xGxvOzh0Gai5KTnI6MvzrVuagr-rq3C1LTug8t2Flrw6HStoremthisQtokenTsecurely.gYounwon'bUsebthisotokenibyasetting

# X/Twitter API
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret

# Gmail API
GMAIL_API_KEY=your_gmail_api_key
GMAIL_SENDER=your_email@gmail.com

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789
OPENCLAW_GATEWAY_TOKEN=your_gateway_token

# Brave Search (optional, for web search)
BRAVE_API_KEY=your_brave_api_key
```

---

## Queen B Agent Configuration

### Windows (Development)
```bash
# Paste Queen B kickoff prompt
cat Jos/queen_b_kickoff.txt

# Configure in OpenClaw
openclaw configure --section agents
# Add custom agent with Queen B prompt
```

### Mac (Production)
```bash
# Copy Jos repo to Mac
cp -r Jos ~/openclaw-projects/Jos

# Configure Queen B agent with full automation
openclaw configure --section agents
# Enable 24/7 scheduling
# Configure email reporting (hourly)
# Set up X/Twitter monitoring
```

---

## Verification Checklist

### Windows
- [ ] PowerShell Admin: `openclaw gateway install --force` completed
- [ ] `openclaw doctor` shows no critical errors
- [ ] `openclaw gateway status` shows running
- [ ] Dashboard accessible: `http://127.0.0.1:18789`
- [ ] Jos repo verified: `dir Jos`
- [ ] Queen B prompt ready: `cat Jos/queen_b_kickoff.txt`

### Mac
- [ ] Homebrew installed: `brew --version`
- [ ] Go installed: `go version`
- [ ] Node.js v22+: `node --version`
- [ ] OpenClaw installed: `openclaw --version`
- [ ] All 48 skills available: `openclaw skills list`
- [ ] Gateway running: `openclaw gateway status`
- [ ] Dashboard accessible: `http://127.0.0.1:18789`
- [ ] Jos repo copied: `ls ~/openclaw-projects/Jos`
- [ ] Queen B agent configured

---

## Running Jos + Queen B

### Windows (Testing/Development)
```powershell
cd C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos
python joy_sales.py
# Monitor dashboard at http://127.0.0.1:5000
```

### Mac (Production/24/7)
```bash
cd ~/openclaw-projects/Jos
python3 joy_sales.py
# Monitor dashboard at http://127.0.0.1:5000
# OpenClaw will handle scheduling and automation
```

---

## Troubleshooting

### Windows Gateway Install Fails
```powershell
# Run as Administrator
Start-Process powershell -ArgumentList '-NoExit', '-Command', 'openclaw gateway install --force' -Verb RunAs
```

### Mac Skills Installation Fails
```bash
# Ensure Homebrew is working
brew doctor

# Reinstall specific skill
openclaw skills check 1password
brew install 1password-cli

# Re-run onboarding
openclaw onboard
```

### Claude API Token Issues
```bash
# Windows
$env:CLAUDE_API_KEY = "your_token_here"

# Mac
export CLAUDE_API_KEY="your_token_here"

# Verify
openclaw configure --section model
```

---

## Timeline

**Windows Setup:** 30 minutes (Gateway install + verification)
**Mac Setup:** 45 minutes (Homebrew + all 48 skills + Jos import)
**Total:** ~1.5 hours for full dual-platform setup

Both platforms ready for simultaneous operation with hardware-optimized configurations.
