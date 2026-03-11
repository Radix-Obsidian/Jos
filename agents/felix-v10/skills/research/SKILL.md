---
name: research
description: Research topics using Grok's web search and X/Twitter search via the xAI Responses API. Use for finding media appearances, news, people, companies, or any task requiring real-time web data.
---

# Research — Grok Web + X Search

## How It Works
Uses xAI's **Responses API** (`/v1/responses`) with built-in tools (`web_search`, `x_search`) for real-time research. This is NOT the chat completions endpoint — that has no search capability.

## API Key
Store your xAI API key at `~/.config/xai/api_key`.

```bash
XAI_KEY=$(cat ~/.config/xai/api_key)
```

## Basic Research Query
```bash
XAI_KEY=$(cat ~/.config/xai/api_key)

curl -s https://api.x.ai/v1/responses \
  -H "Authorization: Bearer $XAI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-4-1-fast",
    "input": "YOUR RESEARCH QUERY HERE",
    "tools": [{"type": "web_search"}, {"type": "x_search"}]
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('output', []):
    if item.get('type') == 'message':
        for c in item.get('content', []):
            if c.get('type') == 'output_text':
                print(c['text'])
            for ann in c.get('annotations', []):
                if ann.get('url'):
                    print(f'  [{ann[\"url\"]}]')
"
```

## Tool Options
| Tool | Purpose |
|------|---------|
| `web_search` | Search the web, browse pages, extract info |
| `x_search` | Search X/Twitter posts and discussions |

Both can be used together: `"tools": [{"type": "web_search"}, {"type": "x_search"}]`

### Web Search Parameters
```json
{"type": "web_search", "allowed_domains": ["example.com"]}
{"type": "web_search", "excluded_domains": ["reddit.com"]}
```

## Model Requirements
- **Only grok-4 family models** support server-side tools
- Use `grok-4-1-fast` for speed (recommended)
- Older models do NOT support tools

## Important Notes
- The `/chat/completions` endpoint does NOT support web search — only `/responses` does
- Responses can take 30-90 seconds for complex queries
- Always use `yieldMs: 90000` and `timeout: 120` for exec calls

## Parsing the Response
The response `output` array contains:
- `web_search_call` items (searches performed)
- `x_search_call` items (X searches performed)
- `message` items with `content[].output_text` (the final answer)
- Annotations with citation URLs

## When to Use
- Finding media appearances, podcast episodes, interviews
- Researching people, companies, events
- Checking recent news or social media discussion
- X/Twitter sentiment or discussion analysis

## When NOT to Use
- Simple factual questions (use regular chat)
- Code generation or analysis
- Tasks that don't need web data
