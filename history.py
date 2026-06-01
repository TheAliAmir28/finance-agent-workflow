import json
from datetime import datetime
from pathlib import Path
from typing import List

# Sets the history folder
HISTORY_DIR = Path("output") / "history"

# Save one analysis run as a JSON file in output/history/.
def save_run_history(user_input, result):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    history_path = HISTORY_DIR / f"run_{timestamp}.json"

    memory = result.get("memory")
    tickers = result.get("tickers", [])

    ticker_metrics = {}
    if memory is not None:
        for ticker in tickers:
            ticker_metrics[ticker] = memory.get(f"{ticker}_metrics", {})

    history_data = {
        "timestamp": timestamp,
        "user_input": user_input,
        "tickers": tickers,
        "period": result.get("period"),
        "is_comparison": result.get("is_comparison"),
        "report_path": result.get("report_path"),
        "dashboard_path": result.get("dashboard_path"),
        "metrics": ticker_metrics,
        "comparison": memory.get("comparison") if memory is not None else None,
    }

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=2, default=str)

    # Returns path to the saved JSON history file.
    return history_path

# Loads the most recent analysis runs from output/history/.
def load_recent_history(limit=5):
    if not HISTORY_DIR.exists():
        return []

    history_files = sorted(
        HISTORY_DIR.glob("run_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    recent_runs = []

    for history_file in history_files[:limit]:
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                run_data = json.load(f)

            # Store path too so the UI can show it
            run_data["history_path"] = str(history_file)
            recent_runs.append(run_data)

        except Exception:
            # Skip broken history files instead of crashing the app
            continue
        
    # Most the most recent history entries, newest first in the form of a list
    return recent_runs