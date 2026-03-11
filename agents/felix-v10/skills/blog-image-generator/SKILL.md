---
name: blog-image-generator
description: Generate blog post hero images using Google Gemini's image generation model.
---

# Blog Image Generator

Generate high-quality hero images for blog posts using Gemini's native image generation.

## Prerequisites
- Google Gemini API key: set `GEMINI_API_KEY` env var or store at `~/.config/gemini/api_key`

## Quick Start

```bash
GEMINI_API_KEY=$(cat ~/.config/gemini/api_key 2>/dev/null || echo "$GEMINI_API_KEY")

curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [{"text": "Generate a blog hero image: bright, modern, clean composition showing [YOUR SUBJECT]. No text in the image. Photorealistic editorial style, warm natural lighting."}]
    }],
    "generationConfig": {
      "responseModalities": ["TEXT", "IMAGE"]
    }
  }' | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
for part in data['candidates'][0]['content']['parts']:
    if 'inlineData' in part:
        img = base64.b64decode(part['inlineData']['data'])
        with open('hero-image.png', 'wb') as f:
            f.write(img)
        print(f'Saved hero-image.png ({len(img)} bytes)')
"
```

## Style Guidelines

**Good prompts:**
- "Bright, clean workspace with laptop showing analytics dashboard, warm natural lighting, editorial photography"
- "Overhead flat-lay of coffee, notebook, and pen on marble surface, soft morning light"
- "Abstract geometric pattern in teal and warm earth tones, modern minimalist design"

**Avoid:**
- Baked-in text/words (Gemini renders text poorly)
- Dark, moody aesthetics (unless that's your brand)
- Generic stock photo compositions

## Tips
- Always specify "no text in the image" — AI models love adding random words
- Include lighting direction ("warm natural lighting", "soft diffused light")
- Reference a photographic style ("editorial", "lifestyle", "product photography")
- Aspect ratio defaults to square — crop after generation for blog headers (16:9)
