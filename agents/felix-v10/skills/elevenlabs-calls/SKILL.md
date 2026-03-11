---
name: elevenlabs-calls
description: Make AI phone calls using ElevenLabs Conversational AI and Twilio.
---

# ElevenLabs Phone Calls

Make outbound AI phone calls using ElevenLabs Conversational AI agents via Twilio.

## Prerequisites

1. **ElevenLabs API Key** — set `ELEVENLABS_API_KEY` env var or store at `~/.config/elevenlabs/api_key`
2. **ElevenLabs Agent** — create at https://elevenlabs.io/app/agents
3. **Twilio Phone Number** — import into ElevenLabs at https://elevenlabs.io/app/agents/phone-numbers

## Quick Start

```bash
# List your agents
{baseDir}/scripts/agents.sh

# List your phone numbers
{baseDir}/scripts/phones.sh

# Make a call
{baseDir}/scripts/call.sh --agent <agent_id> --phone <phone_number_id> --to "+15551234567"

# Check conversation transcript
{baseDir}/scripts/conversation.sh <conversation_id>
```

## Commands

### Make Outbound Call
```bash
{baseDir}/scripts/call.sh \
  --agent <agent_id> \
  --phone <phone_number_id> \
  --to "+15551234567" \
  [--vars '{"name":"John","appointment":"Monday 9am"}']
```

### List Recent Conversations
```bash
{baseDir}/scripts/conversations.sh [--agent <agent_id>] [--limit 10]
```

### Get Conversation Details
```bash
{baseDir}/scripts/conversation.sh <conversation_id>
{baseDir}/scripts/conversation.sh <conversation_id> --transcript
{baseDir}/scripts/conversation.sh <conversation_id> --audio > call.mp3
```

## Dynamic Variables

Pass context to your agent:
```bash
{baseDir}/scripts/call.sh \
  --agent abc123 --phone phone_xyz --to "+15121234567" \
  --vars '{"customer_name":"Jane","reason":"appointment follow-up"}'
```

Reference in your agent's system prompt as `{{customer_name}}`, `{{reason}}`, etc.

## Costs
- ElevenLabs: ~$0.07-0.15/min depending on plan
- Twilio: ~$0.014/min + phone number (~$1/mo)
