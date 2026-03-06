"""Feedback loop — track what works, auto-adjust recommendations.

Analyzes conversion rates by source and engagement metrics by action type
to surface actionable insights for the founder.
"""
from __future__ import annotations

from db import get_connection

import ledger


def calculate_source_scores(db_path: str = None) -> dict[str, float]:
    """Conversion rate per lead source.

    Returns dict like {"apollo": 0.35, "github": 0.12, ...}
    where value = (hot leads from source) / (total leads from source).
    """
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT source,
               COUNT(*) as total,
               SUM(CASE WHEN status='hot' OR status='responded' THEN 1 ELSE 0 END) as converted
        FROM leads
        WHERE source != '' AND source != 'manual'
        GROUP BY source
    """).fetchall()

    scores = {}
    for r in rows:
        total = r["total"]
        converted = r["converted"] or 0
        scores[r["source"]] = converted / total if total > 0 else 0.0
    return scores


def calculate_engagement_scores(db_path: str = None) -> dict[str, float]:
    """Engagement success rate per action type.

    Returns dict like {"x_reply": 0.85, "li_comment": 0.90, ...}
    where value = (sent) / (total attempts).
    """
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT action_type,
               COUNT(*) as total,
               SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent
        FROM engagement_log
        WHERE action_type != ''
        GROUP BY action_type
    """).fetchall()

    scores = {}
    for r in rows:
        total = r["total"]
        sent = r["sent"] or 0
        scores[r["action_type"]] = sent / total if total > 0 else 0.0
    return scores


def get_recommended_actions(db_path: str = None) -> list[str]:
    """Generate human-readable insights from data.

    Compares source conversion rates and engagement success rates
    to surface actionable recommendations.
    """
    insights: list[str] = []

    # Source insights
    source_scores = calculate_source_scores(db_path)
    if len(source_scores) >= 2:
        sorted_sources = sorted(source_scores.items(), key=lambda x: x[1], reverse=True)
        best = sorted_sources[0]
        worst = sorted_sources[-1]
        if best[1] > 0 and worst[1] >= 0:
            ratio = best[1] / worst[1] if worst[1] > 0 else float("inf")
            if ratio > 2:
                insights.append(
                    f"{best[0].title()} leads convert {ratio:.0f}x better than "
                    f"{worst[0].title()} — consider increasing {best[0].title()} budget"
                )
            elif ratio > 1.3:
                insights.append(
                    f"{best[0].title()} leads have the highest conversion rate ({best[1]:.0%})"
                )

    if source_scores:
        total_rate = sum(source_scores.values()) / len(source_scores)
        if total_rate < 0.1:
            insights.append(
                "Overall conversion rate is low — review ICP targeting criteria"
            )

    # Engagement insights
    eng_scores = calculate_engagement_scores(db_path)
    if eng_scores:
        for action, rate in eng_scores.items():
            if rate < 0.5:
                insights.append(
                    f"{action.replace('_', ' ').title()} has a low success rate ({rate:.0%}) — check API limits"
                )

        # Compare X vs LinkedIn engagement
        x_actions = {k: v for k, v in eng_scores.items() if k.startswith("x_")}
        li_actions = {k: v for k, v in eng_scores.items() if k.startswith("li_")}
        if x_actions and li_actions:
            x_avg = sum(x_actions.values()) / len(x_actions)
            li_avg = sum(li_actions.values()) / len(li_actions)
            if x_avg > li_avg * 1.5:
                insights.append("X engagement outperforms LinkedIn — lean into X replies")
            elif li_avg > x_avg * 1.5:
                insights.append("LinkedIn engagement outperforms X — lean into LinkedIn comments")

    if not insights:
        insights.append("Not enough data yet — keep running the pipeline to generate insights")

    ledger.log(f"Feedback loop: generated {len(insights)} insights")
    return insights
