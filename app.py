from flask import Flask, render_template, request, send_file, abort, redirect, url_for, jsonify
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import math
import re
import threading
import time
import uuid
import yfinance as yf
from main import run_analysis_from_request
from agent_trace import AgentTracer
from history import clear_history, delete_history_file, load_recent_history
from watchlist import (
    add_to_watchlist,
    build_watchlist_summary,
    clear_watchlist,
    load_watchlist,
    remove_from_watchlist,
)
from tools.interactive_charts import (
    build_comparison_chart_json,
    build_price_chart_json,
)
from tools.analyst import brand_color_for_ticker, logo_candidates_for_ticker, logo_url_for_ticker
from tools.crypto import is_crypto_symbol, normalize_crypto_symbol

app = Flask(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
ALLOWED_FILE_DIRS = [
    PROJECT_ROOT / "output",
    PROJECT_ROOT / "reports" / "generated",
]
INTERVAL_OPTIONS = [
    {"value": "1d",  "label": "1D",  "phrase": "1 day"},
    {"value": "5d",  "label": "5D",  "phrase": "5 days"},
    {"value": "1mo", "label": "1M",  "phrase": "1 month"},
    {"value": "3mo", "label": "3M",  "phrase": "3 months"},
    {"value": "6mo", "label": "6M",  "phrase": "6 months"},
    {"value": "1y",  "label": "1Y",  "phrase": "1 year"},
    {"value": "2y",  "label": "2Y",  "phrase": "2 years"},
    {"value": "5y",  "label": "5Y",  "phrase": "5 years"},
]
INTERVAL_PHRASES = {
    option["value"]: option["phrase"]
    for option in INTERVAL_OPTIONS
}
SUMMARY_OPTIONS = [
    {"value": "with_summary", "label": "With summary", "phrase": "with summary"},
    {"value": "no_summary", "label": "No summary", "phrase": "no summary"},
]
SUMMARY_PHRASES = {
    option["value"]: option["phrase"]
    for option in SUMMARY_OPTIONS
}
# Human-readable tool names for the live trace feed (mirrors the template).
TOOL_LABELS = {
    "planner": "Planner", "data": "Market Data", "metrics": "Analytics",
    "charts": "Charts", "analyst": "Analyst", "fundamentals": "Fundamentals",
    "earnings": "Earnings", "news": "News", "compare": "Comparison",
}

def format_percent(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "N/A"

def format_number(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"

def as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def read_float_field(source, *field_names):
    if not source:
        return None

    for field_name in field_names:
        try:
            value = source.get(field_name)
        except AttributeError:
            value = getattr(source, field_name, None)
        except Exception:
            continue

        number = as_float(value)
        if number is not None:
            return number

    return None

def build_request_with_controls(user_input, interval, summary_mode):
    request_text = user_input.strip()

    if summary_mode in SUMMARY_PHRASES:
        request_text = re.sub(
            r"\b(?:with|no)\s+summary\b",
            "",
            request_text,
            flags=re.IGNORECASE,
        )
        request_text = " ".join(request_text.split())

    interval_phrase = INTERVAL_PHRASES.get(interval)
    if interval_phrase:
        request_text = f"{request_text} for {interval_phrase}"

    summary_phrase = SUMMARY_PHRASES.get(summary_mode)
    if summary_phrase:
        request_text = f"{request_text} {summary_phrase}"

    return request_text

def build_chart_summary(price_data):
    if price_data is None or price_data.empty or "Close" not in price_data.columns:
        return {"latest_close": "N/A", "period_return": "N/A", "return_class": "neutral"}

    close = price_data["Close"]
    start_price = float(close.iloc[0])
    latest_close = float(close.iloc[-1])

    if start_price == 0:
        period_return = None
    else:
        period_return = (latest_close / start_price) - 1

    return_class = "neutral"
    if period_return is not None:
        if period_return > 0:
            return_class = "positive"
        elif period_return < 0:
            return_class = "negative"

    return {
        "latest_close": f"${latest_close:,.2f}",
        "period_return": format_percent(period_return),
        "return_class": return_class,
    }

def format_currency(value):
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"

def format_signed_currency(value):
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "+" if number >= 0 else "-"
    return f"{sign}${abs(number):,.2f}"

def format_large_currency(value):
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"

    magnitude_labels = [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
    ]
    for magnitude, label in magnitude_labels:
        if abs(number) >= magnitude:
            return f"${number / magnitude:.2f}{label}"

    return f"${number:,.0f}"

def format_date_label(value):
    if not value:
        return "N/A"
    try:
        return datetime.fromisoformat(str(value)).strftime("%b %d, %Y")
    except ValueError:
        return str(value)

def format_history_timestamp(timestamp):
    """Format a saved run timestamp (YYYY-MM-DD_HH-MM-SS) as a clean
    '06/25/2026 - 3:24 PM EST' label for the Recent Runs sidebar."""
    if not timestamp:
        return ""
    try:
        dt = datetime.strptime(str(timestamp), "%Y-%m-%d_%H-%M-%S")
    except (ValueError, TypeError):
        return str(timestamp)

    hour = dt.strftime("%I").lstrip("0") or "12"   # 02 PM -> 2 PM
    return f"{dt.month:02d}/{dt.day:02d}/{dt.year} - {hour}:{dt.strftime('%M %p')} EST"

def format_signed_percent(value):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):+.2%}"
    except (TypeError, ValueError):
        return "N/A"

# ── Analyst sentiment gauge ──
# A semicircular 5-segment gauge (Strong Sell → Strong Buy) with a needle whose
# angle comes from recommendationMean. The arc/label geometry is identical for
# every card, so it's computed once here; only the needle angle and per-rating
# counts vary per company. Colors run red → green and are shared with the hover
# tooltip's dots so a rating reads the same in both places.
_RATING_META = [
    # key,           label,          color      (ordered Strong Buy → Strong Sell
    ("strong_buy",  "Strong Buy",  "#2FA84F"),  #  for the tooltip, best on top)
    ("buy",         "Buy",         "#7CC067"),
    ("hold",        "Hold",        "#E0B33A"),
    ("sell",        "Sell",        "#F2721B"),
    ("strong_sell", "Strong Sell", "#E5484D"),
]


def _build_gauge_geometry():
    cx, cy, r, label_r = 115.0, 100.0, 64.0, 92.0
    stroke = 14
    gap_deg = 3.0
    # Segments run left → right on the arc: Strong Sell … Strong Buy.
    segments_lr = [
        ("strong_sell", "#E5484D", ["Strong", "Sell"]),
        ("sell",        "#F2721B", ["Sell"]),
        ("hold",        "#E0B33A", ["Hold"]),
        ("buy",         "#7CC067", ["Buy"]),
        ("strong_buy",  "#2FA84F", ["Strong", "Buy"]),
    ]

    def polar(radius, deg):
        a = math.radians(deg)
        return cx + radius * math.cos(a), cy - radius * math.sin(a)

    span = 180.0 / len(segments_lr)
    segments = []
    for i, (key, color, lines) in enumerate(segments_lr):
        start = 180.0 - i * span - gap_deg / 2
        end = 180.0 - (i + 1) * span + gap_deg / 2
        x1, y1 = polar(r, start)
        x2, y2 = polar(r, end)
        mid = (start + end) / 2
        lx, ly = polar(label_r, mid)
        # Center every label on its radial point so the outer two-line labels
        # ("Strong Sell"/"Strong Buy") stay balanced and never run off the box.
        anchor = "middle"
        segments.append({
            "key": key,
            "color": color,
            "d": f"M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 0 1 {x2:.2f} {y2:.2f}",
            "lines": lines,
            "lx": round(lx, 1),
            "ly": round(ly, 1),
            "anchor": anchor,
        })

    return {
        "view_box": "0 0 230 116",
        "cx": cx,
        "cy": cy,
        "stroke": stroke,
        # Needle: a slim triangle pointing straight up, rotated about the hub.
        # Tip stops just short of the arc's inner edge.
        "needle": f"M {cx - 4} {cy} L {cx} {cy - 54} L {cx + 4} {cy} Z",
        "hub_r": 7,
        "segments": segments,
    }


ANALYST_GAUGE = _build_gauge_geometry()


def build_analyst_card(analyst_view):
    if not analyst_view:
        return None

    upside = analyst_view.get("upside")
    upside_class = "neutral"
    if upside is not None:
        if upside > 0:
            upside_class = "positive"
        elif upside < 0:
            upside_class = "negative"

    analyst_count = analyst_view.get("analyst_count")
    try:
        analyst_count_text = f"{int(analyst_count)} analysts" if analyst_count is not None else "N/A"
    except (TypeError, ValueError):
        analyst_count_text = "N/A"

    recommendation = analyst_view.get("recommendation", "Unavailable")
    sentiment_positions = {
        "Strong Sell": 0,
        "Sell": 25,
        "Hold": 50,
        "Buy": 75,
        "Strong Buy": 100,
    }
    sentiment_position = sentiment_positions.get(recommendation, 50)

    # Needle points at the exact center of the verdict's segment so it lines up
    # cleanly with both the arc band and the label below. Each of the 5 segments
    # spans 36°, so their centers sit at -72°, -36°, 0° (Hold, straight up),
    # +36°, +72°. If the verdict isn't one of the five, fall back to the 1–5
    # mean to pick which segment, then still center the needle in it.
    verdict_angles = {
        "Strong Sell": -72,
        "Sell": -36,
        "Hold": 0,
        "Buy": 36,
        "Strong Buy": 72,
    }
    if recommendation in verdict_angles:
        needle_angle = verdict_angles[recommendation]
    else:
        mean = analyst_view.get("recommendation_mean")
        if mean is not None and mean > 0:
            fraction = max(0.0, min(1.0, (5 - mean) / 4))
        else:
            fraction = sentiment_position / 100
        segment_index = min(4, max(0, int(fraction * 5)))
        needle_angle = (segment_index - 2) * 36

    # Per-rating counts for the hover tooltip (Strong Buy → Strong Sell), with
    # the same colored dots the gauge segments use.
    rating_counts = analyst_view.get("rating_counts") or {}
    rating_rows = [
        {"label": label, "color": color, "count": rating_counts.get(key, 0)}
        for key, label, color in _RATING_META
    ] if rating_counts else []
    total_ratings = sum(rating_counts.values()) if rating_counts else 0

    if total_ratings:
        based_on_text = f"Based on {total_ratings} analyst{'s' if total_ratings != 1 else ''}"
    elif analyst_count_text != "N/A":
        based_on_text = f"Based on {analyst_count_text}"
    else:
        based_on_text = ""

    return {
        "ticker": analyst_view.get("ticker", ""),
        "available": analyst_view.get("available", False),
        "recommendation": recommendation,
        "sentiment_position": sentiment_position,
        "needle_angle": needle_angle,
        "rating_rows": rating_rows,
        "has_breakdown": bool(rating_rows),
        "total_ratings": total_ratings,
        "based_on_text": based_on_text,
        "analyst_count": analyst_count_text,
        "target_mean": format_currency(analyst_view.get("target_mean")),
        "target_low": format_currency(analyst_view.get("target_low")),
        "target_high": format_currency(analyst_view.get("target_high")),
        "current_price": format_currency(analyst_view.get("current_price")),
        "upside": format_percent(upside),
        "upside_class": upside_class,
        "error": analyst_view.get("error"),
    }

def build_earnings_card(earnings, logo_url=None):
    if not earnings:
        return None

    eps_result = earnings.get("eps_result")
    revenue_result = earnings.get("revenue_result")
    eps_surprise = earnings.get("eps_surprise")
    revenue_surprise = earnings.get("revenue_surprise")
    last_report_date = format_date_label(earnings.get("last_report_date"))
    last_report_label = (
        f"{last_report_date} (period end)"
        if earnings.get("last_report_date_is_period_end") and last_report_date != "N/A"
        else last_report_date
    )

    return {
        "ticker": earnings.get("ticker", ""),
        "logo_url": logo_url,
        "available": earnings.get("available", False),
        "last_report_date": last_report_date,
        "last_report_label": last_report_label,
        "next_call_date": format_date_label(earnings.get("next_call_date")),
        "next_call_date_is_estimate": earnings.get("next_call_date_is_estimate", False),
        "next_call_label": (
            f"{format_date_label(earnings.get('next_call_date'))} (estimated)"
            if earnings.get("next_call_date") and earnings.get("next_call_date_is_estimate", False)
            else format_date_label(earnings.get("next_call_date"))
        ),
        "fiscal_period": earnings.get("fiscal_period") or "N/A",
        "eps_actual": format_currency(earnings.get("eps_actual")),
        "eps_estimate": format_currency(earnings.get("eps_estimate")),
        "eps_surprise": format_signed_percent(eps_surprise),
        "eps_has_surprise": eps_surprise is not None and eps_result is not None,
        "eps_result": eps_result or "N/A",
        "eps_result_class": eps_result or "neutral",
        "revenue_actual": format_large_currency(earnings.get("revenue_actual")),
        "revenue_estimate": format_large_currency(earnings.get("revenue_estimate")),
        "revenue_surprise": format_signed_percent(revenue_surprise),
        "revenue_has_surprise": revenue_surprise is not None and revenue_result is not None,
        "revenue_result": revenue_result or "N/A",
        "revenue_result_class": revenue_result or "neutral",
        "error": earnings.get("error"),
    }

def build_fundamentals_card(fundamentals, logo_url=None):
    if not fundamentals:
        return None

    return {
        "ticker": fundamentals.get("ticker", ""),
        "logo_url": logo_url,
        "available": fundamentals.get("available", False),
        "company_name": fundamentals.get("company_name") or fundamentals.get("ticker", ""),
        "sector": fundamentals.get("sector") or "N/A",
        "industry": fundamentals.get("industry") or "N/A",
        "rows": [
            {"label": "Market cap", "value": format_large_currency(fundamentals.get("market_cap"))},
            {"label": "P/E ratio", "value": format_number(fundamentals.get("pe_ratio"))},
            {"label": "Revenue growth", "value": format_percent(fundamentals.get("revenue_growth"))},
            {"label": "EPS", "value": format_currency(fundamentals.get("eps"))},
            {"label": "Dividend yield", "value": format_percent(fundamentals.get("dividend_yield"))},
        ],
        "error": fundamentals.get("error"),
    }

def build_report_metric_card(ticker, metrics, logo_url=None):
    metrics = metrics or {}
    return {
        "ticker": ticker,
        "logo_url": logo_url,
        "rows": [
            {"label": "Total return", "value": format_percent(metrics.get("total_return"))},
            {"label": "Volatility", "value": format_percent(metrics.get("volatility"))},
            {"label": "Sharpe ratio", "value": format_number(metrics.get("sharpe_ratio"))},
            {"label": "Annualized volatility", "value": format_percent(metrics.get("annualized_volatility"))},
            {"label": "Annualized Sharpe", "value": format_number(metrics.get("annualized_sharpe_ratio"))},
            {"label": "CAGR", "value": format_percent(metrics.get("cagr"))},
            {"label": "Max drawdown", "value": format_percent(metrics.get("max_drawdown"))},
            {"label": "20-day moving average", "value": format_number(metrics.get("ma_20"))},
            {"label": "50-day moving average", "value": format_number(metrics.get("ma_50"))},
        ],
    }

# Tone chip labels for the AI insight cards ("positive" reads as a stance the
# app shouldn't take; desk-note language stays on the right side of advice).
TONE_LABELS = {
    "positive": "Constructive",
    "negative": "Cautious",
    "mixed": "Mixed",
    "neutral": "Neutral",
}


def build_llm_summary_card(title, summary):
    """Shape a structured LLM summary (see tools/llm_client.py) for the
    template. Plain strings (a legacy summary or an unexpected model reply)
    degrade to a narrative-only card."""
    if isinstance(summary, str):
        summary = {"narrative": summary.strip(), "tone": "neutral"}

    tone = summary.get("tone") or "neutral"
    takeaways = [
        {
            "text": item.get("text", ""),
            "sentiment": item.get("sentiment", "neutral"),
        }
        for item in (summary.get("takeaways") or [])
        if isinstance(item, dict) and item.get("text")
    ]

    return {
        "title": title,
        "verdict": summary.get("verdict"),
        "tone": tone,
        "tone_label": TONE_LABELS.get(tone, "Neutral"),
        "summary": summary.get("narrative", ""),
        "takeaways": takeaways,
        "risk": summary.get("risk"),
        "disclaimer": "Not financial advice.",
    }

def _format_duration(ms):
    if ms is None:
        return ""
    try:
        ms = float(ms)
    except (TypeError, ValueError):
        return ""
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.2f} s"


def build_trace_view(trace):
    """Shape the raw execution trace for the template: add display-friendly
    duration labels and a rolled-up status verdict for the trace panel."""
    if not trace:
        return None

    events = []
    for event in trace.get("events", []):
        view = dict(event)
        view["duration_text"] = _format_duration(event.get("duration_ms"))
        events.append(view)

    summary = dict(trace.get("summary", {}))
    summary["total_text"] = _format_duration(summary.get("total_ms"))

    if summary.get("error"):
        summary["verdict"] = "errors"
        summary["verdict_label"] = "Completed with errors"
    elif summary.get("warn"):
        summary["verdict"] = "partial"
        summary["verdict_label"] = "Completed · partial data"
    else:
        summary["verdict"] = "clean"
        summary["verdict_label"] = "All steps nominal"

    return {
        "events": events,
        "stages": trace.get("stages", []),
        "summary": summary,
    }


def fetch_live_quote(ticker):
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker is required.")

    yahoo_symbol = normalize_crypto_symbol(symbol)
    stock = yf.Ticker(yahoo_symbol)
    fast_info = {}
    try:
        fast_info = stock.fast_info or {}
    except Exception:
        fast_info = {}

    price = (
        read_float_field(fast_info, "last_price", "lastPrice", "regular_market_price")
    )
    previous_close = (
        read_float_field(fast_info, "previous_close", "previousClose", "regular_market_previous_close")
    )

    if price is None or previous_close is None:
        info = stock.get_info() or {}
        price = price or read_float_field(info, "currentPrice", "regularMarketPrice")
        previous_close = (
            previous_close
            or read_float_field(info, "previousClose", "regularMarketPreviousClose")
        )

    if price is None:
        raise ValueError(f"No live quote found for {symbol}.")

    change = None
    change_percent = None
    if previous_close not in (None, 0):
        change = price - previous_close
        change_percent = change / previous_close

    return {
        "ticker": symbol,
        "price": price,
        "price_text": (f"{price:,.2f}" if symbol.startswith("^") else format_currency(price)),
        "change": change,
        "change_text": format_signed_currency(change),
        "change_percent": change_percent,
        "change_percent_text": format_signed_percent(change_percent),
        "direction": "positive" if change and change > 0 else "negative" if change and change < 0 else "neutral",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "is_crypto": is_crypto_symbol(symbol),
        "source": "Yahoo Finance",
    }

@app.route("/open")
def open_file():
    file_path = request.args.get("path", "").strip()

    if not file_path:
        abort(400)

    resolved_path = Path(file_path).resolve()
    allowed = any(
        resolved_path == allowed_dir.resolve()
        or allowed_dir.resolve() in resolved_path.parents
        for allowed_dir in ALLOWED_FILE_DIRS
    )

    if not allowed:
        abort(403)

    if not resolved_path.exists() or not resolved_path.is_file():
        abort(404)

    return send_file(resolved_path)


@app.route("/history/delete", methods=["POST"])
def delete_history_run():
    history_path = request.form.get("history_path", "").strip()

    if not history_path:
        abort(400)

    try:
        delete_history_file(history_path)
    except ValueError:
        abort(403)

    return redirect(url_for("index"))


@app.route("/history/clear", methods=["POST"])
def clear_history_runs():
    clear_history()
    return redirect(url_for("index"))

@app.route("/api/quotes")
def live_quotes():
    raw_tickers = request.args.get("tickers", "")
    tickers = [
        ticker.strip().upper()
        for ticker in raw_tickers.split(",")
        if ticker.strip()
    ]
    tickers = list(dict.fromkeys(tickers))[:2]

    if not tickers:
        return jsonify({"quotes": {}, "errors": {"request": "No tickers provided."}}), 400

    quotes = {}
    errors = {}
    for ticker in tickers:
        try:
            quotes[ticker] = fetch_live_quote(ticker)
        except Exception as exc:
            errors[ticker] = str(exc)

    return jsonify({
        "quotes": quotes,
        "errors": errors,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })


@app.route("/api/tape-quotes")
def tape_quotes():
    """Bulk quote fetch for the ticker tape — parallel, up to 20 symbols."""
    raw_tickers = request.args.get("tickers", "")
    tickers = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()]
    tickers = list(dict.fromkeys(tickers))[:60]

    if not tickers:
        return jsonify({"quotes": {}, "errors": {}}), 400

    quotes = {}
    errors = {}

    def _fetch(ticker):
        try:
            return ticker, fetch_live_quote(ticker), None
        except Exception as exc:
            return ticker, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(len(tickers), 20)) as pool:
        for ticker, quote, err in pool.map(_fetch, tickers):
            if quote:
                quotes[ticker] = quote
            else:
                errors[ticker] = err

    return jsonify({
        "quotes": quotes,
        "errors": errors,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })


def _fetch_watchlist_quotes(items):
    """Fetch live quotes for every watchlist ticker in parallel."""
    tickers = [item["ticker"] for item in items]
    quotes = {}
    errors = {}
    if not tickers:
        return quotes, errors

    def _fetch(ticker):
        try:
            return ticker, fetch_live_quote(ticker), None
        except Exception as exc:
            return ticker, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(len(tickers), 20)) as pool:
        for ticker, quote, err in pool.map(_fetch, tickers):
            if quote:
                quotes[ticker] = quote
            else:
                errors[ticker] = err
    return quotes, errors


# Logo sources are resolved over the network the first time a ticker is seen,
# then cached on disk. That network work must never run inside the 30-second
# watchlist poll: a slow probe would stall the (single-shared) request handling
# and freeze every live price. So the poll path reads logos from cache only, and
# this warmer resolves them once per ticker in the background.
_logo_warm_seen = set()
_logo_warm_lock = threading.Lock()


def _warm_logos_async(tickers):
    """Resolve + cache logo sources for new tickers off the request path."""
    with _logo_warm_lock:
        fresh = [t for t in tickers if t and t not in _logo_warm_seen]
        _logo_warm_seen.update(fresh)
    if not fresh:
        return

    def _run():
        for ticker in fresh:
            try:
                logo_candidates_for_ticker(ticker, allow_network=True)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def _watchlist_items_payload(items):
    """Attach ordered logo candidates to each item for client-side rendering.

    Cache-only (allow_network=False) so a poll never blocks on the network;
    `_warm_logos_async` populates that cache in the background.
    """
    if not items:
        return []

    return [
        {
            "ticker": item["ticker"],
            "shares": item.get("shares"),
            "logos": logo_candidates_for_ticker(item["ticker"], allow_network=False),
        }
        for item in items
    ]


@app.route("/api/watchlist")
def watchlist_summary():
    items = load_watchlist()
    _warm_logos_async([item["ticker"] for item in items])
    quotes, errors = _fetch_watchlist_quotes(items)
    summary = build_watchlist_summary(items, quotes)
    return jsonify({
        "items": _watchlist_items_payload(items),
        "summary": summary,
        "errors": errors,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })


# Typeahead suggestions hit Yahoo's search endpoint on (debounced) keystrokes,
# so repeated queries are served from this small TTL cache instead of the
# network — both for speed and to stay clear of Yahoo throttling.
_SYMBOL_SEARCH_TTL = 600
_SYMBOL_SEARCH_MAX_ENTRIES = 500
_symbol_search_cache = {}
_symbol_search_lock = threading.Lock()

# Quote types that make sense in a watchlist; filters out options, futures, etc.
_SEARCHABLE_QUOTE_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY", "INDEX", "MUTUALFUND"}


@app.route("/api/symbol-search")
def symbol_search():
    """Symbol suggestions for the watchlist add box (Google-style typeahead)."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"results": []})
    cache_key = query.upper()

    now = time.time()
    with _symbol_search_lock:
        cached = _symbol_search_cache.get(cache_key)
        if cached and now - cached[1] < _SYMBOL_SEARCH_TTL:
            return jsonify({"results": cached[0]})

    try:
        quotes = yf.Search(query, max_results=8, news_count=0).quotes or []
    except Exception:
        # Don't cache failures — the next keystroke should retry.
        return jsonify({"results": []})

    results = []
    for quote in quotes:
        symbol = str(quote.get("symbol") or "").strip().upper()
        if not symbol or quote.get("quoteType") not in _SEARCHABLE_QUOTE_TYPES:
            continue
        results.append({
            "symbol": symbol,
            "name": quote.get("longname") or quote.get("shortname") or "",
            "exchange": quote.get("exchDisp") or "",
            "type": quote.get("typeDisp") or "",
        })

    with _symbol_search_lock:
        if len(_symbol_search_cache) >= _SYMBOL_SEARCH_MAX_ENTRIES:
            _symbol_search_cache.clear()
        _symbol_search_cache[cache_key] = (results, now)

    return jsonify({"results": results})


@app.route("/watchlist/add", methods=["POST"])
def watchlist_add():
    payload = request.get_json(silent=True) or request.form
    ticker = (payload.get("ticker") or "").strip().upper()
    shares = payload.get("shares")

    if not ticker:
        return jsonify({"ok": False, "error": "Ticker is required."}), 400

    # Validate the symbol by confirming a live quote exists. This rejects
    # garbage input (e.g. a full sentence) before it lands in the watchlist.
    try:
        fetch_live_quote(ticker)
    except Exception:
        return jsonify({"ok": False, "error": f"Couldn't find a quote for “{ticker}”."}), 400

    try:
        items = add_to_watchlist(ticker, shares)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Warm this ticker's logo cache once (network) so the cache-only payload
    # below returns its real brand mark on the very first render.
    try:
        logo_candidates_for_ticker(ticker, allow_network=True)
        with _logo_warm_lock:
            _logo_warm_seen.add(ticker)
    except Exception:
        pass

    return jsonify({"ok": True, "items": _watchlist_items_payload(items)})


@app.route("/watchlist/remove", methods=["POST"])
def watchlist_remove():
    payload = request.get_json(silent=True) or request.form
    ticker = (payload.get("ticker") or "").strip().upper()
    items = remove_from_watchlist(ticker)
    return jsonify({"ok": True, "items": _watchlist_items_payload(items)})


@app.route("/watchlist/clear", methods=["POST"])
def watchlist_clear():
    items = clear_watchlist()
    return jsonify({"ok": True, "items": _watchlist_items_payload(items)})


def build_result_context(result):
    """Convert a completed analysis result into the template's result-derived
    kwargs (cards, charts, trace). Shared by the synchronous POST path and the
    finished-job render path so both produce an identical dashboard."""
    context = {
        "chart_entries": [],
        "comparison_chart_path": None,
        "interactive_chart_entries": [],
        "interactive_comparison_chart": None,
        "llm_summaries": [],
        "metric_cards": [],
        "report_metric_cards": [],
        "fundamentals_cards": [],
        "earnings_cards": [],
        "analyst_cards": [],
        "news_cards": [],
        "comparison_result": None,
        "trace": None,
        "analyst_gauge": ANALYST_GAUGE,
    }
    if not result:
        return context

    memory = result.get("memory")
    tickers = result.get("tickers", [])
    context["trace"] = build_trace_view(result.get("trace"))
    if memory is None:
        return context

    # Collect per-ticker charts, metrics, and research cards
    brand_by_ticker = {}
    for ticker in tickers:
        is_crypto = is_crypto_symbol(ticker)
        chart_path = memory.get(f"{ticker}_chart_path")
        if chart_path:
            context["chart_entries"].append({"ticker": ticker, "path": chart_path})

        price_data = memory.get(f"{ticker}_data")
        period = result.get("period", "")
        metrics = memory.get(f"{ticker}_metrics", {}) or {}
        analyst_view = memory.get(f"{ticker}_analyst_view") or {}
        logo_url = analyst_view.get("logo_url") or logo_url_for_ticker(ticker)
        # Company brand hue, extracted from the logo, used to tint each card.
        brand_rgb = brand_color_for_ticker(ticker, logo_url)
        brand_by_ticker[ticker] = brand_rgb

        if price_data is not None:
            context["interactive_chart_entries"].append({
                "id": f"interactive-chart-{ticker}",
                "ticker": ticker,
                "logo_url": logo_url,
                "brand_rgb": brand_rgb,
                "figure_json": build_price_chart_json(price_data, ticker, period),
                "summary": build_chart_summary(price_data),
            })
        context["metric_cards"].append({
            "ticker": ticker,
            "logo_url": logo_url,
            "brand_rgb": brand_rgb,
            "total_return": format_percent(metrics.get("total_return")),
            "volatility": format_percent(metrics.get("volatility")),
            "sharpe_ratio": format_number(metrics.get("sharpe_ratio")),
        })
        report_card = build_report_metric_card(ticker, metrics, logo_url)
        report_card["brand_rgb"] = brand_rgb
        context["report_metric_cards"].append(report_card)

        if not is_crypto:
            analyst_card = build_analyst_card(analyst_view)
            if analyst_card:
                analyst_card["brand_rgb"] = brand_rgb
                context["analyst_cards"].append(analyst_card)

            fundamentals_card = build_fundamentals_card(
                memory.get(f"{ticker}_fundamentals") or {}, logo_url
            )
            if fundamentals_card:
                fundamentals_card["brand_rgb"] = brand_rgb
                context["fundamentals_cards"].append(fundamentals_card)

            earnings_card = build_earnings_card(
                memory.get(f"{ticker}_earnings") or {}, logo_url
            )
            if earnings_card:
                earnings_card["brand_rgb"] = brand_rgb
                context["earnings_cards"].append(earnings_card)

        ticker_news = memory.get(f"{ticker}_news", []) or []
        context["news_cards"].append({
            "ticker": ticker,
            "logo_url": logo_url,
            "brand_rgb": brand_rgb,
            "items": ticker_news[:3],
        })

    # Collect comparison chart if it exists
    context["comparison_chart_path"] = memory.get("comparison_chart_path")
    context["comparison_result"] = memory.get("comparison")
    if len(tickers) == 2:
        price_data_a = memory.get(f"{tickers[0]}_data")
        price_data_b = memory.get(f"{tickers[1]}_data")
        if price_data_a is not None and price_data_b is not None:
            context["interactive_comparison_chart"] = {
                "id": "interactive-comparison-chart",
                "brand_rgb_a": brand_by_ticker.get(tickers[0]),
                "brand_rgb_b": brand_by_ticker.get(tickers[1]),
                "figure_json": build_comparison_chart_json(
                    price_data_a, price_data_b, tickers[0], tickers[1], result.get("period", ""),
                ),
            }

    # Collect optional LLM summaries (tinted with the company's brand hue; the
    # comparison summary gets both hues split like the comparison chart).
    for ticker in tickers:
        llm_text = memory.get(f"{ticker}_llm_summary")
        if llm_text:
            summary_card = build_llm_summary_card(f"{ticker} AI Summary", llm_text)
            summary_card["brand_rgb"] = brand_by_ticker.get(ticker)
            context["llm_summaries"].append(summary_card)

    comparison_llm = memory.get("comparison_llm_summary")
    if comparison_llm:
        summary_card = build_llm_summary_card("Comparison AI Summary", comparison_llm)
        if len(tickers) == 2:
            summary_card["brand_rgb_a"] = brand_by_ticker.get(tickers[0])
            summary_card["brand_rgb_b"] = brand_by_ticker.get(tickers[1])
        context["llm_summaries"].append(summary_card)

    return context


# ── Background analysis jobs ──
# The execution trace streams while a run is in flight: the analysis runs in a
# background thread, its trace events are buffered here, and the browser polls
# for them. Job state lives in memory and is pruned by TTL — consistent with
# the app's single-instance design.
_jobs = {}
_jobs_lock = threading.Lock()
JOB_TTL_SECONDS = 1800


def _prune_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        for job_id in [jid for jid, job in _jobs.items() if job["created_at"] < cutoff]:
            _jobs.pop(job_id, None)


def _append_job_event(job_id, event):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["events"].append(event)


def _run_analysis_job(job_id, analysis_request):
    # Wire the tracer to stream each step into the job's live event buffer.
    tracer = AgentTracer(on_record=lambda event: _append_job_event(job_id, event))
    try:
        result = run_analysis_from_request(analysis_request, tracer=tracer)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["result"] = result
                job["status"] = "done"
    except Exception as exc:
        logging.exception("Background analysis job failed")
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["status"] = "error"
                job["error"] = str(exc)


@app.route("/api/analyze/start", methods=["POST"])
def analyze_start():
    payload = request.get_json(silent=True) or request.form
    user_input = (payload.get("user_input") or "").strip()
    requested_interval = (payload.get("interval") or "").strip()
    requested_summary = (payload.get("summary_mode") or "").strip()

    if not user_input:
        return jsonify({"ok": False, "error": "Please enter a request."}), 400

    analysis_request = build_request_with_controls(user_input, requested_interval, requested_summary)

    _prune_jobs()
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "events": [],
            "result": None,
            "error": None,
            "created_at": time.time(),
            "user_input": user_input,
            "interval": requested_interval if requested_interval in INTERVAL_PHRASES else "1y",
            "summary_mode": requested_summary if requested_summary in SUMMARY_PHRASES else "with_summary",
        }

    threading.Thread(target=_run_analysis_job, args=(job_id, analysis_request), daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/analyze/status/<job_id>")
def analyze_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"ok": False, "error": "Unknown or expired job."}), 404
        status = job["status"]
        error = job.get("error")
        events = [dict(event) for event in job["events"]]

    for event in events:
        event["duration_text"] = _format_duration(event.get("duration_ms"))
        event["tool_label"] = TOOL_LABELS.get(event["tool"], event["tool"])

    payload = {"ok": True, "status": status, "events": events}
    if status == "done":
        payload["redirect"] = url_for("index", job=job_id)
    elif status == "error":
        payload["error"] = error or "Analysis failed."
    return jsonify(payload)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    user_input = ""
    selected_interval = "1y"
    selected_summary = "with_summary"

    if request.method == "POST":
        # Synchronous fallback (used when JS is unavailable; the live-trace flow
        # uses /api/analyze/start instead).
        user_input = request.form.get("user_input", "").strip()
        requested_interval = request.form.get("interval", "").strip()
        requested_summary = request.form.get("summary_mode", "").strip()
        selected_interval = requested_interval if requested_interval in INTERVAL_PHRASES else "1y"
        selected_summary = requested_summary if requested_summary in SUMMARY_PHRASES else "with_summary"

        if not user_input:
            error = "Please enter a request."
        else:
            try:
                analysis_request = build_request_with_controls(
                    user_input, requested_interval, requested_summary,
                )
                result = run_analysis_from_request(analysis_request)
            except Exception as e:
                logging.exception("Analysis request failed")
                error = str(e)
    else:
        # A finished background job is rendered by id — the live-trace flow
        # navigates here once the run completes, reusing the stored result so
        # the analysis is never run twice.
        job_id = request.args.get("job", "").strip()
        if job_id:
            with _jobs_lock:
                job = _jobs.get(job_id)
                job_snapshot = dict(job) if job else None
            if job_snapshot is None:
                error = "That analysis has expired. Please run it again."
            elif job_snapshot["status"] == "error":
                error = job_snapshot.get("error") or "Analysis failed."
                user_input = job_snapshot.get("user_input", "")
            elif job_snapshot["status"] == "done" and job_snapshot.get("result"):
                result = job_snapshot["result"]
                user_input = job_snapshot.get("user_input", "")
                selected_interval = job_snapshot.get("interval", "1y")
                selected_summary = job_snapshot.get("summary_mode", "with_summary")

    result_context = build_result_context(result)

    recent_runs = load_recent_history(limit=5)
    for run in recent_runs:
        run["display_time"] = format_history_timestamp(run.get("timestamp"))

    return render_template(
        "index.html",
        result=result,
        error=error,
        user_input=user_input,
        selected_interval=selected_interval,
        selected_summary=selected_summary,
        interval_options=INTERVAL_OPTIONS,
        summary_options=SUMMARY_OPTIONS,
        recent_runs=recent_runs,
        **result_context,
    )

if __name__ == "__main__":
    # threaded=True so a slow request (e.g. a first-time logo probe) can never
    # block the live-quote endpoints that poll every few seconds.
    app.run(debug=True, threaded=True)
