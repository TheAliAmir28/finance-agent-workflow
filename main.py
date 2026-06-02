from planner import Planner
from agent import Agent
from memory.store import MemoryStore
from reports.synthesizer import ReportSynthesizer
from reports.dashboard import build_dashboard
from pathlib import Path
import argparse
import logging
from history import save_run_history

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

def parse_args():
    parser = argparse.ArgumentParser(description="Finance Agent Workflow")
    parser.add_argument("--tickers", nargs=2, metavar=("TICKER1", "TICKER2"),
                        help="Two tickers to analyze (e.g., --tickers AAPL NVDA)")
    parser.add_argument("--range", default="1y",
                        help="Time range like 3mo, 6mo, 1y, 2y (default: 1y)")
    parser.add_argument("--summary", action="store_true",
                        help="Enable optional AI summary")
    return parser.parse_args()

# This function runs the full pipeline and returns a structured result dictionary
def run_analysis_from_request(user_input):
    # Set up core components
    planner = Planner()
    memory = MemoryStore()
    agent = Agent(memory)

    try:
        # Convert user input into a structured plan
        plan = planner.create_plan(user_input)
        tasks = plan["tasks"]

        # Store LLM summary mode flag so other parts can use it
        memory.set("use_llm_summary", plan["use_llm_summary"])
    except ValueError as e:
        raise ValueError(f"Planner error: {e}")

    # Check if this is a comparison run
    is_comparison = any(task["task"] == "compare_metrics" for task in tasks)

    if is_comparison:
        tickers_found = {
            task["ticker"]
            for task in tasks
            if "ticker" in task
        }

        if len(tickers_found) < 2:
            raise ValueError(
                "Comparison requested, but fewer than two valid tickers were found."
            )

    try:
        agent.run(tasks)
    except ValueError as e:
        raise ValueError(f"Runtime error: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected runtime error: {e}")

    # Build the HTML dashboard after tasks complete
    dashboard_path = build_dashboard(
        agent.memory,
        Path("output") / "dashboard" / "index.html"
    )
    logging.info(f"Dashboard created: {dashboard_path}")

    # Determine which tickers were involved
    tickers = []
    for task in tasks:
        if "ticker" in task and task["ticker"] not in tickers:
            tickers.append(task["ticker"])

    # Extract period
    period = None
    for task in tasks:
        if task["task"] == "fetch_data":
            period = task["period"]
            break

    # Generate report
    synthesizer = ReportSynthesizer(memory)
    report = synthesizer.generate_report(tickers, period)

    # Build filename
    if len(tickers) == 1:
        filename = f"analysis_{tickers[0]}_{period}.txt"
    else:
        filename = f"comparison_{tickers[0]}_{tickers[1]}_{period}.txt"

    # Save report to disk
    synthesizer.save_report(report, filename)

    report_path = Path("reports") / "generated" / filename

    result = {
        "report": report,
        "report_path": str(report_path),
        "dashboard_path": str(dashboard_path),
        "tickers": tickers,
        "period": period,
        "memory": memory,
        "is_comparison": is_comparison,
    }

    history_path = save_run_history(user_input, result)
    result["history_path"] = str(history_path)

    return result

# CLI wrapper (main)
def main():
    args = parse_args()

    if args.tickers:
        t1, t2 = args.tickers[0].upper(), args.tickers[1].upper()
        user_input = f"Analyze {t1} and {t2} for {args.range}"
        if args.summary:
            user_input += " with summary"
    else:
        user_input = input("Enter your request: ")

    try:
        result = run_analysis_from_request(user_input)
    except ValueError as e:
        logging.error(str(e))
        return
    except RuntimeError as e:
        logging.error(str(e))
        return

    print("\n=== REPORT GENERATED ===\n")
    print(result["report"])
    print(f"\nReport saved to {result['report_path']}")
    print(f"Dashboard created: {result['dashboard_path']}")
    print(f"History saved to: {result['history_path']}")

if __name__ == "__main__":
    main()

