from __future__ import annotations

import io
import json
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yfinance as yf
from tools.crypto import crypto_domain, is_crypto_symbol


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


# ── Logo domain resolution ──────────────────────────────────────────────────
# Resolving a company's website via yfinance is slow, so the ticker→domain
# mapping is cached on disk (domains essentially never change). A blank string
# is cached for tickers with no known website, so we don't re-query them.
_LOGO_CACHE_PATH = Path("output") / "logo_cache.json"
_logo_cache = None
_logo_cache_lock = threading.Lock()


def _load_logo_cache():
    global _logo_cache
    if _logo_cache is None:
        try:
            with open(_LOGO_CACHE_PATH, "r", encoding="utf-8") as f:
                _logo_cache = json.load(f)
        except Exception:
            _logo_cache = {}
    return _logo_cache


def _save_logo_cache():
    try:
        _LOGO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOGO_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_logo_cache, f, indent=2, sort_keys=True)
    except Exception:
        pass


def _fetch_website_domain(symbol):
    """Look up the company's website via yfinance and return its bare domain."""
    try:
        info = yf.Ticker(symbol).get_info() or {}
    except Exception:
        return None
    website = info.get("website") or info.get("irWebsite")
    return _domain_from_website(website) if website else None


def resolve_logo_domain(ticker, website=None, allow_network=True):
    """Best-effort company domain for a ticker, used to build logo URLs.

    Order: explicit website → curated map → crypto → disk cache → yfinance.
    Results (including misses) are cached so each ticker is resolved at most
    once over the network.
    """
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return None

    if website:
        explicit = _domain_from_website(website)
        if explicit:
            return explicit

    if symbol in TICKER_TO_DOMAIN:
        return TICKER_TO_DOMAIN[symbol]

    crypto = crypto_domain(symbol)
    if crypto:
        return crypto

    cache = _load_logo_cache()
    if symbol in cache:
        return cache[symbol] or None

    if not allow_network:
        return None

    domain = _fetch_website_domain(symbol)
    with _logo_cache_lock:
        cache[symbol] = domain or ""   # cache misses too, to avoid re-querying
        _save_logo_cache()
    return domain


def logo_candidates_for_domain(domain):
    """Ordered logo URLs for a domain, highest quality first.

    (Clearbit's logo API was discontinued, so it is intentionally not used.)
    """
    if not domain:
        return []
    return [
        # DuckDuckGo serves the site's apple-touch-icon — a real, high-res
        # brand mark — and resolves reliably across obscure domains.
        f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        # Google favicon: lower-fidelity but an extremely reliable fallback.
        f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
    ]


# ── FMP stock-logo verification ──────────────────────────────────────────────
# The ticker-keyed stock-logo service returns the highest-quality brand logos,
# but for tickers it has no art for it serves a *blank* (white/transparent) PNG
# with a 200 status. A blank image loads fine, so the browser's onerror never
# fires and the user is left with an invisible logo (e.g. UBER). We probe each
# ticker's logo once, detect blanks, and cache the verdict so a blank source is
# dropped from the candidate list instead of silently winning.
_FMP_LOGO_URL = "https://financialmodelingprep.com/image-stock/{symbol}.png"
_FMP_CACHE_PATH = Path("output") / "fmp_logo_cache.json"
_fmp_cache = None
_fmp_cache_lock = threading.Lock()


def _load_fmp_cache():
    global _fmp_cache
    if _fmp_cache is None:
        try:
            with open(_FMP_CACHE_PATH, "r", encoding="utf-8") as f:
                _fmp_cache = json.load(f)
        except Exception:
            _fmp_cache = {}
    return _fmp_cache


def _save_fmp_cache():
    try:
        _FMP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_FMP_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_fmp_cache, f, indent=2, sort_keys=True)
    except Exception:
        pass


def _image_is_blank(data):
    """True if image bytes are an effectively empty placeholder.

    Catches fully-transparent images and ones whose every visible pixel is
    near-white — the shape FMP's "no logo" placeholder takes. If the image
    can't be decoded (e.g. Pillow missing), err toward keeping the logo.
    """
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGBA").resize((32, 32))
    except Exception:
        return False

    visible = [(r, g, b) for (r, g, b, a) in im.getdata() if a > 16]
    if not visible:
        return True
    return all(r > 244 and g > 244 and b > 244 for r, g, b in visible)


def _fmp_logo_is_real(symbol, allow_network=True):
    """Whether FMP serves a real (non-blank) logo for this ticker, cached."""
    cache = _load_fmp_cache()
    if symbol in cache:
        return cache[symbol]
    if not allow_network:
        return True   # unknown — don't suppress a logo we haven't checked

    try:
        req = urllib.request.Request(
            _FMP_LOGO_URL.format(symbol=symbol),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            real = resp.status == 200 and not _image_is_blank(resp.read())
    except Exception:
        return True   # transient failure — leave it unjudged, retry next time

    with _fmp_cache_lock:
        cache[symbol] = real
        _save_fmp_cache()
    return real


def logo_candidates_for_ticker(ticker, website=None, allow_network=True):
    """Ordered list of logo URLs to try for a ticker (best quality first).

    For equities, a ticker-keyed stock-logo service is preferred: it returns
    consistently high-resolution brand logos (100–250px) and works even for
    tickers yfinance has no website for — but only when it actually has art,
    so blank placeholders are filtered out. Domain-based favicons follow as
    fallbacks. Crypto (no stock logo) uses the domain-based sources directly.
    """
    symbol = str(ticker or "").strip().upper()
    domain_candidates = logo_candidates_for_domain(
        resolve_logo_domain(symbol, website, allow_network)
    )
    if symbol and not is_crypto_symbol(symbol) and _fmp_logo_is_real(symbol, allow_network):
        return [
            f"https://financialmodelingprep.com/image-stock/{symbol}.png",
            *domain_candidates,
        ]
    return domain_candidates


def logo_url_for_ticker(ticker, website=None):
    """Single best logo URL — the highest-quality source verified to exist.

    Returns the first candidate from the same chain the watchlist uses, so a
    plain <img> tag gets the real brand logo (e.g. Google's "G", not Alphabet's
    generic favicon) and never a known-blank placeholder.
    """
    candidates = logo_candidates_for_ticker(ticker, website)
    return candidates[0] if candidates else None


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
