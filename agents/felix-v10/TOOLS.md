# TOOLS.md -- Tool Notes

This file is for notes about your local toolchain. Felix reads it to understand what's available and how to use it.

## Coding Sub-Agents

### Ralph Loop (preferred for non-trivial tasks)
Use `ralphy` to wrap coding agents in a retry loop with completion validation. Ralph restarts with fresh context each iteration -- prevents stalling, context bloat, and premature exits.

```bash
# Single task with Codex
ralphy --codex "Fix the authentication bug in the API"

# PRD-based workflow (best for multi-step work)
ralphy --codex --prd PRD.md

# With Claude Code instead
ralphy --claude "Refactor the database layer"

# Parallel agents on separate tasks
ralphy --codex --parallel --prd PRD.md

# Limit iterations
ralphy --codex --max-iterations 10 "Build the feature"
```

### Codex CLI (for direct use)
```bash
codex exec --full-auto "Task description here"
```

### When to Use What
- **Ralph**: Multi-step features, PRD checklists, tasks that have stalled
- **Raw Codex**: Tiny focused fixes, one-file changes, exploratory work

## Background Processes (Windows)

No tmux on Windows. Use background processes instead:

```powershell
# Start a background process
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "script.py" -RedirectStandardOutput "out.log"

# Check if a process is running
tasklist | findstr python

# Kill a process
taskkill /F /IM python.exe /FI "WINDOWTITLE eq my-task"
```

For long-running agents, use `Start-Process` and poll logs for completion.

## Exec Timeout Defaults

| Category | yieldMs | timeout | Example |
|---|---|---|---|
| Quick commands | default | -- | `ls`, `cat` |
| CLI tools | 30000 | 45 | `gh pr list` |
| Package installs | 60000 | 120 | `npm install` |
| Builds & deploys | 60000 | 180 | `npm run build` |
| Long-running | -- | -- | Use `Start-Process` + poll |

## Windows Notes
- **jq**: Install via `winget install jqlang.jq` if not available
- **tmux**: Not available on Windows. Use `Start-Process` for background tasks, `tasklist` for monitoring
- **ralphy-cli**: Check availability with `ralphy --version`. If not installed, use `codex` directly
- **curl**: Available natively on Windows 11
- **Python**: Use `python` (not `python3`) on Windows
