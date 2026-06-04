from tools.data_fetch import fetch_price_history
from tools.metrics import compute_all_metrics, compare_metrics
from pathlib import Path
from tools.charts import plot_close_price_line, plot_comparison_normalized
from tools.analyst import fetch_analyst_view
from tools.earnings import fetch_earnings_snapshot
from tools.fundamentals import fetch_company_fundamentals
from tools.news import fetch_stock_news
from tools.crypto import is_crypto_symbol
import logging
"""
The Agent is responsible for actually doing the work.

It takes a list of tasks produced by the planner and
executes them one by one, storing results in shared memory.
"""
class Agent:
    def __init__(self, memory):
        # Shared memory object used to store data between steps
        self.memory = memory
    
    # Execute a list of tasks in order.
    def run(self, tasks):
        # Go through each task one at a time
        for task in tasks:
            # Task: fetch historical price data
            if task["task"] == "fetch_data":
                ticker = task["ticker"]
                period = task["period"]
                start_date = task.get("start_date")
                end_date = task.get("end_date")

                try:
                    # Pull price history from the data source
                    price_data = fetch_price_history(ticker, period, start_date, end_date)
                    # Store successful results in memory
                    self.memory.set(f"{ticker}_data", price_data)
                    self.memory.set(f"{ticker}_status", "ok")
                    self.memory.set(f"{ticker}_period", period)
                    logging.info(f"Fetched data for {ticker} ({period})")
                except Exception as e:
                    # Mark ticker as have failed. This allows later steps to safely skip it
                    self.memory.set(f"{ticker}_status", "error")
                    self.memory.set(f"{ticker}_error", str(e))
                    logging.error(f"Failed to fetch data for {ticker}: {e}")

            # Task: compute metrics + build chart
            elif task["task"] == "compute_metrics":
                ticker = task["ticker"]
                 # Only continue if data was fetched successfully
                status = self.memory.get(f"{ticker}_status")
                if status != "ok":
                    logging.warning(f"Skipping metric computation for {ticker} because data fetch failed.")
                    continue

                price_data = self.memory.get(f"{ticker}_data")
                # Compute return, volatility, Sharpe ratio, etc.
                metrics = compute_all_metrics(price_data)
                # Folder where charts are saved
                charts_dir = Path("output") / "charts"
                period = self.memory.get(f"{ticker}_period", "unknown")
                # Build and save the price chart
                chart_path = plot_close_price_line(price_data, ticker, period, charts_dir)
                 # Save chart path so reports and dashboard can use it
                self.memory.set(f"{ticker}_chart_path", str(chart_path.resolve()))

                self.memory.set(f"{ticker}_metrics", metrics)
                logging.info(f"Computed metrics and chart for {ticker}")

                if is_crypto_symbol(ticker):
                    self.memory.set(f"{ticker}_analyst_view", {"ticker": ticker, "available": False})
                    self.memory.set(f"{ticker}_fundamentals", {"ticker": ticker, "available": False})
                    self.memory.set(f"{ticker}_earnings", {"ticker": ticker, "available": False})
                else:
                    try:
                        latest_close = price_data["Close"].iloc[-1]
                        analyst_view = fetch_analyst_view(ticker, latest_close)
                        self.memory.set(f"{ticker}_analyst_view", analyst_view)
                        logging.info(f"Fetched analyst view for {ticker}")
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_analyst_view",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Analyst view unavailable for {ticker}: {e}")

                    try:
                        fundamentals = fetch_company_fundamentals(ticker)
                        self.memory.set(f"{ticker}_fundamentals", fundamentals)
                        logging.info(f"Fetched fundamentals for {ticker}")
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_fundamentals",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Fundamentals unavailable for {ticker}: {e}")

                    try:
                        earnings = fetch_earnings_snapshot(ticker)
                        self.memory.set(f"{ticker}_earnings", earnings)
                        logging.info(f"Fetched earnings snapshot for {ticker}")
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_earnings",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Earnings unavailable for {ticker}: {e}")

                try:
                    news_items = fetch_stock_news(ticker, limit=3)
                    self.memory.set(f"{ticker}_news", news_items)
                    logging.info(f"Fetched news for {ticker}")
                except Exception as e:
                    self.memory.set(f"{ticker}_news", [])
                    logging.warning(f"News unavailable for {ticker}: {e}")
            
            # Task: compare two stocks
            elif task["task"] == "compare_metrics":
                # Find tickers that have computed metrics
                metric_keys = [key for key in self.memory.keys() if key.endswith("_metrics")]
                # We can only compare exactly two tickers
                if len(metric_keys) != 2:
                    raise ValueError("Comparison requires exactly two valid tickers.")
                # Extract ticker symbols from memory keys
                ticker_a = metric_keys[0].replace("_metrics", "")
                ticker_b = metric_keys[1].replace("_metrics", "")
                # Load metrics for both stocks
                metrics_a = self.memory.get(f"{ticker_a}_metrics")
                metrics_b = self.memory.get(f"{ticker_b}_metrics")
                # Compare metrics (return, Sharpe, etc.)
                comparison = compare_metrics(metrics_a, metrics_b, ticker_a, ticker_b)
                self.memory.set("comparison", comparison)
                logging.info(f"Created comparison for {ticker_a} vs {ticker_b}")

                # Build comparison chart
                price_data_a = self.memory.get(f"{ticker_a}_data")
                price_data_b = self.memory.get(f"{ticker_b}_data")
                # Use the same period for both stocks
                period = self.memory.get(f"{ticker_a}_period", "unknown")
                charts_dir = Path("output") / "charts"
                # Create comparison chart
                compare_chart_path = plot_comparison_normalized(
                    price_data_a,
                    price_data_b,
                    ticker_a,
                    ticker_b,
                    period,
                    charts_dir,
                )

                # Store chart path so HTML dashboard can display it
                self.memory.set("comparison_chart_path", str(compare_chart_path.resolve()))
                logging.info(f"Saved comparison chart for {ticker_a} vs {ticker_b}")
