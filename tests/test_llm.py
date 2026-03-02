"""Tests for llm.py — LLM engine with MLX inference and graceful fallback."""
from __future__ import annotations

import sys
import pytest
from unittest.mock import patch, MagicMock, call

import llm
from llm import (
    _load_model,
    reset_model,
    generate,
    generate_with_fallback,
    _post_process,
    parse_email_output,
    build_outreach_prompt,
    build_engagement_prompt,
    build_closing_prompt,
    build_follow_up_prompt,
    build_audit_prompt,
    _COMPETITOR_NAMES,
)


@pytest.fixture(autouse=True)
def mock_llm_loading():
    """Override conftest's mock_llm_loading — test_llm.py controls model loading itself."""
    yield


@pytest.fixture(autouse=True)
def clean_model_state():
    """Reset model state before and after every test."""
    reset_model()
    yield
    reset_model()


# ===================================================================
# _load_model
# ===================================================================


class TestLoadModel:
    """Tests for _load_model lazy loading behaviour."""

    def test_load_model_success_via_mock_import(self):
        """When mlx_lm.load works, model and tokenizer are cached."""
        fake_model = MagicMock(name="model")
        fake_tok = MagicMock(name="tokenizer")
        mock_mlx = MagicMock()
        mock_mlx.load.return_value = (fake_model, fake_tok)

        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            model, tokenizer = _load_model()

        assert model is fake_model
        assert tokenizer is fake_tok
        assert llm._model is fake_model
        assert llm._tokenizer is fake_tok

    def test_load_model_caches_on_success(self):
        """Once loaded, subsequent calls return cached model."""
        fake_model = MagicMock(name="model")
        fake_tok = MagicMock(name="tokenizer")
        llm._model = fake_model
        llm._tokenizer = fake_tok
        model, tokenizer = _load_model()
        assert model is fake_model
        assert tokenizer is fake_tok

    def test_load_model_returns_none_when_load_failed_flag_set(self):
        """If _load_failed is True, don't retry."""
        llm._load_failed = True
        model, tokenizer = _load_model()
        assert model is None
        assert tokenizer is None

    def test_load_model_sets_load_failed_on_import_error(self):
        """When mlx_lm is not installed, _load_failed goes True."""
        reset_model()
        with patch("builtins.__import__", side_effect=ImportError("no mlx_lm")):
            model, tokenizer = _load_model()
        assert model is None
        assert tokenizer is None
        assert llm._load_failed is True

    def test_load_model_sets_load_failed_on_load_exception(self):
        """When mlx_lm.load raises, _load_failed goes True."""
        mock_mlx = MagicMock()
        mock_mlx.load.side_effect = RuntimeError("model not found")

        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            model, tokenizer = _load_model()

        assert model is None
        assert tokenizer is None
        assert llm._load_failed is True


# ===================================================================
# reset_model
# ===================================================================


class TestResetModel:
    """Tests for reset_model clearing cached state."""

    def test_reset_clears_model_and_tokenizer(self):
        llm._model = MagicMock()
        llm._tokenizer = MagicMock()
        llm._load_failed = True
        reset_model()
        assert llm._model is None
        assert llm._tokenizer is None
        assert llm._load_failed is False

    def test_reset_is_idempotent(self):
        reset_model()
        reset_model()
        assert llm._model is None
        assert llm._tokenizer is None
        assert llm._load_failed is False


# ===================================================================
# generate
# ===================================================================


def _setup_generate_mocks(
    *,
    chat_template_result: str = "<prompt>",
    chat_template_error: bool = False,
    mlx_generate_result: str = "A valid response with enough characters.",
    mlx_generate_error: Exception | None = None,
):
    """Helper: set up llm._model, llm._tokenizer and a mock mlx_lm module.

    Returns the mock module so callers can inspect calls.
    """
    fake_model = MagicMock(name="model")
    fake_tokenizer = MagicMock(name="tokenizer")

    if chat_template_error:
        fake_tokenizer.apply_chat_template.side_effect = Exception("template error")
    else:
        fake_tokenizer.apply_chat_template.return_value = chat_template_result

    llm._model = fake_model
    llm._tokenizer = fake_tokenizer

    mock_mlx_mod = MagicMock()
    if mlx_generate_error:
        mock_mlx_mod.generate.side_effect = mlx_generate_error
    else:
        mock_mlx_mod.generate.return_value = mlx_generate_result

    return mock_mlx_mod, fake_model, fake_tokenizer


class TestGenerate:
    """Tests for the generate() function."""

    def test_generate_returns_none_when_model_unavailable(self):
        llm._load_failed = True
        result = generate("Hello")
        assert result is None

    def test_generate_returns_none_when_no_model_loaded(self):
        """When _load_model returns (None, None), generate returns None."""
        with patch("llm._load_model", return_value=(None, None)):
            result = generate("Hello")
        assert result is None

    def test_generate_calls_mlx_generate_and_returns_post_processed(self):
        mock_mlx, fake_model, fake_tok = _setup_generate_mocks(
            mlx_generate_result="Hello, this is a great output from the LLM model."
        )
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            result = generate("Tell me about voice AI")

        assert mock_mlx.generate.called
        assert result == "Hello, this is a great output from the LLM model."

    def test_generate_handles_chat_template_failure(self):
        """When apply_chat_template raises, falls back to manual prompt."""
        mock_mlx, fake_model, fake_tok = _setup_generate_mocks(
            chat_template_error=True,
            mlx_generate_result="Fallback prompt was used successfully here.",
        )
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            result = generate("Test prompt")

        assert mock_mlx.generate.called
        # Verify the manual prompt was used (contains <|system|> marker)
        prompt_arg = mock_mlx.generate.call_args
        assert "<|system|>" in str(prompt_arg)

    def test_generate_handles_mlx_generate_exception(self):
        """When mlx_generate raises, generate returns None."""
        mock_mlx, _, _ = _setup_generate_mocks(
            mlx_generate_error=RuntimeError("GPU OOM"),
        )
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            result = generate("Test prompt")

        assert result is None

    def test_generate_uses_custom_max_tokens(self):
        """When max_tokens is passed, it should be forwarded."""
        mock_mlx, _, _ = _setup_generate_mocks(
            mlx_generate_result="Short valid output for the test here.",
        )
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            generate("prompt", max_tokens=500)

        call_kwargs = mock_mlx.generate.call_args
        assert call_kwargs.kwargs["max_tokens"] == 500

    def test_generate_uses_default_max_tokens(self):
        """When max_tokens is not passed, LLM_MAX_TOKENS is used."""
        mock_mlx, _, _ = _setup_generate_mocks()
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            generate("prompt")

        call_kwargs = mock_mlx.generate.call_args
        assert call_kwargs.kwargs["max_tokens"] == llm.LLM_MAX_TOKENS

    def test_generate_passes_custom_system_prompt(self):
        """Custom system_prompt should appear in the chat template call."""
        mock_mlx, _, fake_tok = _setup_generate_mocks()
        custom_system = "You are a pirate sales rep."
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            generate("Ahoy", system_prompt=custom_system)

        template_call = fake_tok.apply_chat_template.call_args
        messages = template_call[0][0]
        assert messages[0]["content"] == custom_system

    def test_generate_post_processes_output(self):
        """Output goes through _post_process (e.g., strips bold)."""
        mock_mlx, _, _ = _setup_generate_mocks(
            mlx_generate_result="Sure! **Bold** text that is long enough to count.",
        )
        with patch.dict(sys.modules, {"mlx_lm": mock_mlx}):
            result = generate("prompt")

        assert "Sure!" not in result
        assert "**" not in result
        assert "Bold" in result


# ===================================================================
# generate_with_fallback
# ===================================================================


class TestGenerateWithFallback:
    """Tests for generate_with_fallback."""

    def test_returns_llm_output_when_long_enough(self):
        long_text = "This is a great response that is definitely longer than twenty characters."
        with patch("llm.generate", return_value=long_text):
            result = generate_with_fallback("prompt", "system", "fallback text")
        assert result == long_text

    def test_returns_fallback_when_generate_returns_none(self):
        with patch("llm.generate", return_value=None):
            result = generate_with_fallback("prompt", "system", "my fallback text")
        assert result == "my fallback text"

    def test_returns_fallback_when_generate_returns_short_string(self):
        with patch("llm.generate", return_value="Too short"):
            result = generate_with_fallback("prompt", "system", "fallback here")
        assert result == "fallback here"

    def test_returns_fallback_when_generate_returns_empty_string(self):
        with patch("llm.generate", return_value=""):
            result = generate_with_fallback("prompt", "system", "fallback text")
        assert result == "fallback text"

    def test_returns_fallback_when_result_is_exactly_20_chars(self):
        """Boundary: 20-char string should trigger fallback (needs >20)."""
        text_20 = "a" * 20
        assert len(text_20) == 20
        with patch("llm.generate", return_value=text_20):
            result = generate_with_fallback("prompt", "system", "fallback")
        assert result == "fallback"

    def test_returns_llm_output_when_result_is_21_chars(self):
        """Boundary: 21-char string should be accepted."""
        text_21 = "a" * 21
        with patch("llm.generate", return_value=text_21):
            result = generate_with_fallback("prompt", "system", "fallback")
        assert result == text_21

    def test_forwards_max_tokens(self):
        with patch("llm.generate", return_value=None) as mock_gen:
            generate_with_fallback("p", "s", "fb", max_tokens=999)
        mock_gen.assert_called_once_with("p", "s", 999)

    def test_returns_fallback_when_result_is_whitespace_padded(self):
        """Whitespace-only result (stripped length 0) triggers fallback."""
        with patch("llm.generate", return_value="   \n  "):
            result = generate_with_fallback("p", "s", "fallback")
        assert result == "fallback"


# ===================================================================
# _post_process
# ===================================================================


class TestPostProcess:
    """Tests for _post_process text cleaning and safety."""

    # --- Empty / whitespace ---

    def test_empty_input_returns_empty(self):
        assert _post_process("") == ""

    def test_none_input_returns_empty(self):
        assert _post_process(None) == ""

    def test_whitespace_only_returns_empty(self):
        result = _post_process("   \n\t  ")
        assert result == ""

    # --- Prefix stripping ---

    def test_strips_sure_prefix(self):
        result = _post_process("Sure! Here is your outreach message for the lead today.")
        assert not result.startswith("Sure!")

    def test_strips_heres_prefix(self):
        result = _post_process("Here's a great message for you to send right away now.")
        assert not result.lower().startswith("here's")

    def test_strips_certainly_prefix(self):
        result = _post_process("Certainly! I'll write that for you right away and here it is.")
        assert not result.startswith("Certainly!")

    def test_strips_of_course_prefix(self):
        result = _post_process("Of course! Let me draft a perfect message for this lead.")
        assert not result.startswith("Of course!")

    def test_strips_here_is_prefix(self):
        result = _post_process("Here is the personalized outreach message for the lead.")
        assert not result.startswith("Here is")

    def test_strips_prefix_with_colon_separator(self):
        result = _post_process("Sure!: the output starts right after the colon separator.")
        assert "Sure!" not in result

    # --- Markdown removal ---

    def test_removes_bold_markdown(self):
        result = _post_process("This is **bold text** in the middle of a sentence that is long enough.")
        assert "**" not in result
        assert "bold text" in result

    def test_removes_header_markdown(self):
        result = _post_process("# Header Line\nBody text that follows the header line right here.")
        assert not result.startswith("#")
        assert "Header Line" in result

    def test_removes_multiple_bold_sections(self):
        result = _post_process("Hello **name**, your **company** is doing great things we should chat.")
        assert "**" not in result
        assert "name" in result
        assert "company" in result

    def test_removes_h2_header(self):
        result = _post_process("## Section Header\nContent below the section header text.")
        assert "##" not in result
        assert "Section Header" in result

    # --- Competitor rejection ---

    def test_rejects_elevenlabs(self):
        assert _post_process("Unlike ElevenLabs, we offer better pricing and features.") == ""

    def test_rejects_eleven_labs_with_space(self):
        assert _post_process("We are better than Eleven Labs in every way possible.") == ""

    def test_rejects_deepgram(self):
        assert _post_process("Compared to Deepgram, Voco is faster and more reliable.") == ""

    def test_rejects_assemblyai(self):
        assert _post_process("AssemblyAI can't match our latency or developer experience.") == ""

    def test_rejects_whisper_ai(self):
        assert _post_process("Whisper AI has limitations that Voco V2 does not have.") == ""

    def test_rejects_competitor_case_insensitive(self):
        assert _post_process("We outperform DEEPGRAM on every benchmark that matters.") == ""

    def test_all_competitors_covered(self):
        """Ensure we check every competitor in _COMPETITOR_NAMES."""
        expected = {"elevenlabs", "eleven labs", "deepgram", "assemblyai", "whisper ai"}
        assert _COMPETITOR_NAMES == expected

    def test_each_competitor_individually(self):
        """Every single entry in _COMPETITOR_NAMES must reject output."""
        for comp in _COMPETITOR_NAMES:
            text = f"Our product is way better than {comp} for this use case."
            assert _post_process(text) == "", f"Failed to reject competitor: {comp}"

    # --- Truncation ---

    def test_truncates_over_2000_chars(self):
        long_text = "word " * 500  # ~2500 chars
        result = _post_process(long_text)
        assert len(result) <= 2001  # 2000 + ellipsis char
        assert result.endswith("\u2026")

    def test_does_not_truncate_under_2000_chars(self):
        text = "A decent message. " * 50  # ~900 chars
        result = _post_process(text)
        assert "\u2026" not in result

    def test_truncation_breaks_at_word_boundary(self):
        """Truncated text should not cut a word in half."""
        long_text = "abcdefghij " * 250  # ~2750 chars
        result = _post_process(long_text)
        # Should end at a space boundary (no partial word before ellipsis)
        before_ellipsis = result[:-1]
        assert before_ellipsis.endswith("abcdefghij")

    # --- Clean text passthrough ---

    def test_clean_text_passes_through(self):
        text = "Hi Sarah, I noticed your work on voice APIs. Would love to chat about Voco V2."
        assert _post_process(text) == text

    def test_preserves_normal_formatting(self):
        text = "Line one.\nLine two.\nLine three is here for the test."
        result = _post_process(text)
        assert "Line one." in result
        assert "Line three" in result


# ===================================================================
# parse_email_output
# ===================================================================


class TestParseEmailOutput:
    """Tests for parse_email_output."""

    def test_valid_subject_and_body(self):
        text = "Subject: Quick question about voice\n\nHi Sarah, I saw your recent post..."
        result = parse_email_output(text)
        assert result["subject"] == "Quick question about voice"
        assert "Hi Sarah" in result["body"]

    def test_subject_with_colon_in_value(self):
        text = "Subject: Re: Voice AI discussion\n\nBody text here and more."
        result = parse_email_output(text)
        assert result["subject"] == "Re: Voice AI discussion"

    def test_no_subject_line(self):
        text = "Just a plain message without any subject line at all."
        result = parse_email_output(text)
        assert result["subject"] == ""
        assert result["body"] == text

    def test_empty_input(self):
        result = parse_email_output("")
        assert result["subject"] == ""
        assert result["body"] == ""

    def test_subject_only_no_body(self):
        text = "Subject: Just a subject"
        result = parse_email_output(text)
        assert result["subject"] == "Just a subject"
        assert result["body"] == ""

    def test_multiline_body(self):
        text = "Subject: Hello\n\nLine 1\nLine 2\nLine 3"
        result = parse_email_output(text)
        assert result["subject"] == "Hello"
        assert "Line 1" in result["body"]
        assert "Line 3" in result["body"]

    def test_case_insensitive_subject(self):
        text = "subject: lowercase subject\n\nBody content here."
        result = parse_email_output(text)
        assert result["subject"] == "lowercase subject"

    def test_body_strips_leading_blank_lines(self):
        text = "Subject: Test\n\n\n\nActual body starts here."
        result = parse_email_output(text)
        assert result["body"].startswith("Actual body")


# ===================================================================
# build_outreach_prompt
# ===================================================================


class TestBuildOutreachPrompt:
    """Tests for build_outreach_prompt."""

    def test_email_prompt_contains_lead_info(self):
        lead = {
            "name": "Sarah Chen",
            "title": "CTO",
            "company": "VoiceTech Inc",
            "industry": "AI/ML",
        }
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert "Sarah Chen" in result
        assert "CTO" in result
        assert "VoiceTech Inc" in result
        assert "AI/ML" in result
        assert "Subject:" in result
        assert "120 words" in result

    def test_linkedin_prompt_format(self):
        lead = {"name": "James Wu", "company": "StartupCo"}
        result = build_outreach_prompt(lead, "self_serve", "linkedin")
        assert "James Wu" in result
        assert "LinkedIn" in result
        assert "80 words" in result
        assert "Subject:" not in result

    def test_enterprise_tier_label(self):
        lead = {"name": "Test Lead"}
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert "high-value enterprise" in result

    def test_self_serve_tier_label(self):
        lead = {"name": "Test Lead"}
        result = build_outreach_prompt(lead, "self_serve", "email")
        assert "self-serve" in result

    def test_includes_x_post_when_present(self):
        lead = {"name": "Emily Park", "x_post_text": "Voice AI is the future!"}
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert "Voice AI is the future!" in result

    def test_returns_nonempty_string(self):
        lead = {"name": "Min Lead"}
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_product_info(self):
        lead = {"name": "Test"}
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert "Voco V2" in result
        assert "$49/mo" in result

    def test_includes_funding_and_size_when_present(self):
        lead = {
            "name": "David Kim",
            "company": "BigCorp",
            "funding_stage": "Series B",
            "company_size": 200,
        }
        result = build_outreach_prompt(lead, "enterprise", "email")
        assert "Series B" in result
        assert "200" in result


# ===================================================================
# build_engagement_prompt
# ===================================================================


class TestBuildEngagementPrompt:
    """Tests for build_engagement_prompt for different action types."""

    def test_x_reply(self):
        result = build_engagement_prompt("x_reply", post_text="Great talk on AI!", lead_name="Sarah Chen")
        assert "reply" in result.lower()
        assert "Great talk on AI!" in result
        assert "Sarah" in result

    def test_x_reply_without_lead_name(self):
        result = build_engagement_prompt("x_reply", post_text="Some post")
        assert "reply" in result.lower()
        assert "Some post" in result

    def test_x_quote(self):
        result = build_engagement_prompt("x_quote", post_text="Voice is the next UI")
        assert "quote" in result.lower()
        assert "Voice is the next UI" in result

    def test_x_tweet(self):
        result = build_engagement_prompt("x_tweet", topic="developer tools")
        assert "developer tools" in result

    def test_x_tweet_default_topic(self):
        result = build_engagement_prompt("x_tweet")
        assert "voice AI" in result

    def test_li_comment(self):
        result = build_engagement_prompt("li_comment", post_text="Hiring engineers", lead_name="David Kim")
        assert "LinkedIn" in result
        assert "David" in result

    def test_li_post(self):
        result = build_engagement_prompt("li_post", topic="voice trends")
        assert "LinkedIn" in result
        assert "voice trends" in result

    def test_li_post_default_topic(self):
        result = build_engagement_prompt("li_post")
        assert "voice AI trends" in result

    def test_unknown_action_type(self):
        result = build_engagement_prompt("unknown_type", topic="general")
        assert "general" in result
        assert isinstance(result, str)

    def test_returns_nonempty_for_all_types(self):
        for action in ("x_reply", "x_quote", "x_tweet", "li_comment", "li_post", "other"):
            result = build_engagement_prompt(action, post_text="test", topic="test")
            assert len(result) > 0, f"Empty prompt for action_type={action}"


# ===================================================================
# build_closing_prompt
# ===================================================================


class TestBuildClosingPrompt:
    """Tests for build_closing_prompt."""

    def test_book_demo_prompt(self):
        lead = {"name": "Sarah Chen", "company": "VoiceTech", "title": "CTO"}
        result = build_closing_prompt(lead, "enterprise", "book_demo")
        assert "Sarah Chen" in result
        assert "VoiceTech" in result
        assert "demo" in result.lower()
        assert "calendly" in result.lower()

    def test_payment_link_prompt(self):
        lead = {"name": "James Wu", "company": "SmallCo", "title": "Dev"}
        result = build_closing_prompt(lead, "self_serve", "payment_link")
        assert "James Wu" in result
        assert "$49/mo" in result
        assert "stripe" in result.lower()

    def test_includes_x_post(self):
        lead = {"name": "Emily Park", "company": "AI Corp", "title": "Eng", "x_post_text": "Love voice tech!"}
        result = build_closing_prompt(lead, "enterprise", "book_demo")
        assert "Love voice tech!" in result

    def test_returns_nonempty(self):
        lead = {"name": "Test", "company": "Co", "title": "Role"}
        result = build_closing_prompt(lead, "enterprise", "book_demo")
        assert len(result) > 0

    def test_minimal_lead_data(self):
        """Even with empty dict, prompt should not crash."""
        lead = {}
        result = build_closing_prompt(lead, "self_serve", "payment_link")
        assert isinstance(result, str)
        assert len(result) > 0


# ===================================================================
# build_follow_up_prompt
# ===================================================================


class TestBuildFollowUpPrompt:
    """Tests for build_follow_up_prompt."""

    def test_step_1_gentle(self):
        lead = {"name": "Sarah Chen", "company": "VoiceTech"}
        result = build_follow_up_prompt(lead, 1, "enterprise")
        assert "Sarah Chen" in result
        assert "gentle" in result.lower() or "curious" in result.lower()

    def test_step_2_social_proof(self):
        lead = {"name": "James Wu", "company": "StartupCo"}
        result = build_follow_up_prompt(lead, 2, "self_serve")
        assert "social proof" in result.lower() or "benefit" in result.lower()

    def test_step_3_final(self):
        lead = {"name": "Emily Park", "company": "AI Corp"}
        result = build_follow_up_prompt(lead, 3, "enterprise")
        assert "final" in result.lower() or "graceful" in result.lower()

    def test_includes_format_instruction(self):
        lead = {"name": "Test", "company": "Co"}
        result = build_follow_up_prompt(lead, 1, "enterprise")
        assert "Subject:" in result

    def test_includes_product_info(self):
        lead = {"name": "Test", "company": "Co"}
        result = build_follow_up_prompt(lead, 1, "self_serve")
        assert "Voco V2" in result
        assert "$49/mo" in result

    def test_step_beyond_3_uses_final_message(self):
        lead = {"name": "Test", "company": "Co"}
        result = build_follow_up_prompt(lead, 5, "enterprise")
        assert "final" in result.lower() or "graceful" in result.lower()


# ===================================================================
# build_audit_prompt
# ===================================================================


class TestBuildAuditPrompt:
    """Tests for build_audit_prompt."""

    def test_includes_kpi_data(self):
        kpi = {
            "total_processed": 100,
            "hot_leads": 20,
            "cold_leads": 70,
            "responded": 10,
            "delivery_rate": 0.95,
            "close_rate": 0.15,
        }
        result = build_audit_prompt(kpi, [])
        assert "100" in result
        assert "20" in result
        assert "70" in result
        assert "95.0%" in result
        assert "15.0%" in result

    def test_includes_existing_suggestions(self):
        kpi = {"total_processed": 50, "hot_leads": 5, "cold_leads": 40,
               "responded": 5, "delivery_rate": 0.80, "close_rate": 0.10}
        suggestions = ["Improve subject lines", "Target more enterprises"]
        result = build_audit_prompt(kpi, suggestions)
        assert "Improve subject lines" in result
        assert "Target more enterprises" in result

    def test_empty_suggestions(self):
        kpi = {"total_processed": 0, "hot_leads": 0, "cold_leads": 0,
               "responded": 0, "delivery_rate": 0.0, "close_rate": 0.0}
        result = build_audit_prompt(kpi, [])
        assert "None" in result

    def test_returns_nonempty(self):
        kpi = {"total_processed": 1, "hot_leads": 0, "cold_leads": 1,
               "responded": 0, "delivery_rate": 1.0, "close_rate": 0.0}
        result = build_audit_prompt(kpi, [])
        assert len(result) > 0
        assert "actionable" in result.lower()

    def test_handles_missing_kpi_keys_gracefully(self):
        """Missing keys should default to 0."""
        kpi = {}
        result = build_audit_prompt(kpi, [])
        assert "0" in result
        assert isinstance(result, str)
