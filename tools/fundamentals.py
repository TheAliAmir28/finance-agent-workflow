import yfinance as yf


def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dividend_yield_as_ratio(info):
    dividend_rate = _as_float(info.get("dividendRate"))
    current_price = _as_float(info.get("currentPrice")) or _as_float(info.get("regularMarketPrice"))

    if dividend_rate is not None and current_price not in (None, 0):
        return dividend_rate / current_price

    dividend_yield = _as_float(info.get("dividendYield"))
    if dividend_yield is None:
        return None

    # Some yfinance quote fields return percent points, e.g. 0.35 for 0.35%.
    # The dashboard/report formatters expect decimal ratios, e.g. 0.0035.
    if dividend_yield >= 0.1:
        return dividend_yield / 100

    return dividend_yield


def fetch_company_fundamentals(ticker):
    """
    Fetch company and valuation fundamentals from yfinance.
    Missing fields are returned as None so callers can render N/A cleanly.
    """
    symbol = ticker.upper()

    try:
        info = yf.Ticker(symbol).get_info() or {}
    except Exception as exc:
        return {
            "ticker": symbol,
            "available": False,
            "error": str(exc),
        }

    fundamentals = {
        "ticker": symbol,
        "available": True,
        "company_name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": _as_float(info.get("marketCap")),
        "pe_ratio": _as_float(info.get("trailingPE")) or _as_float(info.get("forwardPE")),
        "revenue_growth": _as_float(info.get("revenueGrowth")),
        "eps": _as_float(info.get("trailingEps")),
        "dividend_yield": _dividend_yield_as_ratio(info),
    }

    key_values = [
        fundamentals["company_name"],
        fundamentals["sector"],
        fundamentals["market_cap"],
        fundamentals["pe_ratio"],
        fundamentals["revenue_growth"],
        fundamentals["eps"],
        fundamentals["dividend_yield"],
    ]
    fundamentals["available"] = any(value is not None for value in key_values)

    return fundamentals
