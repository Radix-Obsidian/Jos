"""Local LLM engine — MLX inference on Apple Silicon with graceful fallback.

Primary: mlx-lm local inference (Llama-3.2-3B-Instruct-4bit, ~1.5GB)
Fallback: Returns provided fallback text if model unavailable.

Usage:
    from llm import generate_with_fallback
    text = generate_with_fallback(prompt, system_prompt, fallback_text="Hi {name}...")
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger("joy.llm")

# ---------------------------------------------------------------------------
# Config (read from env, safe defaults)
# ---------------------------------------------------------------------------
LLM_MODEL: str = os.getenv(
    "LLM_MODEL", "mlx-community/Llama-3.2-3B-Instruct-4bit"
)
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "350"))

# ---------------------------------------------------------------------------
# Lazy-loaded model + tokenizer (module-level singletons)
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None
_load_failed: bool = False  # sticky flag – don't retry after first failure


def _load_model():
    """Load MLX model + tokenizer on first call. Caches globally."""
    global _model, _tokenizer, _load_failed
    if _model is not None:
        return _model, _tokenizer
    if _load_failed:
        return None, None

    try:
        from mlx_lm import load  # type: ignore[import-untyped]

        logger.info("Loading LLM model %s …", LLM_MODEL)
        _model, _tokenizer = load(LLM_MODEL)
        logger.info("Model loaded successfully.")
        return _model, _tokenizer
    except Exception as exc:
        _load_failed = True
        logger.warning("MLX model load failed (%s). Using template fallback.", exc)
        return None, None


def reset_model():
    """Reset cached model (for testing)."""
    global _model, _tokenizer, _load_failed
    _model = None
    _tokenizer = None
    _load_failed = False


# ---------------------------------------------------------------------------
# Groq fallback (fast cloud LLM — used when MLX is unavailable e.g. Windows)
# ---------------------------------------------------------------------------

def _try_groq(prompt: str, system: str, max_tokens: int) -> Optional[str]:
    """Call Groq llama-3.3-70b-versatile. Returns None on any failure."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        import requests  # already in requirements
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return _post_process(text) or None
        logger.warning("Groq API returned %s", resp.status_code)
    except Exception as exc:
        logger.warning("Groq call failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate(
    prompt: str,
    system_prompt: str = "You are Joy, a friendly sales rep for Voco V2.",
    max_tokens: int | None = None,
) -> Optional[str]:
    """Generate text with local MLX model.

    Returns None if model is unavailable.
    """
    model, tokenizer = _load_model()
    if model is None:
        return None

    from mlx_lm import generate as mlx_generate  # type: ignore[import-untyped]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    try:
        chat_prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        # Fallback: manual prompt construction
        chat_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n"

    tokens = max_tokens or LLM_MAX_TOKENS
    try:
        output = mlx_generate(
            model, tokenizer, prompt=chat_prompt, max_tokens=tokens
        )
        return _post_process(output)
    except Exception as exc:
        logger.warning("MLX generation failed: %s", exc)
        return None


def generate_with_fallback(
    prompt: str,
    system_prompt: str,
    fallback_text: str,
    max_tokens: int | None = None,
) -> str:
    """Generate text, falling back to *fallback_text* if LLM unavailable.

    This is the primary entry point for all agents. The fallback_text is
    the existing f-string template so the system **never** breaks.
    """
    result = generate(prompt, system_prompt, max_tokens)
    if result and len(result.strip()) > 20:
        return result
    # MLX unavailable (e.g. Windows) — try Groq before falling back to template
    groq_result = _try_groq(prompt, system_prompt, max_tokens or LLM_MAX_TOKENS)
    if groq_result and len(groq_result.strip()) > 20:
        return groq_result
    return fallback_text


# ---------------------------------------------------------------------------
# Post-processing & safety
# ---------------------------------------------------------------------------

# Competitors — any mention disqualifies the LLM output
_COMPETITOR_NAMES = {"elevenlabs", "eleven labs", "deepgram", "assemblyai", "whisper ai"}


def _post_process(text: str) -> str:
    """Clean up LLM output: strip, remove common artifacts, validate."""
    if not text:
        return ""

    # Strip whitespace + common LLM prefixes
    text = text.strip()
    for prefix in ("Sure!", "Here's", "Certainly!", "Of course!", "Here is"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip(" :-–—\n")

    # Remove markdown formatting artifacts
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold** → bold
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)  # # headers

    # Competitor mention check
    text_lower = text.lower()
    for comp in _COMPETITOR_NAMES:
        if comp in text_lower:
            logger.warning("LLM output mentions competitor '%s' — rejecting.", comp)
            return ""

    # Truncate if absurdly long (>2000 chars)
    if len(text) > 2000:
        text = text[:2000].rsplit(" ", 1)[0] + "…"

    return text


# ---------------------------------------------------------------------------
# Prompt builders — reusable across agents
# ---------------------------------------------------------------------------

SYSTEM_OUTREACH = (
    "You are Joy, a warm and professional sales rep for Voco V2 — "
    "an AI-powered voice platform for engineering teams. "
    "Write concise, personalized outreach that sounds human. "
    "Never use filler words or buzzwords. Be specific about the lead's work. "
    "Keep emails under 120 words. Keep LinkedIn DMs under 80 words. "
    "Always sign off as 'Joy, Voco V2 Team'. "
    "NEVER mention competitors by name."
)

SYSTEM_ENGAGEMENT = (
    "You are a founder sharing genuine insights about voice AI and developer tools. "
    "Write short, value-adding comments (1-3 sentences) that sound natural on social media. "
    "Never pitch a product directly. Add perspective, not praise. "
    "NEVER use hashtags. NEVER mention competitors by name."
)

SYSTEM_CLOSER = (
    "You are Joy, closing a warm sales conversation for Voco V2. "
    "The lead has shown strong interest. Write a personal, direct closing message "
    "that references their specific situation. Keep it under 100 words. "
    "Include a clear call-to-action. Sign off as 'Joy, Voco V2 Team'. "
    "NEVER mention competitors by name."
)

SYSTEM_FOLLOW_UP = (
    "You are Joy, following up on a previous outreach for Voco V2. "
    "Be warm but brief. Reference the previous message naturally. "
    "Each follow-up should feel different, not copy-paste. "
    "Keep it under 80 words. Sign off as 'Joy, Voco V2 Team'. "
    "NEVER mention competitors by name."
)

SYSTEM_AUDITOR = (
    "You are a sales analytics expert. Analyze the provided KPI data and "
    "generate 2-3 actionable insights. Be specific with numbers. "
    "Focus on what to change, not what happened. Keep each insight to one sentence."
)


def build_outreach_prompt(lead: dict, tier: str, channel: str) -> str:
    """Build a prompt for personalized outreach generation."""
    name = lead.get("name", "")
    title = lead.get("title", "")
    company = lead.get("company", "")
    industry = lead.get("industry", "")
    x_post = lead.get("x_post_text", "")
    funding = lead.get("funding_stage", "")
    size = lead.get("company_size", 0)

    parts = [
        f"Write a personalized cold {channel} to this lead:",
        f"- Name: {name}",
        f"- Title: {title}" if title else "",
        f"- Company: {company}" if company else "",
        f"- Industry: {industry}" if industry else "",
        f"- Company size: ~{size} employees" if size else "",
        f"- Funding: {funding}" if funding else "",
        f"- Their recent X post: \"{x_post}\"" if x_post else "",
        "",
        f"Tier: {tier} ({'high-value enterprise' if tier == 'enterprise' else 'self-serve / smaller team'})",
        "",
        "Product: Voco V2 — AI-powered voice platform. Teams ship voice features in days not months.",
        "Pricing: $49/mo self-serve, custom for enterprise.",
        "",
    ]

    if channel == "email":
        parts.append("Format: Return ONLY Subject: <subject>\\n\\n<body>")
        parts.append("Keep the email under 120 words.")
    else:
        parts.append("Format: Return ONLY the LinkedIn message body.")
        parts.append("Keep it under 80 words. No subject line needed.")

    return "\n".join(p for p in parts if p is not None)


def build_engagement_prompt(
    action_type: str,
    post_text: str = "",
    lead_name: str = "",
    topic: str = "",
) -> str:
    """Build a prompt for social engagement drafts."""
    if action_type == "x_reply":
        return (
            f"Write a short reply to this X/Twitter post:\n"
            f"\"{post_text}\"\n\n"
            f"{'Address ' + lead_name.split()[0] + ' by first name. ' if lead_name else ''}"
            f"Add a genuine insight, not generic praise. 1-2 sentences max."
        )
    elif action_type == "x_quote":
        return (
            f"Write a quote tweet adding your founder perspective to this post:\n"
            f"\"{post_text}\"\n\n"
            f"Share an original take. 1-2 sentences. Don't just agree."
        )
    elif action_type == "x_tweet":
        return (
            f"Write an original thought leadership tweet about: {topic or 'voice AI'}\n\n"
            f"Share a specific insight or contrarian take. No hashtags. Under 280 chars."
        )
    elif action_type == "li_comment":
        return (
            f"Write a LinkedIn comment on this post:\n"
            f"\"{post_text}\"\n\n"
            f"{'Address ' + lead_name.split()[0] + ' by first name. ' if lead_name else ''}"
            f"Add substantive value. 1-3 sentences."
        )
    elif action_type == "li_post":
        return (
            f"Write a LinkedIn post about: {topic or 'voice AI trends'}\n\n"
            f"Use a hook line, then 3-4 short paragraphs. End with a question. "
            f"Professional but conversational tone. Under 200 words."
        )
    return f"Write a short social media comment about: {topic or post_text}"


def build_closing_prompt(lead: dict, tier: str, action: str) -> str:
    """Build a prompt for closing script generation."""
    name = lead.get("name", "")
    company = lead.get("company", "")
    title = lead.get("title", "")
    x_post = lead.get("x_post_text", "")

    parts = [
        f"Write a closing message for this hot lead:",
        f"- Name: {name}, {title} at {company}",
        f"- Their recent post: \"{x_post}\"" if x_post else "",
        "",
    ]

    if action == "book_demo":
        parts.append("Goal: Get them to book a 15-min demo.")
        parts.append("Demo link: https://calendly.com/voco-demo")
        parts.append("Keep it warm and direct. Under 100 words.")
    elif action == "payment_link":
        parts.append("Goal: Get them to start with Voco V2 self-serve ($49/mo).")
        parts.append("Payment link: https://buy.stripe.com/voco-v2")
        parts.append("Keep it casual and brief. Under 80 words.")

    return "\n".join(p for p in parts if p)


def build_follow_up_prompt(lead: dict, step: int, tier: str) -> str:
    """Build a prompt for follow-up message generation."""
    name = lead.get("name", "")
    company = lead.get("company", "")

    base = (
        f"Write follow-up #{step} to {name} at {company}.\n"
        f"Tier: {tier}. Product: Voco V2 (AI voice platform, $49/mo self-serve).\n"
    )

    if step == 1:
        base += "This is the first follow-up after initial outreach. Be gentle and curious."
    elif step == 2:
        base += "Second follow-up. Share a brief social proof or specific benefit."
    else:
        base += "Final follow-up. Graceful close — leave the door open, no pressure."

    base += "\nFormat: Subject: <subject>\\n\\n<body>\nKeep it under 80 words."
    return base


def build_audit_prompt(kpi_data: dict, suggestions_so_far: list[str]) -> str:
    """Build a prompt for auditor analysis."""
    return (
        f"Analyze these sales pipeline KPIs and provide 2-3 actionable insights:\n\n"
        f"Total processed: {kpi_data.get('total_processed', 0)}\n"
        f"Hot leads: {kpi_data.get('hot_leads', 0)}\n"
        f"Cold leads: {kpi_data.get('cold_leads', 0)}\n"
        f"Responded: {kpi_data.get('responded', 0)}\n"
        f"Delivery rate: {kpi_data.get('delivery_rate', 0):.1%}\n"
        f"Close rate: {kpi_data.get('close_rate', 0):.1%}\n\n"
        f"Rule-based observations: {'; '.join(suggestions_so_far) if suggestions_so_far else 'None'}\n\n"
        f"Return ONLY the insights, one per line. Be specific."
    )


def parse_email_output(text: str) -> dict:
    """Parse LLM output that should contain Subject: ... and body."""
    lines = text.strip().split("\n", 1)

    subject = ""
    body = text.strip()

    for i, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            body = "\n".join(lines[i + 1:]).strip() if i + 1 < len(lines) else ""
            break

    # Clean up body — remove leading blank lines
    body = body.lstrip("\n")

    return {"subject": subject, "body": body}
