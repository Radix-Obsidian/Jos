# Felix — CEO Mode AI Agent

Felix is a revenue-focused AI persona for OpenClaw. He doesn't wait for tasks — he proposes plans, tracks execution, monitors your business, and drives toward your revenue target.

## What's Included

### Core Files
- **SOUL.md** — Felix's personality, voice, and operating style
- **IDENTITY.md** — Mission, daily rhythm, and customization guide
- **AGENTS.md** — Workspace setup with memory architecture (PARA system)
- **HEARTBEAT.md** — Automated health check and review cycle
- **TOOLS.md** — Coding agent orchestration patterns (Ralph loops, tmux)

### Skills
- **coding-agent-loops** — Persistent coding agent sessions with auto-retry
- **revenue-metrics** — Stripe revenue tracking across multiple accounts
- **site-health** — Production site availability monitoring

## Quick Start

1. Copy these files into your OpenClaw workspace (usually `~/clawd/`)
2. Edit `IDENTITY.md` with your company name, revenue target, and products
3. Edit `AGENTS.md` with your available tools and API keys
4. Edit `HEARTBEAT.md` with your specific sites, services, and checks
5. Configure `skills/revenue-metrics/scripts/stripe-metrics.py` with your Stripe accounts
6. Configure `skills/site-health/scripts/check.sh` with your production URLs

## How Felix Works

**Daily cycle:**
- Heartbeats check site health, running processes, and execution against plan
- Nightly deep dive reviews revenue, proposes tomorrow's plan
- Morning execution against the approved plan

**Memory system:**
- Layer 1: Entity knowledge graph (`~/life/` using PARA)
- Layer 2: Daily timeline notes (`memory/YYYY-MM-DD.md`)
- Layer 3: User preferences and patterns (`MEMORY.md`)

**Coding orchestration:**
- Long-running tasks go in tmux sessions (survive restarts)
- Ralph loops auto-retry failed agent runs with fresh context
- Completion hooks notify you immediately when work finishes

## Philosophy

Felix thinks like an owner, not an employee. He'll:
- Propose growth experiments unprompted
- Fix problems before reporting them
- Track revenue daily and hold himself accountable
- Never hedge when he has a clear position

Built by [The Masinov Company](https://shopclawmart.com).
