import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
from tools.crypto import normalize_crypto_symbol

# Cache settings
CACHE_DIR = Path("output") / "cache" # This is the folder where cached price data lives
CACHE_MAX_AGE_SECONDS = 60 * 60 * 24  # This means 24 hours. 

def _safe_cache_part(value):
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)

# If the user asks for AAPL and 1y, this returns 'output/cache/AAPL_1y.csv'
def _get_cache_path(ticker, period):
    ticker = ticker.upper()
    safe_period = _safe_cache_part(period)
    return CACHE_DIR / f"{ticker}_{safe_period}.csv"

#Checks if the file exists and is younger than 24 hours
def _is_cache_fresh(cache_path):
    if not cache_path.exists():
        return False

    file_age_seconds = time.time() - cache_path.stat().st_mtime
    return file_age_seconds < CACHE_MAX_AGE_SECONDS

def _clean_close_prices(price_data):
    close_prices = price_data[["Close"]].copy()
    close_prices.index = pd.to_datetime(close_prices.index, errors="coerce", utc=True).tz_localize(None)
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
    cache_path = _get_cache_path(yahoo_symbol, period)

    # Use cached data if it exists and is still fresh
    if _is_cache_fresh(cache_path):
        cached_data = pd.read_csv(cache_path, index_col=0, parse_dates=True)

        if cached_data.empty or "Close" not in cached_data.columns:
            raise ValueError(f"Cached data for ticker {ticker} is invalid.")

        return _clean_close_prices(cached_data)

    # Otherwise fetch fresh data from Yahoo Finance
    stock = yf.Ticker(yahoo_symbol)
    if start_date and end_date:
        # yfinance treats end as exclusive; user-facing custom ranges are inclusive.
        exclusive_end = (
            datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()
        history = stock.history(start=start_date, end=exclusive_end, interval="1d")
    else:
        history = stock.history(period=period, interval="1d")

    if history.empty:
        raise ValueError(f"No data found for ticker: {ticker}")

    close_prices = _clean_close_prices(history)
    close_prices.to_csv(cache_path)

    return close_prices



