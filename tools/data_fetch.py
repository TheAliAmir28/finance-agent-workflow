import yfinance as yf

# Fetch historical price data for a given stock ticker.
def fetch_price_history(ticker, period):
    # Create handle for the stock
    stock = yf.Ticker(ticker);
    # Fetch historical data as a pandas DataFrame
    history =  stock.history(period=period, interval="1d")

    if history.empty:
        raise ValueError(f"No data found for ticker: {ticker}")

    close_prices = history[["Close"]]
    return close_prices



