from planner import Planner
from agent import Agent
from agent_trace import AgentTracer
from memory.store import MemoryStore
from reports.synthesizer import ReportSynthesizer
from reports.dashboard import build_dashboard
from pathlib import Path
import argparse
import logging
import os
from history import save_run_history
from llm_agent import LLMAgentError, run_llm_agent

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
def run_analysis_from_request(user_input, tracer=None):
    memory = MemoryStore()
    # Shared tracer records every planner/agent step for the execution-trace UI.
    # A caller (e.g. the background job) may inject one wired to stream live.
    tracer = tracer or AgentTracer()

    # Primary path: the LLM tool-calling agent decides which tools to run.
    # Fallback path: the original regex Planner → Agent pipeline, used when no
    # API key is configured or the LLM path fails for any reason.
    if os.getenv("OPENAI_API_KEY"):
        try:
            meta = run_llm_agent(user_input, memory, tracer)
            tickers, period = meta["tickers"], meta["period"]
        except LLMAgentError as exc:
            logging.warning("LLM agent unavailable, using fallback planner: %s", exc)
            memory.clear()
            tracer.record("planner", "LLM agent unavailable — regex fallback", "warn",
                          detail=str(exc))
            tickers, period = _run_regex_pipeline(user_input, memory, tracer)
    else:
        tickers, period = _run_regex_pipeline(user_input, memory, tracer)

    is_comparison = len(tickers) == 2

    # Build the HTML dashboard after tasks complete
    dashboard_path = build_dashboard(
        memory,
        Path("output") / "dashboard" / "index.html"
    )
    logging.info(f"Dashboard created: {dashboard_path}")

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
        "trace": tracer.export(),
    }

    history_path = save_run_history(user_input, result)
    result["history_path"] = str(history_path)

    return result


# The original Planner → Agent path, kept verbatim as the fallback.
def _run_regex_pipeline(user_input, memory, tracer):
    planner = Planner()
    agent = Agent(memory, tracer)

    try:
        # Convert user input into a structured plan
        plan_started = tracer.now()
        plan = planner.create_plan(user_input)
        tasks = plan["tasks"]

        # Store LLM summary mode flag so other parts can use it
        memory.set("use_llm_summary", plan["use_llm_summary"])

        # Record the planning step from the parsed plan
        planned_tickers = []
        planned_period = None
        for task in tasks:
            ticker = task.get("ticker")
            if ticker and ticker not in planned_tickers:
                planned_tickers.append(ticker)
            if task["task"] == "fetch_data" and planned_period is None:
                planned_period = task.get("period")
        ticker_label = ", ".join(planned_tickers) if planned_tickers else "none"
        summary_label = "on" if plan["use_llm_summary"] else "off"
        tracer.record(
            "planner", "Parse request → task plan", "ok",
            detail=(
                f"{len(planned_tickers)} ticker(s): {ticker_label} · "
                f"period {planned_period or 'default'} · AI summary {summary_label} · "
                f"{len(tasks)} tasks queued"
            ),
            duration_ms=tracer.elapsed_ms(plan_started),
        )
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

    return tickers, period

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

