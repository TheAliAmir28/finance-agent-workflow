import math
import pandas as pd

def _close_series(price_data):
    close = pd.to_numeric(price_data["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("Price data did not include valid numeric close prices.")
    return close

# Compute daily percentage returns from closing price data.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_daily_returns(price_data):
    # Select the closing price, then compute percent change from previous row 
    daily_returns = _close_series(price_data).pct_change()
    return daily_returns

# Compute total return over the entire period.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_total_return(price_data):
    # First closing price
    close = _close_series(price_data)
    start_price = close.iloc[0]
    # Last closing price
    end_price = close.iloc[-1]

    total_return = (end_price - start_price) / start_price
    return total_return

# Compute volatility as the standard deviation of daily returns.
# daily_returns (pandas.Series): Daily returns
def compute_volatility(daily_returns):
    # Daily returns are already computed once so we avoid duplicated logic 
    volatility = daily_returns.std()
    return volatility

# Compute a simplified Sharpe-like ratio.
# daily_returns (pandas.Series): Daily returns
def compute_sharpe_ratio(daily_returns):
    # Average daily return
    mean_return = daily_returns.mean()
    # Volatility
    volatility = daily_returns.std()
    # Zero-check
    if volatility == 0:
        return None
    
    sharpe_ratio = mean_return / volatility
    return sharpe_ratio

# Makes Sharpe ratio more realistic by annualizing it.
# daily_returns (pandas.Series): Daily returns
def compute_annualized_volatility(daily_returns):
    daily_volatility = daily_returns.std()
    annualized_volatility = daily_volatility * math.sqrt(252)
    return annualized_volatility


# Takes daily volatility and scales it up to a yearly estimate.
# daily_returns (pandas.Series): Daily returns
def compute_annualized_sharpe_ratio(daily_returns, risk_free_rate=0.0):
    mean_daily_return = daily_returns.mean()
    daily_volatility = daily_returns.std()

    if daily_volatility == 0:
        return None

    annualized_sharpe = ((mean_daily_return - risk_free_rate / 252) / daily_volatility) * math.sqrt(252)
    return annualized_sharpe


# Measures the yearly compound growth rate over the period.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column and datetime index
def compute_cagr(price_data):
    close = _close_series(price_data)
    start_price = close.iloc[0]
    end_price = close.iloc[-1]

    dates = pd.to_datetime(price_data.index, errors="coerce", utc=True).tz_localize(None)
    dates = dates[~pd.isna(dates)]
    if len(dates) < 2:
        return None

    num_days = (dates[-1] - dates[0]).days
    if num_days <= 0:
        return None

    num_years = num_days / 365.25
    if num_years <= 0:
        return None

    cagr = (end_price / start_price) ** (1 / num_years) - 1
    return cagr


# Finds the worst drop from a previous peak.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_max_drawdown(price_data):
    close = _close_series(price_data)
    running_max = close.cummax()
    drawdowns = (close - running_max) / running_max
    max_drawdown = drawdowns.min()
    return max_drawdown


# Returns the latest 20-day and 50-day moving averages
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_moving_averages(price_data):
    close = _close_series(price_data)
    ma_20_series = close.rolling(window=20).mean()
    ma_50_series = close.rolling(window=50).mean()

    ma_20 = ma_20_series.iloc[-1] if len(ma_20_series) > 0 else None
    ma_50 = ma_50_series.iloc[-1] if len(ma_50_series) > 0 else None

    # Convert NaN to None for cleaner downstream handling
    if ma_20 != ma_20:
        ma_20 = None
    if ma_50 != ma_50:
        ma_50 = None

    return {"ma_20": ma_20, "ma_50": ma_50}

# Compute all relevant metrics for a stock.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_all_metrics(price_data):
    daily_returns = compute_daily_returns(price_data)

    total_return = compute_total_return(price_data)
    volatility = compute_volatility(daily_returns)
    sharpe_ratio = compute_sharpe_ratio(daily_returns)

    annualized_volatility = compute_annualized_volatility(daily_returns)
    annualized_sharpe_ratio = compute_annualized_sharpe_ratio(daily_returns)
    cagr = compute_cagr(price_data)
    max_drawdown = compute_max_drawdown(price_data)
    moving_averages = compute_moving_averages(price_data)

    metrics = {
        "total_return": total_return,
        "volatility": volatility,
        "sharpe_ratio": sharpe_ratio,
        "annualized_volatility": annualized_volatility,
        "annualized_sharpe_ratio": annualized_sharpe_ratio,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "ma_20": moving_averages["ma_20"],
        "ma_50": moving_averages["ma_50"],
    }

    return metrics 

# Compare metrics for two stocks and determine a winner.
def compare_metrics(metrics_a, metrics_b, ticker_a, ticker_b):
    sharpe_a = metrics_a.get("sharpe_ratio")
    sharpe_b = metrics_b.get("sharpe_ratio")

    # Primary winner determinator - sharpe ratio
    if sharpe_a is not None and sharpe_b is not None:
        if sharpe_a > sharpe_b:
            winner = ticker_a
            reason = "Higher risk-adjusted return (Sharpe ratio)"
        elif sharpe_b > sharpe_a:
            winner = ticker_b
            reason = "Higher risk-adjusted return (Sharpe ratio)"
        else:
            winner = None
            reason = "Equal risk-adjusted performance"
    elif sharpe_a is not None:
        winner = ticker_a
        reason = "Valid Sharpe ratio while the other is undefined"
    elif sharpe_b is not None:
        winner = ticker_b
        reason = "Valid Sharpe ratio while the other is undefined"
    else:
        winner = None
        reason = "Sharpe ratio unavailable for both stocks"

    # Secondary winner determinator - total return
    if winner is None:
        return_a = metrics_a.get("total_return")
        return_b = metrics_b.get("total_return")

        if return_a > return_b:
            winner = ticker_a
            reason = "Higher total return"
        elif return_b > return_a:
            winner = ticker_b
            reason = "Higher total return"
        else:
            winner = "Tie"
            reason = "Both stocks performed equally"
    
    comparison = {"winner": winner, "reason": reason, "metrics_compared": {ticker_a: metrics_a, ticker_b: metrics_b}}

    return comparison
