---
name: talking-head
description: Generate talking-head avatar videos from a script. Handles ElevenLabs TTS audio generation and VEED Fabric 1.0 video synthesis via Fal API.
---

# Talking Head Video Generator

Create lip-synced avatar videos from text scripts.

## Pipeline
1. **Write script** — the words your avatar will speak
2. **Generate audio** — ElevenLabs TTS with your chosen voice
3. **Generate video** — VEED Fabric 1.0 via Fal API (720p)

## Usage

```bash
python3 {baseDir}/scripts/generate.py \
  --script "Your script text here" \
  --voice <elevenlabs_voice_id> \
  --avatar <image_url_or_path> \
  --output ~/Desktop/video.mp4
```

## Avatar Requirements
- Clear, front-facing headshot
- Good lighting, neutral expression
- JPG or PNG, at least 512x512

## Voice Options

Find voice IDs at https://elevenlabs.io/app/voice-library or use:
```bash
curl -s "https://api.elevenlabs.io/v1/voices" \
  -H "xi-api-key: $(cat ~/.config/elevenlabs/api_key)" | python3 -m json.tool
```

## API Keys

- **ElevenLabs**: `~/.config/elevenlabs/api_key`
- **Fal**: `~/.config/fal/api_key` (env var `FAL_KEY`)

## Costs
- ElevenLabs TTS: ~$0.15-0.30 per minute of audio
- Fal Fabric 1.0: ~$0.10-0.20 per video generation
- Total: ~$0.30-0.50 per short video (~30s-1min)

## Tips
- Keep scripts under 60 seconds for best quality
- Use a consistent avatar image for brand recognition
- Test with a short phrase before generating full videos
