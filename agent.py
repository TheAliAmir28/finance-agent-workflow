from tools.data_fetch import fetch_price_history
from tools.metrics import compute_all_metrics, compare_metrics
from pathlib import Path
from tools.charts import plot_close_price_line, plot_comparison_normalized
from tools.analyst import fetch_analyst_view
from tools.earnings import fetch_earnings_snapshot
from tools.fundamentals import fetch_company_fundamentals
from tools.news import fetch_stock_news
from tools.crypto import is_crypto_symbol
from agent_trace import AgentTracer
import logging
"""
The Agent is responsible for actually doing the work.

It takes a list of tasks produced by the planner and
executes them one by one, storing results in shared memory.

Every step is also recorded on an AgentTracer (real timing + status) so the UI
can replay the agent loop as a transparent, live execution trace.
"""


# ── Small, resilient formatters used only to build human-readable trace
#    detail lines. They never raise, so tracing can't break a run. ──
def _fmt_money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(value):
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_num(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_big(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    for magnitude, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(number) >= magnitude:
            return f"${number / magnitude:.2f}{suffix}"
    return f"${number:,.0f}"


class Agent:
    def __init__(self, memory, tracer=None):
        # Shared memory object used to store data between steps
        self.memory = memory
        # Records each executed step for the UI's execution-trace panel. A run
        # without a supplied tracer still works — it just records into its own.
        self.tracer = tracer or AgentTracer()

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

                started = self.tracer.now()
                try:
                    # Pull price history from the data source
                    price_data = fetch_price_history(ticker, period, start_date, end_date)
                    # Store successful results in memory
                    self.memory.set(f"{ticker}_data", price_data)
                    self.memory.set(f"{ticker}_status", "ok")
                    self.memory.set(f"{ticker}_period", period)
                    logging.info(f"Fetched data for {ticker} ({period})")

                    try:
                        rows = len(price_data)
                        first = float(price_data["Close"].iloc[0])
                        last = float(price_data["Close"].iloc[-1])
                        detail = f"{rows} bars · {_fmt_money(first)} → {_fmt_money(last)}"
                    except Exception:
                        detail = f"Loaded price history · {period}"
                    self.tracer.record(
                        "data", "Fetch price history", "ok",
                        detail=detail, ticker=ticker,
                        duration_ms=self.tracer.elapsed_ms(started),
                    )
                except Exception as e:
                    # Mark ticker as have failed. This allows later steps to safely skip it
                    self.memory.set(f"{ticker}_status", "error")
                    self.memory.set(f"{ticker}_error", str(e))
                    logging.error(f"Failed to fetch data for {ticker}: {e}")
                    self.tracer.record(
                        "data", "Fetch price history", "error",
                        detail=str(e), ticker=ticker,
                        duration_ms=self.tracer.elapsed_ms(started),
                    )

            # Task: compute metrics + build chart
            elif task["task"] == "compute_metrics":
                ticker = task["ticker"]
                 # Only continue if data was fetched successfully
                status = self.memory.get(f"{ticker}_status")
                if status != "ok":
                    logging.warning(f"Skipping metric computation for {ticker} because data fetch failed.")
                    self.tracer.record(
                        "metrics", "Compute performance metrics", "skip",
                        detail="Skipped — price data unavailable", ticker=ticker,
                    )
                    continue

                price_data = self.memory.get(f"{ticker}_data")

                # Compute return, volatility, Sharpe ratio, etc.
                started = self.tracer.now()
                metrics = compute_all_metrics(price_data)
                self.memory.set(f"{ticker}_metrics", metrics)
                self.tracer.record(
                    "metrics", "Compute performance metrics", "ok",
                    detail=(
                        f"Return {_fmt_pct(metrics.get('total_return'))} · "
                        f"Sharpe {_fmt_num(metrics.get('sharpe_ratio'))} · "
                        f"Max DD {_fmt_pct(metrics.get('max_drawdown'))}"
                    ),
                    ticker=ticker,
                    duration_ms=self.tracer.elapsed_ms(started),
                )

                # Folder where charts are saved
                charts_dir = Path("output") / "charts"
                period = self.memory.get(f"{ticker}_period", "unknown")
                # Build and save the price chart
                started = self.tracer.now()
                chart_path = plot_close_price_line(price_data, ticker, period, charts_dir)
                 # Save chart path so reports and dashboard can use it
                self.memory.set(f"{ticker}_chart_path", str(chart_path.resolve()))
                self.tracer.record(
                    "charts", "Render price chart", "ok",
                    detail="Close-price line chart generated", ticker=ticker,
                    duration_ms=self.tracer.elapsed_ms(started),
                )
                logging.info(f"Computed metrics and chart for {ticker}")

                if is_crypto_symbol(ticker):
                    self.memory.set(f"{ticker}_analyst_view", {"ticker": ticker, "available": False})
                    self.memory.set(f"{ticker}_fundamentals", {"ticker": ticker, "available": False})
                    self.memory.set(f"{ticker}_earnings", {"ticker": ticker, "available": False})
                    for tool, label in (
                        ("analyst", "Fetch analyst coverage"),
                        ("fundamentals", "Fetch company fundamentals"),
                        ("earnings", "Fetch earnings snapshot"),
                    ):
                        self.tracer.record(
                            tool, label, "skip",
                            detail="Not applicable for crypto assets", ticker=ticker,
                        )
                else:
                    started = self.tracer.now()
                    try:
                        latest_close = price_data["Close"].iloc[-1]
                        analyst_view = fetch_analyst_view(ticker, latest_close)
                        self.memory.set(f"{ticker}_analyst_view", analyst_view)
                        logging.info(f"Fetched analyst view for {ticker}")
                        if analyst_view.get("available"):
                            detail = (
                                f"{analyst_view.get('recommendation', '—')} · "
                                f"{analyst_view.get('analyst_count', '?')} analysts · "
                                f"{_fmt_pct(analyst_view.get('upside'))} upside"
                            )
                            self.tracer.record(
                                "analyst", "Fetch analyst coverage", "ok",
                                detail=detail, ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                        else:
                            self.tracer.record(
                                "analyst", "Fetch analyst coverage", "warn",
                                detail="No analyst coverage available", ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_analyst_view",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Analyst view unavailable for {ticker}: {e}")
                        self.tracer.record(
                            "analyst", "Fetch analyst coverage", "warn",
                            detail="Analyst data unavailable", ticker=ticker,
                            duration_ms=self.tracer.elapsed_ms(started),
                        )

                    started = self.tracer.now()
                    try:
                        fundamentals = fetch_company_fundamentals(ticker)
                        self.memory.set(f"{ticker}_fundamentals", fundamentals)
                        logging.info(f"Fetched fundamentals for {ticker}")
                        if fundamentals.get("available"):
                            detail = (
                                f"{fundamentals.get('sector') or 'n/a'} · "
                                f"{_fmt_big(fundamentals.get('market_cap'))} cap · "
                                f"P/E {_fmt_num(fundamentals.get('pe_ratio'))}"
                            )
                            self.tracer.record(
                                "fundamentals", "Fetch company fundamentals", "ok",
                                detail=detail, ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                        else:
                            self.tracer.record(
                                "fundamentals", "Fetch company fundamentals", "warn",
                                detail="Fundamentals unavailable", ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_fundamentals",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Fundamentals unavailable for {ticker}: {e}")
                        self.tracer.record(
                            "fundamentals", "Fetch company fundamentals", "warn",
                            detail="Fundamentals unavailable", ticker=ticker,
                            duration_ms=self.tracer.elapsed_ms(started),
                        )

                    started = self.tracer.now()
                    try:
                        earnings = fetch_earnings_snapshot(ticker)
                        self.memory.set(f"{ticker}_earnings", earnings)
                        logging.info(f"Fetched earnings snapshot for {ticker}")
                        if earnings.get("available"):
                            result_word = earnings.get("eps_result")
                            result_suffix = f" · EPS {result_word}" if result_word else ""
                            detail = (
                                f"{earnings.get('fiscal_period') or 'latest report'} · "
                                f"EPS {_fmt_money(earnings.get('eps_actual'))}{result_suffix}"
                            )
                            self.tracer.record(
                                "earnings", "Fetch earnings snapshot", "ok",
                                detail=detail, ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                        else:
                            self.tracer.record(
                                "earnings", "Fetch earnings snapshot", "warn",
                                detail="Earnings data unavailable", ticker=ticker,
                                duration_ms=self.tracer.elapsed_ms(started),
                            )
                    except Exception as e:
                        self.memory.set(
                            f"{ticker}_earnings",
                            {"ticker": ticker, "available": False, "error": str(e)},
                        )
                        logging.warning(f"Earnings unavailable for {ticker}: {e}")
                        self.tracer.record(
                            "earnings", "Fetch earnings snapshot", "warn",
                            detail="Earnings data unavailable", ticker=ticker,
                            duration_ms=self.tracer.elapsed_ms(started),
                        )

                started = self.tracer.now()
                try:
                    news_items = fetch_stock_news(ticker, limit=3)
                    self.memory.set(f"{ticker}_news", news_items)
                    logging.info(f"Fetched news for {ticker}")
                    count = len(news_items or [])
                    if count:
                        self.tracer.record(
                            "news", "Pull market news", "ok",
                            detail=f"{count} recent headline{'s' if count != 1 else ''}",
                            ticker=ticker, duration_ms=self.tracer.elapsed_ms(started),
                        )
                    else:
                        self.tracer.record(
                            "news", "Pull market news", "warn",
                            detail="No recent news found", ticker=ticker,
                            duration_ms=self.tracer.elapsed_ms(started),
                        )
                except Exception as e:
                    self.memory.set(f"{ticker}_news", [])
                    logging.warning(f"News unavailable for {ticker}: {e}")
                    self.tracer.record(
                        "news", "Pull market news", "warn",
                        detail="News feed unavailable", ticker=ticker,
                        duration_ms=self.tracer.elapsed_ms(started),
                    )

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
                started = self.tracer.now()
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

                try:
                    return_a = metrics_a.get("total_return")
                    return_b = metrics_b.get("total_return")
                    if return_a is not None and return_b is not None:
                        leader = ticker_a if float(return_a) >= float(return_b) else ticker_b
                        detail = f"{ticker_a} vs {ticker_b} · {leader} leads on total return"
                    else:
                        detail = f"{ticker_a} vs {ticker_b} · normalized growth chart built"
                except Exception:
                    detail = f"{ticker_a} vs {ticker_b}"
                self.tracer.record(
                    "compare", "Compare & build growth chart", "ok",
                    detail=detail, duration_ms=self.tracer.elapsed_ms(started),
                )
