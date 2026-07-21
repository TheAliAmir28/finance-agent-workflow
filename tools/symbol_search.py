"""Shared Yahoo symbol lookup with a small TTL cache.

Used by the /api/symbol-search typeahead route and the LLM agent's
resolve_symbol tool, so both stay behind one throttle-friendly cache.
"""

import threading
import time

import yfinance as yf

_TTL_SECONDS = 600
_MAX_ENTRIES = 500
_cache = {}
_lock = threading.Lock()

# Quote types that make sense here; filters out options, futures, etc.
SEARCHABLE_QUOTE_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY", "INDEX", "MUTUALFUND"}


def search_symbols(query, max_results=8):
    """Return [{symbol, name, exchange, type}] for a free-text query."""
    query = str(query or "").strip()
    if not query:
        return []
    cache_key = query.upper()

    now = time.time()
    with _lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[1] < _TTL_SECONDS:
            return cached[0]

    try:
        quotes = yf.Search(query, max_results=max_results, news_count=0).quotes or []
    except Exception:
        # Don't cache failures — the next call should retry.
        return []

    results = []
    for quote in quotes:
        symbol = str(quote.get("symbol") or "").strip().upper()
        if not symbol or quote.get("quoteType") not in SEARCHABLE_QUOTE_TYPES:
            continue
        results.append({
            "symbol": symbol,
            "name": quote.get("longname") or quote.get("shortname") or "",
            "exchange": quote.get("exchDisp") or "",
            "type": quote.get("typeDisp") or "",
        })

    with _lock:
        if len(_cache) >= _MAX_ENTRIES:
            _cache.clear()
        _cache[cache_key] = (results, now)
    return results
