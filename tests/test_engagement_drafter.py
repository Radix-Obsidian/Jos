"""Tests for engagement_drafter.py — founder-voice engagement drafts."""
from __future__ import annotations

import pytest

from engagement_drafter import (
    draft_x_reply,
    draft_x_quote,
    draft_thought_leadership_tweet,
    draft_linkedin_comment,
    draft_linkedin_post,
)


SAMPLE_LEAD = {
    "name": "Jane Smith",
    "email": "jane@voiceco.com",
    "company": "VoiceCo",
    "x_username": "janesmith",
}


# ---------- draft_x_reply ----------

def test_x_reply_voice_keyword():
    result = draft_x_reply(SAMPLE_LEAD, "Voice features are the future of AI", "123")
    assert result["action_type"] == "x_reply"
    assert result["platform"] == "x"
    assert "Jane" in result["outreach_draft"]
    assert "voice" in result["outreach_draft"].lower() or "60%" in result["outreach_draft"]
    assert result["target_post_id"] == "123"


def test_x_reply_ai_agent_keyword():
    result = draft_x_reply(SAMPLE_LEAD, "Building an AI agent for customer support", "456")
    assert "agent" in result["outreach_draft"].lower() or "voice" in result["outreach_draft"].lower()


def test_x_reply_startup_keyword():
    result = draft_x_reply(SAMPLE_LEAD, "Startup life — shipping every day", "789")
    assert "hustle" in result["outreach_draft"].lower() or "bottleneck" in result["outreach_draft"].lower()


def test_x_reply_generic():
    result = draft_x_reply(SAMPLE_LEAD, "Interesting trends in tech this quarter", "101")
    assert "take" in result["outreach_draft"].lower() or "approaching" in result["outreach_draft"].lower()


def test_x_reply_no_name():
    lead = {"name": "", "email": "", "company": ""}
    result = draft_x_reply(lead, "Voice AI is growing", "111")
    assert result["action_type"] == "x_reply"
    # No name — should still produce text without error
    assert len(result["outreach_draft"]) > 10


def test_x_reply_has_correct_fields():
    result = draft_x_reply(SAMPLE_LEAD, "Voice tech rocks", "222")
    assert result["channel"] == "x"
    assert result["source"] == "engagement"
    assert result["target_post_url"] == "https://x.com/i/status/222"
    assert result["lead_name"] == "Jane Smith"
    assert result["lead_email"] == "jane@voiceco.com"


# ---------- draft_x_quote ----------

def test_x_quote_voice_keyword():
    result = draft_x_quote(SAMPLE_LEAD, "Speech recognition is evolving fast", "333")
    assert result["action_type"] == "x_quote"
    assert "Voco V2" in result["outreach_draft"]


def test_x_quote_generic():
    result = draft_x_quote(SAMPLE_LEAD, "Hot take on enterprise SaaS", "444")
    assert result["action_type"] == "x_quote"
    assert "Worth reading" in result["outreach_draft"]


def test_x_quote_includes_username():
    result = draft_x_quote(SAMPLE_LEAD, "General thoughts on tech", "555")
    assert "@janesmith" in result["outreach_draft"]


# ---------- draft_thought_leadership_tweet ----------

def test_thought_tweet_voice():
    result = draft_thought_leadership_tweet("voice AI")
    assert result["action_type"] == "x_tweet"
    assert result["platform"] == "x"
    assert "2027" in result["outreach_draft"] or "voice" in result["outreach_draft"].lower()


def test_thought_tweet_ai_agent():
    result = draft_thought_leadership_tweet("ai agent")
    assert "agent" in result["outreach_draft"].lower()


def test_thought_tweet_generic():
    result = draft_thought_leadership_tweet("developer tools")
    assert "CTO" in result["outreach_draft"] or "Voco" in result["outreach_draft"]


def test_thought_tweet_no_lead_info():
    result = draft_thought_leadership_tweet("anything")
    assert result["lead_name"] == ""
    assert result["lead_email"] == ""
    assert result["target_post_id"] == ""


# ---------- draft_linkedin_comment ----------

def test_li_comment_voice_keyword():
    result = draft_linkedin_comment(SAMPLE_LEAD, "Audio processing is key", "urn:li:post:1")
    assert result["action_type"] == "li_comment"
    assert result["platform"] == "linkedin"
    assert "Jane" in result["outreach_draft"]


def test_li_comment_hiring_keyword():
    result = draft_linkedin_comment(SAMPLE_LEAD, "We're hiring senior engineers", "urn:li:post:2")
    assert "team" in result["outreach_draft"].lower() or "engineering" in result["outreach_draft"].lower()


def test_li_comment_generic():
    result = draft_linkedin_comment(SAMPLE_LEAD, "Thoughts on Q4 planning", "urn:li:post:3")
    assert "thoughtful" in result["outreach_draft"].lower() or "CTO" in result["outreach_draft"]


def test_li_comment_truncates_post_text():
    long_text = "x" * 1000
    result = draft_linkedin_comment(SAMPLE_LEAD, long_text, "urn:li:post:4")
    assert len(result["target_post_text"]) <= 500


# ---------- draft_linkedin_post ----------

def test_li_post_voice():
    result = draft_linkedin_post("voice AI")
    assert result["action_type"] == "li_post"
    assert result["platform"] == "linkedin"
    assert "Voco V2" in result["outreach_draft"]


def test_li_post_generic():
    result = draft_linkedin_post("developer tools")
    assert "CTO" in result["outreach_draft"]
    assert result["action_type"] == "li_post"


def test_li_post_no_lead_info():
    result = draft_linkedin_post("anything")
    assert result["lead_name"] == ""
    assert result["target_post_id"] == ""
