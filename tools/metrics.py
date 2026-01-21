# Compute daily percentage returns from closing price data.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_daily_returns(price_data):
    # Select the closing price, then compute percent change from previous row 
    daily_returns = price_data["Close"].pct_change()
    return daily_returns

# Compute total return over the entire period.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_total_return(price_data):
    # First closing price
    start_price = price_data["Close"].iloc[0]
    # Last closing price
    end_price = price_data["Close"].iloc[-1]

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

# Compute all relevant metrics for a stock.
# price_data (pandas.DataFrame): DataFrame with a 'Close' column
def compute_all_metrics(price_data):

    daily_returns = compute_daily_returns(price_data)
    total_return = compute_total_return(price_data)
    volatility = compute_volatility(daily_returns)
    sharpe_ratio = compute_sharpe_ratio(daily_returns)  

    metrics = {"total_return" : total_return, "volatility" : volatility, "sharpe_ratio" : sharpe_ratio}

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
