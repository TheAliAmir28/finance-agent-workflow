from __future__ import annotations

import json
import os

from openai import OpenAI

"""
Generates a structured AI summary of the analysis in `payload`.

Returns a dict:
    {
        "verdict":   short headline call, e.g. "Strong run, elevated risk",
        "tone":      "positive" | "negative" | "mixed" | "neutral",
        "narrative": 2-4 sentence desk-note paragraph,
        "takeaways": [{"text": str, "sentiment": "positive"|"negative"|"neutral"}],
        "risk":      one-sentence biggest risk,
    }

    - If OPENAI_API_KEY is missing, returns None (LLM mode off).
    - If the API call fails or returns unusable JSON, returns None (fail-safe).
"""

_VALID_TONES = {"positive", "negative", "mixed", "neutral"}
_VALID_SENTIMENTS = {"positive", "negative", "neutral"}

_SYSTEM_MSG = (
    "You are a sell-side equity analyst writing the morning desk note. "
    "Voice: direct, concrete, numbers-forward. No filler phrases like "
    "'provides a snapshot' or 'it is important to note'. Put every claim next "
    "to the number that supports it, and contextualize rather than recite: "
    "say whether a Sharpe ratio is strong or weak, whether a drawdown is mild "
    "or punishing, whether valuation looks rich or cheap for the sector. "
    "Weave in fundamentals, the latest earnings result, analyst consensus and "
    "price-target upside, and news headlines when they are provided — they are "
    "context, not a checklist; use what matters, skip what doesn't. "
    "Hard rules: use ONLY the numbers provided (never invent data); if a field "
    "is null or missing, simply don't mention it; never give investment advice "
    "or use words like buy, sell, hold, or should; news headlines may be cited "
    "as sentiment context but never as proven causes of price moves. "
    "Accuracy check: before writing any comparative word (higher, lower, "
    "outperformed, surpasses, beats), re-verify the direction against the two "
    "numbers — a claim pointing the wrong way is worse than no claim."
)

# NOTE: joined with `+` (never str.format) — the JSON examples below contain
# literal braces that .format() would misread as placeholders.
_USER_MSG_PREFIX = (
    "Write the desk note for this analysis as JSON with exactly these keys:\n"
    '- "verdict": the headline call in at most 8 words, e.g. '
    '"Strong run, but the ride was rough".\n'
    '- "tone": one of "positive", "negative", "mixed", "neutral" — the overall '
    "read of the data.\n"
    '- "narrative": 2-4 sentences. Lead with the story of the period, then the '
    "most decision-relevant context (risk-adjusted quality, valuation, "
    "earnings momentum, street view). For comparisons: open with the verdict "
    "on who won and why, then the single factor that separates the two.\n"
    '- "takeaways": exactly 3 or 4 items, each {"text": one sharp sentence, '
    '"sentiment": "positive"|"negative"|"neutral"}. Each must carry a number. '
    "Cover different ground than the narrative where possible.\n"
    '- "risk": one sentence naming the biggest risk visible in this data '
    "(drawdown depth, volatility, valuation, earnings miss, thin coverage...).\n\n"
    "DATA:\n"
)


def _clean_takeaways(raw):
    """Coerce the model's takeaways into [{text, sentiment}], dropping junk."""
    takeaways = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        sentiment = str(item.get("sentiment") or "").strip().lower()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"
        takeaways.append({"text": text, "sentiment": sentiment})
    return takeaways[:4]


def generate_llm_summary(payload, use_llm: bool = True):
    # If the user explicitly disabled LLM summaries, stop immediately
    if not use_llm:
        return None
    # Read API key from environment variable
    # If it's missing, LLM mode is automatically disabled
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        client = OpenAI()

        # default=str keeps the request safe if a stray date or numpy scalar
        # slips through the payload builders.
        data = json.dumps(payload, indent=1, default=str)

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": _USER_MSG_PREFIX + data},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")

        narrative = str(raw.get("narrative") or "").strip()
        if not narrative:
            return None

        tone = str(raw.get("tone") or "").strip().lower()
        return {
            "verdict": str(raw.get("verdict") or "").strip() or None,
            "tone": tone if tone in _VALID_TONES else "neutral",
            "narrative": narrative,
            "takeaways": _clean_takeaways(raw.get("takeaways")),
            "risk": str(raw.get("risk") or "").strip() or None,
        }

    except Exception:
        # Fail-safe behavior:
        # If the API errors, times out, or anything breaks,
        # the core app continues without AI.
        return None


def summary_to_text(summary):
    """Render a structured summary as plain text for the .txt report."""
    if not summary:
        return ""
    lines = []
    if summary.get("verdict"):
        lines.append(f"Verdict: {summary['verdict']}")
    if summary.get("narrative"):
        lines.append(summary["narrative"])
    takeaways = summary.get("takeaways") or []
    if takeaways:
        lines.append("Key takeaways:")
        lines.extend(f"- {item['text']}" for item in takeaways)
    if summary.get("risk"):
        lines.append(f"Biggest risk: {summary['risk']}")
    lines.append("Not financial advice.")
    return "\n".join(lines)
