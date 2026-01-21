from planner import Planner
from agent import Agent
from memory.store import MemoryStore
from reports.synthesizer import ReportSynthesizer
from reports.dashboard import build_dashboard
from pathlib import Path
"""
Main entry point of the application.

This function reads user input, builds a task plan, runs the analysis pipeline and generates charts, dashboard, and report
"""
def main():
    # Set up core components
    planner = Planner()
    memory = MemoryStore()
    agent = Agent(memory)
    # Ask the user for a request
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

