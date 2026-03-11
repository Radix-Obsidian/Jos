---
name: coding-agent-loops
description: Run long-lived AI coding agents (Codex, Claude Code) in persistent tmux sessions with Ralph retry loops and completion hooks. Use when running multi-step coding tasks, PRD-based workflows, or any programming agent that needs to survive restarts, retry on failure, and notify on completion.
---

# Coding Agent Loops

Run AI coding agents in persistent, self-healing sessions with automatic retry and completion notification.

## Core Concept

Instead of one long agent session that stalls or dies, run many short sessions in a loop. Each iteration starts fresh — no accumulated context. The agent picks up where it left off via files and git history.

## Prerequisites

- `tmux` installed
- `ralphy-cli`: `npm install -g ralphy-cli`
- A coding agent: `codex` (Codex CLI) or `claude` (Claude Code)
- Stable tmux socket: always use `~/.tmux/sock`

## Quick Start

### Single Task
```bash
tmux -S ~/.tmux/sock new -d -s my-task \
  "cd /path/to/repo && ralphy --codex 'Fix the authentication bug'; \
   EXIT_CODE=\$?; echo EXITED: \$EXIT_CODE; \
   openclaw system event --text 'my-task finished (exit \$EXIT_CODE) in \$(pwd)' --mode now; \
   sleep 999999"
```

### PRD-Based Workflow
```bash
tmux -S ~/.tmux/sock new -d -s feature-build \
  "cd /path/to/repo && ralphy --codex --prd PRD.md; \
   EXIT_CODE=\$?; echo EXITED: \$EXIT_CODE; \
   openclaw system event --text 'feature-build finished (exit \$EXIT_CODE)' --mode now; \
   sleep 999999"
```

### Parallel Agents
```bash
ralphy --codex --parallel --prd PRD.md
```

## Session Management

```bash
# List active sessions
tmux -S ~/.tmux/sock list-sessions

# Check progress
tmux -S ~/.tmux/sock capture-pane -t my-task -p | tail -20

# Kill a session
tmux -S ~/.tmux/sock kill-session -t my-task
```

## Command Anatomy

1. **Stable socket:** `-S ~/.tmux/sock` (survives macOS `/tmp` cleanup)
2. **Named session:** `-s <name>` (for monitoring)
3. **PATH fix:** `PATH=/opt/homebrew/bin:$PATH` (if tools aren't found)
4. **The agent command:** `codex exec --full-auto` or `ralphy --codex`
5. **Completion hook:** `openclaw system event` for instant notification
6. **Sleep tail:** `sleep 999999` keeps shell alive for readable output

## PRD Format

Ralph tracks completion via markdown checklists:

```markdown
## Tasks
- [ ] Create the API endpoint
- [ ] Add input validation
- [ ] Write tests
- [x] Already done (skipped)
```

## When to Use What

| Scenario | Tool |
|----------|------|
| Multi-step feature with PRD | `ralphy --codex --prd PRD.md` |
| Task that has stalled before | `ralphy --codex` (auto-retry) |
| Parallel independent tasks | `ralphy --codex --parallel --prd PRD.md` |
| Tiny focused fix | `codex exec --full-auto` |
| Skip tests for speed | `ralphy --codex --fast` |
| Use Claude Code | `ralphy --claude` |

## Post-Completion Verification

Before declaring success or failure:
1. `git log --oneline -3` — did the agent commit?
2. `git diff --stat` — uncommitted changes?
3. Read the tmux pane output — what actually happened?

## Troubleshooting

- **"Failed to refresh token"** → run `codex auth login`
- **Agent reads files and exits** → wrap in Ralph loop
- **API rate limits (429s)** → reduce parallelism or stagger starts
- **Session died** → restart with same command
