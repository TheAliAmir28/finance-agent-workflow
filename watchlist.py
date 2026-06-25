"""Watchlist persistence and daily-summary computation.

Stores a single user watchlist as JSON in output/watchlist.json. Each entry is
a ticker the user wants to follow, with an optional `shares` count so the same
list can represent either plain favorites (shares omitted) or real holdings.

The live-quote fetching lives in app.py (it owns the yfinance helpers); this
module only stores the list and turns a set of quotes into a daily summary.
"""

import json
from datetime import datetime
from pathlib import Path

WATCHLIST_PATH = Path("output") / "watchlist.json"
MAX_ITEMS = 30


def _normalize_ticker(ticker):
    return str(ticker or "").strip().upper()


def _coerce_shares(shares):
    """Return a positive float, or None for a plain favorite."""
    if shares in (None, ""):
        return None
    try:
        value = float(shares)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def load_watchlist():
    """Return the saved watchlist as a list of {ticker, shares, added_at}."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    items = data.get("items", []) if isinstance(data, dict) else []
    cleaned = []
    for item in items:
        ticker = _normalize_ticker(item.get("ticker"))
        if not ticker:
            continue
        cleaned.append({
            "ticker": ticker,
            "shares": _coerce_shares(item.get("shares")),
            "added_at": item.get("added_at"),
        })
    return cleaned


def _save(items):
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2)


def add_to_watchlist(ticker, shares=None):
    """Add or update a ticker. Returns the updated list.

    Assumes the ticker has already been validated by the caller (app.py checks
    that a live quote exists before calling this).
    """
    ticker = _normalize_ticker(ticker)
    if not ticker:
        raise ValueError("Ticker is required.")

    items = load_watchlist()
    shares = _coerce_shares(shares)

    for item in items:
        if item["ticker"] == ticker:
            item["shares"] = shares  # update existing entry in place
            _save(items)
            return items

    if len(items) >= MAX_ITEMS:
        raise ValueError(f"Watchlist is full (max {MAX_ITEMS}).")

    items.append({
        "ticker": ticker,
        "shares": shares,
        "added_at": datetime.now().isoformat(timespec="seconds"),
    })
    _save(items)
    return items


def remove_from_watchlist(ticker):
    """Remove a ticker. Returns the updated list."""
    ticker = _normalize_ticker(ticker)
    items = [item for item in load_watchlist() if item["ticker"] != ticker]
    _save(items)
    return items


def _format_percent(value):
    if value is None:
        return "N/A"
    return f"{value:+.2%}"


def build_watchlist_summary(items, quotes):
    """Turn the watchlist + a {ticker: quote} map into a daily summary.

    `quotes` values follow the shape returned by app.fetch_live_quote
    (price, change, change_percent as a fraction, direction, ...).

    Returns a dict with the headline narrative plus the structured numbers and
    per-row data the dashboard renders.
    """
    rows = []
    changes = []                 # (ticker, change_percent) for items with a quote
    total_value = 0.0
    total_day_change = 0.0
    total_prev_value = 0.0
    has_holdings = False
    quoted_changes = []          # plain list of change_percent for equal-weight avg

    for item in items:
        ticker = item["ticker"]
        shares = item.get("shares")
        quote = quotes.get(ticker) or {}
        price = quote.get("price")
        change = quote.get("change")
        change_percent = quote.get("change_percent")

        row = {
            "ticker": ticker,
            "shares": shares,
            "available": bool(quote),
            "price": price,
            "price_text": quote.get("price_text", "—"),
            "change_percent": change_percent,
            "change_percent_text": quote.get("change_percent_text", "N/A"),
            "direction": quote.get("direction", "neutral"),
            "position_value": None,
            "position_value_text": None,
            "day_change_value": None,
            "day_change_value_text": None,
        }

        if change_percent is not None:
            changes.append((ticker, change_percent))
            quoted_changes.append(change_percent)

        if shares and price is not None:
            has_holdings = True
            value = price * shares
            row["position_value"] = value
            row["position_value_text"] = f"${value:,.2f}"
            total_value += value
            if change is not None:
                day_change = change * shares
                row["day_change_value"] = day_change
                row["day_change_value_text"] = (
                    f"{'+' if day_change >= 0 else '-'}${abs(day_change):,.2f}"
                )
                total_day_change += day_change
                total_prev_value += value - day_change

        rows.append(row)

    # Equal-weighted average daily move across everything we have a quote for.
    avg_change_pct = (
        sum(quoted_changes) / len(quoted_changes) if quoted_changes else None
    )
    # Value-weighted move for real holdings (what the portfolio actually did).
    weighted_change_pct = (
        total_day_change / total_prev_value if total_prev_value else None
    )
    headline_pct = weighted_change_pct if has_holdings and weighted_change_pct is not None else avg_change_pct

    leader = max(changes, key=lambda c: c[1]) if changes else None
    laggard = min(changes, key=lambda c: c[1]) if changes else None

    narrative = _build_narrative(headline_pct, leader, laggard, len(rows))

    return {
        "narrative": narrative,
        "headline_pct": headline_pct,
        "headline_pct_text": _format_percent(headline_pct),
        "direction": _direction(headline_pct),
        "has_holdings": has_holdings,
        "total_value": total_value if has_holdings else None,
        "total_value_text": f"${total_value:,.2f}" if has_holdings else None,
        "total_day_change": total_day_change if has_holdings else None,
        "total_day_change_text": (
            f"{'+' if total_day_change >= 0 else '-'}${abs(total_day_change):,.2f}"
            if has_holdings else None
        ),
        "leader": {"ticker": leader[0], "change_percent": leader[1]} if leader else None,
        "laggard": {"ticker": laggard[0], "change_percent": laggard[1]} if laggard else None,
        "count": len(rows),
        "rows": rows,
    }


def _direction(pct):
    if pct is None:
        return "neutral"
    if pct > 0.00005:
        return "positive"
    if pct < -0.00005:
        return "negative"
    return "neutral"


def _build_narrative(headline_pct, leader, laggard, count):
    if count == 0:
        return "Your watchlist is empty. Add a few tickers to see how they're doing today."
    if headline_pct is None:
        return "Live quotes are unavailable right now. Try again in a moment."

    direction = _direction(headline_pct)
    if direction == "positive":
        lead = f"Your watchlist is up {abs(headline_pct):.1%} today."
    elif direction == "negative":
        lead = f"Your watchlist is down {abs(headline_pct):.1%} today."
    else:
        lead = "Your watchlist is roughly flat today."

    parts = [lead]

    # "carrying the day" only makes sense when something is actually up.
    if leader and leader[1] > 0.00005 and count > 1:
        parts.append(f"{leader[0]} is carrying the day ({leader[1]:+.1%}).")

    # Biggest decliner — only mention when something is actually down, and when
    # it isn't the same single name we just called the leader.
    if laggard and laggard[1] < -0.00005 and (not leader or laggard[0] != leader[0]):
        parts.append(f"{laggard[0]} has the biggest drawdown ({laggard[1]:+.1%}).")

    return " ".join(parts)
