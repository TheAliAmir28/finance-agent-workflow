from pathlib import Path

from tools.llm_client import generate_llm_summary

"""
Helper function used by the report generator.

Tries to pull the first and last Close prices from the data.
If anything goes wrong, it safely returns (None, None) instead of crashing the program.
"""
def _get_start_end_close(price_data):
    try:
        if price_data is None or len(price_data) == 0:
            return None, None
        start = float(price_data["Close"].iloc[0])
        end = float(price_data["Close"].iloc[-1])
        return start, end
    except Exception:
        return None, None

"""
Turns stored data and metrics into a readable text report.

This class does not fetch data or calculate metrics.
It only reads from memory and focuses on presentation.
"""
class ReportSynthesizer:
    def __init__(self, memory):
        # Shared memory that holds all results from the Agent
        self.memory = memory

    # Generate a human-readable analysis report.
    def generate_report(self, tickers, period):
        # Single stock report
        if len(tickers) == 1:
            ticker = tickers[0]

            status = self.memory.get(f"{ticker}_status")

            report = []
            report.append("=== STOCK ANALYSIS REPORT ===\n")
            report.append(f"Ticker: {ticker}")
            report.append(f"Time Period: {period}\n")

            # If data fetch failed, explain the issue and stop early
            if status != "ok":
                error_msg = self.memory.get(f"{ticker}_error", "Unknown error")
                report.append("Error:")
                report.append(
                    f"- Unable to retrieve data for {ticker}.\n"
                    f"- Reason: {error_msg}"
                )
                report.append("\nPlease check the ticker symbol and try again.")
                return "\n".join(report)

            # Pull computed metrics from memory
            metrics = self.memory.get(f"{ticker}_metrics", {}) or {}

            report.append("Performance Metrics:")

            total_return = metrics.get("total_return")
            volatility = metrics.get("volatility")
            sharpe = metrics.get("sharpe_ratio")
            # Print metrics
            if total_return is not None:
                report.append(f"- Total Return: {float(total_return):.2%}")
            else:
                report.append("- Total Return: N/A")

            if volatility is not None:
                report.append(f"- Volatility: {float(volatility):.2%}")
            else:
                report.append("- Volatility: N/A")

            if sharpe is not None:
                try:
                    report.append(f"- Sharpe Ratio: {float(sharpe):.2f}")
                except Exception:
                    report.append("- Sharpe Ratio: N/A")
            else:
                report.append("- Sharpe Ratio: N/A")

            # Optional LLM-generated summary
            price_data = self.memory.get(f"{ticker}_data")
            start_close, end_close = _get_start_end_close(price_data)
            # Build a small, clean output for the LLM
            payload = {
                "mode": "single",
                "ticker": ticker,
                "period": period,
                "metrics": {
                    "total_return": float(total_return) if total_return is not None else None,
                    "volatility": float(volatility) if volatility is not None else None,
                    "sharpe_ratio": sharpe,
                },
                "start_close": start_close,
                "end_close": end_close,
            }
            # Check if AI summaries are enabled
            use_llm = self.memory.get("use_llm_summary", True)
            llm_text = generate_llm_summary(payload, use_llm)

            if llm_text:
                # Store summary for dashboard use
                self.memory.set(f"{ticker}_llm_summary", llm_text)
                report.append("")
                report.append("LLM Summary (Optional):")
                report.append(llm_text)
                report.append("")

            else:
                # Fallback summary when AI is disabled or unavailable
                report.append("\nSummary:")
                if total_return is not None and volatility is not None:
                    report.append(
                        f"Over the selected period, {ticker} showed a total return of "
                        f"{float(total_return):.2%} with a volatility of "
                        f"{float(volatility):.2%}. "
                        "This provides a snapshot of the stock’s overall performance "
                        "and risk profile."
                    )
                else:
                    report.append(
                        f"Over the selected period, {ticker} produced a set of performance metrics. "
                        "This provides a snapshot of overall performance and risk."
                    )

            return "\n".join(report)

        # COMPARISON REPORT
        if len(tickers) == 2:
            ticker_a, ticker_b = tickers

            status_a = self.memory.get(f"{ticker_a}_status")
            status_b = self.memory.get(f"{ticker_b}_status")

            report = []
            report.append("=== STOCK COMPARISON REPORT ===\n")
            report.append(f"Time Period: {period}\n")

            # If either ticker failed, explain why and stop
            if status_a != "ok" or status_b != "ok":
                report.append("Comparison Error:")

                if status_a != "ok":
                    error_a = self.memory.get(f"{ticker_a}_error", "Unknown error")
                    report.append(f"- {ticker_a}: {error_a}")

                if status_b != "ok":
                    error_b = self.memory.get(f"{ticker_b}_error", "Unknown error")
                    report.append(f"- {ticker_b}: {error_b}")

                report.append(
                    "\nComparison could not be performed because one or more tickers "
                    "did not return valid data."
                )

                return "\n".join(report)

            # Both tickers are valid, so continue normally
            metrics_a = self.memory.get(f"{ticker_a}_metrics", {}) or {}
            metrics_b = self.memory.get(f"{ticker_b}_metrics", {}) or {}
            comparison = self.memory.get("comparison") or {}

            # Print metrics for ticker A
            report.append(f"{ticker_a}:")
            tr_a = metrics_a.get("total_return")
            vol_a = metrics_a.get("volatility")
            sharpe_a = metrics_a.get("sharpe_ratio")

            report.append(f"- Total Return: {float(tr_a):.2%}" if tr_a is not None else "- Total Return: N/A")
            report.append(f"- Volatility: {float(vol_a):.2%}" if vol_a is not None else "- Volatility: N/A")
            report.append(
                f"- Sharpe Ratio: {float(sharpe_a):.2f}"
                if sharpe_a is not None
                else "- Sharpe Ratio: N/A"
            )
            report.append("")

            # Print metrics for ticker B
            report.append(f"{ticker_b}:")
            tr_b = metrics_b.get("total_return")
            vol_b = metrics_b.get("volatility")
            sharpe_b = metrics_b.get("sharpe_ratio")

            report.append(f"- Total Return: {float(tr_b):.2%}" if tr_b is not None else "- Total Return: N/A")
            report.append(f"- Volatility: {float(vol_b):.2%}" if vol_b is not None else "- Volatility: N/A")
            report.append(
                f"- Sharpe Ratio: {float(sharpe_b):.2f}"
                if sharpe_b is not None
                else "- Sharpe Ratio: N/A"
            )
            report.append("")

            # Optional LLM comparison summary
            price_data_a = self.memory.get(f"{ticker_a}_data")
            price_data_b = self.memory.get(f"{ticker_b}_data")
            start_a, end_a = _get_start_end_close(price_data_a)
            start_b, end_b = _get_start_end_close(price_data_b)

            payload = {
                "mode": "comparison",
                "period": period,
                "tickers": [ticker_a, ticker_b],
                "ticker_a": {
                    "ticker": ticker_a,
                    "metrics": {
                        "total_return": float(tr_a) if tr_a is not None else None,
                        "volatility": float(vol_a) if vol_a is not None else None,
                        "sharpe_ratio": sharpe_a,
                    },
                    "start_close": start_a,
                    "end_close": end_a,
                },
                "ticker_b": {
                    "ticker": ticker_b,
                    "metrics": {
                        "total_return": float(tr_b) if tr_b is not None else None,
                        "volatility": float(vol_b) if vol_b is not None else None,
                        "sharpe_ratio": sharpe_b,
                    },
                    "start_close": start_b,
                    "end_close": end_b,
                },
                "comparison": {
                    "winner": comparison.get("winner"),
                    "reason": comparison.get("reason"),
                } if comparison else None,
            }

            use_llm = self.memory.get("use_llm_summary", True)
            llm_text = generate_llm_summary(payload, use_llm)

            # Print comparison result
            winner = comparison.get("winner", "N/A")
            reason = comparison.get("reason", "N/A")

            report.append(f"Winner: {winner}")
            report.append(f"Reason: {reason}\n")
            report.append("")

            if llm_text:
                self.memory.set("comparison_llm_summary", llm_text)
                report.append("LLM Summary (Optional):")
                report.append(llm_text)
                report.append("")
            else: 
                # Fallback text when AI is disabled
                report.append("Conclusion:")

                
                if winner in ("Tie", None, "N/A"):
                    report.append(
                        f"Over the selected period, {ticker_a} and {ticker_b} performed similarly on a risk-adjusted basis. "
                        "This comparison highlights how return and volatility together provide a more complete picture "
                        "than raw performance alone."
                    )
                else:
                    loser = ticker_b if winner == ticker_a else ticker_a
                    report.append(
                        f"Over the selected period, {winner} outperformed "
                        f"{loser} "
                        "based on risk-adjusted performance and overall returns. "
                        "This comparison highlights how return and volatility together "
                        "provide a more complete picture than raw performance alone."
                    )

            return "\n".join(report)
        # Catch-all fallback (should not normally happen)
        return "Unable to generate report."

    # Save the report text to a file.
    def save_report(self, report_text, filename):
        base_dir = Path(__file__).resolve().parent  # /reports
        out_dir = base_dir / "generated"  # /reports/generated
        out_dir.mkdir(parents=True, exist_ok=True)  # create the folder if it doesn't exist already
        # Write report text to file
        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_text)
