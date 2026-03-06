"""Tests for feedback_loop.py — source scores, engagement scores, and insights."""
from __future__ import annotations

import os
import tempfile

import pytest

from db import get_connection, _initialized_paths, _init_lock
from feedback_loop import (
    calculate_engagement_scores,
    calculate_source_scores,
    get_recommended_actions,
)


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Force table init for this new path
    with _init_lock:
        _initialized_paths.discard(path)
    conn = get_connection(path)
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# calculate_source_scores
# ---------------------------------------------------------------------------

def test_source_scores_empty_db(tmp_db):
    """Empty leads table returns empty dict."""
    scores = calculate_source_scores(tmp_db)
    assert scores == {}


def test_source_scores_with_data(tmp_db):
    """Verify conversion rates per source with mixed lead statuses."""
    conn = get_connection(tmp_db)
    # apollo: 2 hot out of 4 total = 0.5
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('A1', 'apollo', 'hot')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('A2', 'apollo', 'hot')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('A3', 'apollo', 'cold')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('A4', 'apollo', 'cold')")
    # github: 1 responded out of 2 total = 0.5
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('G1', 'github', 'responded')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('G2', 'github', 'cold')")
    # crunchbase: 0 hot out of 3 total = 0.0
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('C1', 'crunchbase', 'cold')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('C2', 'crunchbase', 'cold')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('C3', 'crunchbase', 'cold')")
    conn.commit()

    scores = calculate_source_scores(tmp_db)
    assert scores["apollo"] == pytest.approx(0.5)
    assert scores["github"] == pytest.approx(0.5)
    assert scores["crunchbase"] == pytest.approx(0.0)


def test_source_scores_ignores_manual_source(tmp_db):
    """Leads with source='manual' should be excluded from scoring."""
    conn = get_connection(tmp_db)
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('M1', 'manual', 'hot')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('M2', 'manual', 'cold')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('A1', 'apollo', 'hot')")
    conn.commit()

    scores = calculate_source_scores(tmp_db)
    assert "manual" not in scores
    assert "apollo" in scores
    assert scores["apollo"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# calculate_engagement_scores
# ---------------------------------------------------------------------------

def test_engagement_scores_empty_db(tmp_db):
    """Empty engagement_log table returns empty dict."""
    scores = calculate_engagement_scores(tmp_db)
    assert scores == {}


def test_engagement_scores_with_data(tmp_db):
    """Verify success rates per action type."""
    conn = get_connection(tmp_db)
    # x_reply: 3 sent out of 4 = 0.75
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'failed')")
    # li_comment: 1 sent out of 2 = 0.5
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'failed')")
    conn.commit()

    scores = calculate_engagement_scores(tmp_db)
    assert scores["x_reply"] == pytest.approx(0.75)
    assert scores["li_comment"] == pytest.approx(0.5)


def test_engagement_scores_mixed_statuses(tmp_db):
    """Only 'sent' counts as success; other statuses (failed, queued) do not."""
    conn = get_connection(tmp_db)
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_tweet', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_tweet', 'failed')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_tweet', 'queued')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_tweet', 'error')")
    conn.commit()

    scores = calculate_engagement_scores(tmp_db)
    assert scores["x_tweet"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# get_recommended_actions
# ---------------------------------------------------------------------------

def test_recommended_actions_no_data(tmp_db):
    """With no leads or engagement, returns 'Not enough data' insight."""
    actions = get_recommended_actions(tmp_db)
    assert len(actions) == 1
    assert "Not enough data" in actions[0]


def test_recommended_actions_best_source_insight(tmp_db):
    """When one source converts 3x better, recommend increasing its budget."""
    conn = get_connection(tmp_db)
    # apollo: 3 out of 4 hot = 0.75
    for _ in range(3):
        conn.execute("INSERT INTO leads (name, source, status) VALUES ('a', 'apollo', 'hot')")
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('a', 'apollo', 'cold')")
    # github: 1 out of 4 hot = 0.25 (ratio = 3x)
    conn.execute("INSERT INTO leads (name, source, status) VALUES ('g', 'github', 'hot')")
    for _ in range(3):
        conn.execute("INSERT INTO leads (name, source, status) VALUES ('g', 'github', 'cold')")
    conn.commit()

    actions = get_recommended_actions(tmp_db)
    combined = " ".join(actions)
    assert "Apollo" in combined
    assert "3x" in combined
    assert "budget" in combined.lower()


def test_recommended_actions_low_conversion(tmp_db):
    """When all sources are below 10%, flag low overall conversion."""
    conn = get_connection(tmp_db)
    # apollo: 0 out of 10 = 0%
    for _ in range(10):
        conn.execute("INSERT INTO leads (name, source, status) VALUES ('a', 'apollo', 'cold')")
    # github: 0 out of 10 = 0%
    for _ in range(10):
        conn.execute("INSERT INTO leads (name, source, status) VALUES ('g', 'github', 'cold')")
    conn.commit()

    actions = get_recommended_actions(tmp_db)
    combined = " ".join(actions)
    assert "low" in combined.lower() or "conversion" in combined.lower()


def test_recommended_actions_low_engagement_rate(tmp_db):
    """Action type with <50% success rate triggers API-limit warning."""
    conn = get_connection(tmp_db)
    # x_reply: 1 sent out of 5 = 20%
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    for _ in range(4):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'failed')")
    conn.commit()

    actions = get_recommended_actions(tmp_db)
    combined = " ".join(actions)
    assert "X Reply" in combined
    assert "20%" in combined
    assert "API" in combined or "api" in combined.lower()


def test_recommended_actions_x_vs_linkedin(tmp_db):
    """When X engagement outperforms LinkedIn 1.5x, recommend X."""
    conn = get_connection(tmp_db)
    # x_reply: 9 out of 10 sent = 90%
    for _ in range(9):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'failed')")
    # li_comment: 4 out of 10 sent = 40% (X avg 90% > 40% * 1.5 = 60%)
    for _ in range(4):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'sent')")
    for _ in range(6):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'failed')")
    conn.commit()

    actions = get_recommended_actions(tmp_db)
    combined = " ".join(actions)
    assert "X engagement outperforms LinkedIn" in combined


def test_recommended_actions_linkedin_vs_x(tmp_db):
    """When LinkedIn engagement outperforms X 1.5x, recommend LinkedIn."""
    conn = get_connection(tmp_db)
    # li_comment: 9 out of 10 sent = 90%
    for _ in range(9):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'sent')")
    conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('linkedin', 'li_comment', 'failed')")
    # x_reply: 4 out of 10 sent = 40% (LI avg 90% > 40% * 1.5 = 60%)
    for _ in range(4):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'sent')")
    for _ in range(6):
        conn.execute("INSERT INTO engagement_log (platform, action_type, status) VALUES ('x', 'x_reply', 'failed')")
    conn.commit()

    actions = get_recommended_actions(tmp_db)
    combined = " ".join(actions)
    assert "LinkedIn engagement outperforms X" in combined
