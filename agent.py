from tools.data_fetch import fetch_price_history
from tools.metrics import compute_all_metrics, compare_metrics
from pathlib import Path
from tools.charts import plot_close_price_line, plot_comparison_normalized
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

                try:
                    # Pull price history from the data source
                    price_data = fetch_price_history(ticker, period)
                    # Store successful results in memory
                    self.memory.set(f"{ticker}_data", price_data)
                    self.memory.set(f"{ticker}_status", "ok")
                    self.memory.set(f"{ticker}_period", period)
                except Exception as e:
                    # Mark ticker as have failed. This allows later steps to safely skip it
                    self.memory.set(f"{ticker}_status", "error")
                    self.memory.set(f"{ticker}_error", str(e))

            # Task: compute metrics + build chart
            elif task["task"] == "compute_metrics":
                ticker = task["ticker"]
                 # Only continue if data was fetched successfully
                status = self.memory.get(f"{ticker}_status")
                if status != "ok":
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
            
            # Task: compare two stocks
            elif task["task"] == "compare_metrics":
                # Find tickers that have computed metrics
                metric_keys = [key for key in self.memory._store.keys() if key.endswith("_metrics")]
                # We can only compare exactly two tickers
                if len(metric_keys) != 2:
                    self.memory.set("comparison_error", "Comparison could not be performed because one or more tickers were invalid.")
                    continue
                # Extract ticker symbols from memory keys
                ticker_a = metric_keys[0].replace("_metrics", "")
                ticker_b = metric_keys[1].replace("_metrics", "")
                # Load metrics for both stocks
                metrics_a = self.memory.get(f"{ticker_a}_metrics")
                metrics_b = self.memory.get(f"{ticker_b}_metrics")
                # Compare metrics (return, Sharpe, etc.)
                comparison = compare_metrics(metrics_a, metrics_b, ticker_a, ticker_b)
                self.memory.set("comparison", comparison)

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