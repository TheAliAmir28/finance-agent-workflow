from __future__ import annotations

import yfinance as yf
from urllib.parse import urlparse
from tools.crypto import crypto_domain


RECOMMENDATION_LABELS = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "sell": "Sell",
    "strong_sell": "Strong Sell",
}

TICKER_TO_DOMAIN = {
    "AAPL": "apple.com",
    "AMAT": "amat.com",
    "AMD": "amd.com",
    "AMZN": "amazon.com",
    "COST": "costco.com",
    "GOOGL": "abc.xyz",
    "META": "meta.com",
    "MSFT": "microsoft.com",
    "MU": "micron.com",
    "NFLX": "netflix.com",
    "NVDA": "nvidia.com",
    "PLTR": "palantir.com",
    "QXO": "qxo.com",
    "TSLA": "tesla.com",
    "WMT": "walmart.com",
}


def _format_recommendation(value):
    if not value:
        return "Unavailable"

    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return RECOMMENDATION_LABELS.get(normalized, str(value).strip().title())


def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _domain_from_website(website):
    parsed = urlparse(str(website))
    domain = parsed.netloc or parsed.path
    domain = domain.lower().removeprefix("www.").strip("/")

    if not domain or "." not in domain:
        return None

    return domain


def logo_url_for_ticker(ticker, website=None):
    domain = _domain_from_website(website) if website else None
    domain = domain or crypto_domain(ticker) or TICKER_TO_DOMAIN.get(ticker.upper())

    if not domain:
        return None

    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def fetch_analyst_view(ticker, latest_close=None):
    """
    Fetch analyst recommendation and price-target data when yfinance provides it.
    Returns a small, presentation-ready dictionary and never raises for missing
    analyst data.
    """
    symbol = ticker.upper()
    latest_close = _as_float(latest_close)

    try:
        info = yf.Ticker(symbol).get_info() or {}
    except Exception as exc:
        return {
            "ticker": symbol,
            "available": False,
            "logo_url": logo_url_for_ticker(symbol),
            "error": str(exc),
        }

    recommendation = _format_recommendation(info.get("recommendationKey"))
    website = info.get("website")
    analyst_count = info.get("numberOfAnalystOpinions")
    target_mean = _as_float(info.get("targetMeanPrice"))
    target_low = _as_float(info.get("targetLowPrice"))
    target_high = _as_float(info.get("targetHighPrice"))
    current_price = _as_float(info.get("currentPrice")) or latest_close

    upside = None
    if target_mean is not None and current_price not in (None, 0):
        upside = (target_mean / current_price) - 1

    available = any(
        value not in (None, "Unavailable")
        for value in (recommendation, analyst_count, target_mean, target_low, target_high)
    )

    return {
        "ticker": symbol,
        "available": available,
        "recommendation": recommendation,
        "website": website,
        "logo_url": logo_url_for_ticker(symbol, website),
        "analyst_count": analyst_count,
        "target_mean": target_mean,
        "target_low": target_low,
        "target_high": target_high,
        "current_price": current_price,
        "upside": upside,
    }
