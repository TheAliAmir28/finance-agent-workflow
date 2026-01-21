from __future__ import annotations

import os
from typing import Optional, Dict, Any

from openai import OpenAI

"""
Returns a short natural-language summary of the metrics in `payload`.
    - If OPENAI_API_KEY is missing, returns None (LLM mode off).
    - If the API call fails, returns None (fail-safe).
"""
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
        # Create OpenAI client using the environment key
        client = OpenAI()

        # Keep the input small and predictable
        system_msg = (
            "You are a helpful assistant summarizing stock performance metrics. "
            "Write in simple, clear English. Be concise. "
            "Do NOT give financial advice (no 'buy/sell/should'). "
            "Use the numbers provided; do not invent data."
        )
        # User message explains exactly what format we want
        # The payload contains only clean, structured numbers
        user_msg = (
            "Write a short summary (120-180 words) of this analysis.\n\n"
            "Requirements:\n"
            "- 1 short paragraph + 3 bullet key takeaways.\n"
            "- Mention return, volatility, and Sharpe ratio.\n"
            "- If there are two tickers, mention who had better risk-adjusted performance.\n"
            "- End with: 'Not financial advice.'\n\n"
            f"DATA:\n{payload}"
        )
        # Make the API request
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_output_tokens=260,
            temperature=0.4,
        )
        # Get the generated text
        text = (resp.output_text or "").strip()
        # Return text only if something meaningful was generated
        return text if text else None

    except Exception:
        # Fail-safe behavior:
        # If the API errors, times out, or anything breaks,
        # the core app continues without AI.
        return None
