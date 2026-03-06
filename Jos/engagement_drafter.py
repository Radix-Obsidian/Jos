"""Generate founder-voice engagement drafts for X and LinkedIn.

Uses local LLM (MLX) for contextual generation with keyword-match fallback.
Drafts are value-adding comments, not sales pitches. They go through
the approval queue before posting via x_poster.py or linkedin_poster.py.
"""
from __future__ import annotations

import logging

from config import PRODUCT
from llm import generate_with_fallback, build_engagement_prompt, SYSTEM_ENGAGEMENT

import ledger

logger = logging.getLogger("joy.engagement")


def draft_x_reply(lead: dict, post_text: str, post_id: str) -> dict:
    """Generate a value-add reply to an ICP's X post.

    Returns dict ready for queue_engagement() with action_type='x_reply'.
    """
    name = lead.get("name", "").split()[0] if lead.get("name") else ""
    company = lead.get("company", "")

    # Template fallback (keyword-based)
    post_lower = post_text.lower()
    if any(kw in post_lower for kw in ["voice", "speech", "audio", "tts"]):
        fallback = (
            f"Great point{' ' + name if name else ''}. We've seen teams cut voice feature "
            f"dev time by 60% with the right platform. The bottleneck is usually "
            f"infra, not models."
        )
    elif any(kw in post_lower for kw in ["ai agent", "llm", "chatbot", "assistant"]):
        fallback = (
            f"Agree{' ' + name if name else ''} — voice is the next interface for AI agents. "
            f"Text-based agents are table stakes now. The winners will be voice-first."
        )
    elif any(kw in post_lower for kw in ["startup", "founder", "building", "shipping"]):
        fallback = (
            f"Love the hustle{' ' + name if name else ''}. What's your biggest "
            f"bottleneck right now? Always curious what founders are battling."
        )
    else:
        fallback = (
            f"Interesting take{' ' + name if name else ''}. Been thinking about "
            f"this a lot. Would love to hear more about how "
            f"{company + ' is' if company else 'you are'} approaching it."
        )

    # LLM generation
    prompt = build_engagement_prompt("x_reply", post_text=post_text, lead_name=lead.get("name", ""))
    reply = generate_with_fallback(prompt, SYSTEM_ENGAGEMENT, fallback, max_tokens=100)

    ledger.log(f"Drafted X reply for {lead.get('name', 'unknown')} on post {post_id}")

    return {
        "lead_name": lead.get("name", ""),
        "lead_email": lead.get("email", ""),
        "outreach_draft": reply,
        "action_type": "x_reply",
        "target_post_id": post_id,
        "target_post_url": f"https://x.com/i/status/{post_id}",
        "target_post_text": post_text[:500],
        "platform": "x",
        "source": "engagement",
        "channel": "x",
    }


def draft_x_quote(lead: dict, post_text: str, post_id: str) -> dict:
    """Generate a quote tweet adding founder perspective.

    Returns dict ready for queue_engagement() with action_type='x_quote'.
    """
    name = lead.get("name", "").split()[0] if lead.get("name") else ""

    # Template fallback
    post_lower = post_text.lower()
    if any(kw in post_lower for kw in ["voice", "speech", "audio"]):
        fallback = (
            f"This is exactly why we built {PRODUCT['name']}. Voice features "
            f"shouldn't take months to ship. The platform layer is what's missing "
            f"for most teams."
        )
    else:
        fallback = (
            f"Worth reading. The best founders I talk to are thinking about this. "
            f"{'@' + lead.get('x_username', '') + ' ' if lead.get('x_username') else ''}"
            f"nails it here."
        )

    # LLM generation
    prompt = build_engagement_prompt("x_quote", post_text=post_text)
    quote = generate_with_fallback(prompt, SYSTEM_ENGAGEMENT, fallback, max_tokens=100)

    ledger.log(f"Drafted X quote for post {post_id}")

    return {
        "lead_name": lead.get("name", ""),
        "lead_email": lead.get("email", ""),
        "outreach_draft": quote,
        "action_type": "x_quote",
        "target_post_id": post_id,
        "target_post_url": f"https://x.com/i/status/{post_id}",
        "target_post_text": post_text[:500],
        "platform": "x",
        "source": "engagement",
        "channel": "x",
    }


def draft_thought_leadership_tweet(topic: str) -> dict:
    """Generate an original thought leadership tweet.

    Returns dict ready for queue_engagement() with action_type='x_tweet'.
    """
    # Template fallback
    topic_lower = topic.lower()
    if "voice" in topic_lower:
        fallback = (
            f"Hot take: every SaaS product will have a voice interface by 2027. "
            f"The companies building voice features NOW will own the next wave. "
            f"The barrier isn't AI — it's the platform layer."
        )
    elif "ai agent" in topic_lower:
        fallback = (
            f"AI agents that can only type are like smartphones that can only text. "
            f"Voice is the natural interface. We're building the bridge."
        )
    else:
        fallback = (
            f"Talking to 50+ CTOs this month. The #1 request: a voice platform "
            f"that doesn't require 6 months of infra work. That's exactly what "
            f"we're solving at {PRODUCT['name']}."
        )

    # LLM generation
    prompt = build_engagement_prompt("x_tweet", topic=topic)
    tweet = generate_with_fallback(prompt, SYSTEM_ENGAGEMENT, fallback, max_tokens=100)

    # Enforce 280 char limit
    if len(tweet) > 280:
        tweet = tweet[:277] + "…"

    ledger.log(f"Drafted thought leadership tweet on '{topic}'")

    return {
        "lead_name": "",
        "lead_email": "",
        "outreach_draft": tweet,
        "action_type": "x_tweet",
        "target_post_id": "",
        "target_post_url": "",
        "target_post_text": "",
        "platform": "x",
        "source": "engagement",
        "channel": "x",
    }


def draft_linkedin_comment(lead: dict, post_text: str, post_urn: str) -> dict:
    """Generate a LinkedIn comment on an ICP's post.

    Returns dict ready for queue_engagement() with action_type='li_comment'.
    """
    name = lead.get("name", "").split()[0] if lead.get("name") else ""

    # Template fallback
    post_lower = post_text.lower()
    if any(kw in post_lower for kw in ["voice", "speech", "audio"]):
        fallback = (
            f"Great insight{' ' + name if name else ''}. We're seeing the same trend — "
            f"voice is becoming table stakes for product teams. The infrastructure "
            f"gap is real and closing fast."
        )
    elif any(kw in post_lower for kw in ["hiring", "team", "engineering"]):
        fallback = (
            f"Love seeing teams invest in this area. The best engineering orgs "
            f"I talk to are all prioritizing voice/audio capabilities right now."
        )
    else:
        fallback = (
            f"Really thoughtful post{' ' + name if name else ''}. This resonates with "
            f"conversations I'm having with CTOs across the industry."
        )

    # LLM generation
    prompt = build_engagement_prompt("li_comment", post_text=post_text, lead_name=lead.get("name", ""))
    comment = generate_with_fallback(prompt, SYSTEM_ENGAGEMENT, fallback, max_tokens=150)

    ledger.log(f"Drafted LinkedIn comment for {lead.get('name', 'unknown')}")

    return {
        "lead_name": lead.get("name", ""),
        "lead_email": lead.get("email", ""),
        "outreach_draft": comment,
        "action_type": "li_comment",
        "target_post_id": post_urn,
        "target_post_url": "",
        "target_post_text": post_text[:500],
        "platform": "linkedin",
        "source": "engagement",
        "channel": "linkedin",
    }


def draft_linkedin_post(topic: str) -> dict:
    """Generate a LinkedIn post for founder-led content.

    Returns dict ready for queue_engagement() with action_type='li_post'.
    """
    # Template fallback
    topic_lower = topic.lower()
    if "voice" in topic_lower:
        fallback = (
            f"Voice AI is having its 'mobile moment.'\n\n"
            f"In 2008, every company needed an app. By 2027, every product will "
            f"need a voice interface.\n\n"
            f"The teams building voice features today will own the next wave.\n\n"
            f"At {PRODUCT['name']}, we're making it possible to ship voice features "
            f"in days, not months.\n\n"
            f"What's your take — is voice the next big platform shift?"
        )
    else:
        fallback = (
            f"Talked to 50+ CTOs this month about their biggest engineering "
            f"bottleneck.\n\n"
            f"The answer surprised me: it's not AI models. It's the infrastructure "
            f"layer between models and production.\n\n"
            f"That's the gap we're closing at {PRODUCT['name']}.\n\n"
            f"If you're building voice features, I'd love to hear what's "
            f"blocking you."
        )

    # LLM generation
    prompt = build_engagement_prompt("li_post", topic=topic)
    post = generate_with_fallback(prompt, SYSTEM_ENGAGEMENT, fallback, max_tokens=250)

    ledger.log(f"Drafted LinkedIn post on '{topic}'")

    return {
        "lead_name": "",
        "lead_email": "",
        "outreach_draft": post,
        "action_type": "li_post",
        "target_post_id": "",
        "target_post_url": "",
        "target_post_text": "",
        "platform": "linkedin",
        "source": "engagement",
        "channel": "linkedin",
    }
