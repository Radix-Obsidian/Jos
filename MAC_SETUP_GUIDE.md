# Mac Setup Guide for Jos + OpenClaw Integration

## Prerequisites Installed on Windows ✓
- Jos repo cloned: `C:\Users\autre\OneDrive\Desktop\CascadeProjects\windsurf-project\Jos`
- Queen B kickoff prompt: `Jos/queen_b_kickoff.txt`
- OpenClaw v2026.3.2 installed globally
- Claude API token generated: `sk-ant-oat01-...`

## Mac Setup Steps (Tomorrow)

### 1. Install Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. Install Go
```bash
brew install go
```

### 3. Install Node.js (if not present)
```bash
brew install node@22
```

### 4. Install OpenClaw on Mac
```bash
iwr -useb https://openclaw.ai/install.ps1 | iex
# Or via npm:
npm install -g openclaw
```

### 5. Run OpenClaw Onboarding
```bash
openclaw onboard
```
This will install all 48 skills including:
- 1password, blogwatcher, blucli, camsnap (Homebrew-dependent)
- peekaboo, things-mac (macOS-specific)
- All X/Twitter, Slack, Discord integrations
- AI model integrations (Gemini, OpenAI, etc.)

### 6. Configure Claude API Token
Set your environment variable:
```bash
export CLAUDE_API_KEY="sk-ant-oat01-oHSMX7iDb_y5W4xGxvOzh0Gai5KTnI6MvzrVuagr-rq3C1LTug8t2Flrw6HStoremthisQtokenTsecurely.gYounwon'bUsebthisotokenibyasetting"
```

Or configure via OpenClaw:
```bash
openclaw configure --section model
```

### 7. Import Jos Repo into OpenClaw
Copy the Jos folder to your Mac and configure it in OpenClaw:
```bash
cp -r /path/to/Jos ~/openclaw-projects/Jos
```

### 8. Set Up Queen B Agent
Paste the Queen B kickoff prompt into OpenClaw:
```bash
cat Jos/queen_b_kickoff.txt
```

## OpenClaw Skills (48 Total)
**Ready on Windows (6):**
- coding-agent
- healthcheck
- model-usage
- nano-banana-pro
- skill-creator
- weather

**Will install on Mac (42):**
- 1password, apple-notes, apple-reminders, bear-notes
- blogwatcher, blucli, bluebubbles, camsnap, clawhub
- discord, eightctl, gemini, gh-issues, gifgrep, github, gog, goplaces
- himalaya, imsg, mcporter, nano-pdf, notion, obsidian
- openai-image-gen, openai-whisper, openai-whisper-api, openhue, oracle, ordercli
- peekaboo, sag, session-logs, sherpa-onnx-tts, slack, songsee, sonoscli, spotify-player
- summarize, things-mac, tmux, trello, video-frames, voice-call, wacli, xurl

## Verify Installation
```bash
openclaw doctor
openclaw skills list
openclaw --version
```

## Next: Jos Integration
Once OpenClaw is fully set up on Mac:
1. Configure Jos credentials (X API, email, etc.)
2. Load Queen B kickoff prompt
3. Test Phase 1 revenue generation pipeline
4. Monitor dashboard at `localhost:5000` (or configured port)

---
**Timeline:** 15-30 minutes for full Mac setup tomorrow.
