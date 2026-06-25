import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time
from tools.crypto import normalize_crypto_symbol, is_crypto_symbol

# Cache settings
CACHE_DIR = Path("output") / "cache" # This is the folder where cached price data lives
CACHE_MAX_AGE_SECONDS = 60 * 60 * 24  # 24 hours for standard periods


def _bar_interval_for_period(period):
    """Return the yfinance bar interval appropriate for the requested period."""
    if period == "1d":
        return "5m"   # ~78 five-minute bars — high-resolution intraday view
    if period == "5d":
        return "1h"   # ~35 hourly bars — clean weekly intraday view
    return "1d"


def _cache_max_age_seconds(period, is_crypto=False):
    """Intraday data goes stale quickly; use a shorter TTL for short periods."""
    if period == "1d":
        return 60 * 10    # 10 minutes
    if period == "5d":
        return 60 * 30    # 30 minutes
    if is_crypto:
        return 60 * 60    # rolling 24/7 windows should not sit stale all day
    return CACHE_MAX_AGE_SECONDS

def _safe_cache_part(value):
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)

# If the user asks for AAPL and 1y, this returns 'output/cache/AAPL_1y.csv'
def _get_cache_path(ticker, period):
    ticker = ticker.upper()
    safe_period = _safe_cache_part(period)
    return CACHE_DIR / f"{ticker}_{safe_period}.csv"

def _is_cache_fresh(cache_path, period="", is_crypto=False):
    if not cache_path.exists():
        return False
    file_age_seconds = time.time() - cache_path.stat().st_mtime
    return file_age_seconds < _cache_max_age_seconds(period, is_crypto)


def _rolling_period_bounds(period, now=None):
    """Return UTC start/end datetimes for app-relative periods."""
    now = now or datetime.now(timezone.utc)
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")

    value = period[:-1]
    if period.endswith("mo") and period[:-2].isdigit():
        start_ts = now_ts - pd.DateOffset(months=int(period[:-2]))
    elif period.endswith("d") and value.isdigit():
        start_ts = now_ts - pd.Timedelta(days=int(value))
    elif period.endswith("y") and value.isdigit():
        start_ts = now_ts - pd.DateOffset(years=int(value))
    else:
        return None

    return start_ts.to_pydatetime(), now_ts.to_pydatetime()


def _clip_to_rolling_period(price_data, period, now=None):
    bounds = _rolling_period_bounds(period, now=now)
    if not bounds:
        return price_data

    start_dt, end_dt = bounds
    idx = pd.to_datetime(price_data.index, errors="coerce", utc=True)
    mask = (idx >= pd.Timestamp(start_dt)) & (idx <= pd.Timestamp(end_dt))
    clipped = price_data.loc[mask].copy()
    return clipped if not clipped.empty else price_data

def _clean_close_prices(price_data):
    close_prices = price_data[["Close"]].copy()
    idx = pd.to_datetime(close_prices.index, errors="coerce")
    # Strip timezone if present; preserve the actual timestamp values as-is.
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    close_prices.index = idx
    close_prices["Close"] = pd.to_numeric(close_prices["Close"], errors="coerce")
    close_prices = close_prices.dropna(subset=["Close"])
    close_prices = close_prices[~close_prices.index.isna()]

    if close_prices.empty:
        raise ValueError("Price data did not include valid numeric close prices.")

    return close_prices

# Fetch historical price data for a given stock ticker.
def fetch_price_history(ticker, period, start_date=None, end_date=None):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yahoo_symbol = normalize_crypto_symbol(ticker)
    is_crypto = is_crypto_symbol(yahoo_symbol)
    cache_path = _get_cache_path(yahoo_symbol, period)

    # Use cached data if it exists and is still fresh
    if _is_cache_fresh(cache_path, period, is_crypto):
        cached_data = pd.read_csv(cache_path, index_col=0, parse_dates=True)

        if cached_data.empty or "Close" not in cached_data.columns:
            raise ValueError(f"Cached data for ticker {ticker} is invalid.")

        cached_data = _clean_close_prices(cached_data)
        if is_crypto and not (start_date and end_date):
            cached_data = _clip_to_rolling_period(cached_data, period)
        return cached_data

    # Otherwise fetch fresh data from Yahoo Finance
    stock = yf.Ticker(yahoo_symbol)
    if start_date and end_date:
        # yfinance treats end as exclusive; user-facing custom ranges are inclusive.
        exclusive_end = (
            datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()
        history = stock.history(start=start_date, end=exclusive_end, interval="1d")
    elif is_crypto:
        bar_interval = _bar_interval_for_period(period)
        bounds = _rolling_period_bounds(period)
        if bounds:
            start_dt, end_dt = bounds
            history = stock.history(
                start=start_dt,
                end=end_dt + timedelta(minutes=1),
                interval=bar_interval,
            )
            history = _clip_to_rolling_period(history, period, now=end_dt)
        else:
            history = stock.history(period=period, interval=bar_interval)
    else:
        bar_interval = _bar_interval_for_period(period)
        history = stock.history(period=period, interval=bar_interval)

    if history.empty:
        raise ValueError(f"No data found for ticker: {ticker}")

    # For intraday periods, normalise timestamps before caching.
    # Stocks  → convert to US/Eastern so "09:30" renders as 9:30 AM, not 2:30 PM UTC.
    # Crypto  → strip tz only, keep UTC values; 24/7 markets are naturally UTC-based.
    if period in ("1d", "5d"):
        try:
            if is_crypto:
                if history.index.tz is not None:
                    history.index = history.index.tz_localize(None)
            else:
                if history.index.tz is not None:
                    history.index = history.index.tz_convert("America/New_York").tz_localize(None)
                else:
                    history.index = (
                        history.index.tz_localize("UTC")
                        .tz_convert("America/New_York")
                        .tz_localize(None)
                    )
        except Exception:
            pass  # fall back to whatever timezone the index already has

    close_prices = _clean_close_prices(history)
    close_prices.to_csv(cache_path)

    return close_prices



