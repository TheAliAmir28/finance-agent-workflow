from planner import Planner
from agent import Agent
from memory.store import MemoryStore
from reports.synthesizer import ReportSynthesizer
from reports.dashboard import build_dashboard
from pathlib import Path
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Finance Agent Workflow")
    parser.add_argument("--tickers", nargs=2, metavar=("TICKER1", "TICKER2"),
                        help="Two tickers to analyze (e.g., --tickers AAPL NVDA)")
    parser.add_argument("--range", default="1y",
                        help="Time range like 3mo, 6mo, 1y, 2y (default: 1y)")
    parser.add_argument("--summary", action="store_true",
                        help="Enable optional AI summary")
    return parser.parse_args()

"""
Main entry point of the application.

This function reads user input, builds a task plan, runs the analysis pipeline and generates charts, dashboard, and report
"""
def main():
    # Set up core components
    planner = Planner()
    memory = MemoryStore()
    agent = Agent(memory)
    # CLI usage
    args = parse_args()

    if args.tickers:
        t1, t2 = args.tickers[0].upper(), args.tickers[1].upper()
        user_input = f"Analyze {t1} and {t2} for {args.range}"
        if args.summary:
            user_input += " with summary"
    # If CLI isn't in use
    else:
        user_input = input("Enter your request: ")

    try:
        # Convert user input into a structured plan
        plan = planner.create_plan(user_input)
        tasks = plan["tasks"]

        # Store LLM summary mode flag so other parts can use it
        memory.set("use_llm_summary", plan["use_llm_summary"])
    except ValueError as e:
        # Planner errors usually mean invalid input like no tickers, too many etc.
        print(f"Error: {e}")
        return

    # Check if this is a comparison run
    is_comparison = any(task["task"] == "compare_metrics" for task in tasks)

    if is_comparison:
        # Retrieve unique tickers found in tasks
        tickers_found = {
            task["ticker"]
            for task in tasks
            if "ticker" in task
        }
        # Comparison requires exactly two valid tickers
        if len(tickers_found) < 2:
            print(
                "Error: Comparison requested, but fewer than two valid tickers were found.\n"
                "Please check the ticker symbols and try again."
            )
            return

    # Run the task pipeline
    agent.run(tasks)
    # Build the HTML dashboard after tasks complete
    dashboard_path = build_dashboard(agent.memory, Path("output") / "dashboard" / "index.html")
    print(f"Dashboard created: {dashboard_path}")

    # Determine which tickers involved
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
    
    #Final output to the console
    print("\n=== REPORT GENERATED ===\n")
    print(report)
    print(f"\nReport saved to reports/generated/{filename}")

if __name__ == "__main__":
    main()

