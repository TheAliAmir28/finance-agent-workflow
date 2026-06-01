from flask import Flask, render_template, request, send_file, abort
from pathlib import Path
from main import run_analysis_from_request
from history import load_recent_history

app = Flask(__name__)

@app.route("/open")
def open_file():
    file_path = request.args.get("path", "").strip()

    if not file_path:
        abort(400)

    resolved_path = Path(file_path).resolve()

    if not resolved_path.exists() or not resolved_path.is_file():
        abort(404)

    return send_file(resolved_path)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    user_input = ""
    chart_entries = []
    comparison_chart_path = None
    llm_summaries = []

    if request.method == "POST":
        user_input = request.form.get("user_input", "").strip()

        if not user_input:
            error = "Please enter a request."
        else:
            try:
                result = run_analysis_from_request(user_input)

                memory = result.get("memory")
                tickers = result.get("tickers", [])

                if memory is not None:
                    # Collect per-ticker chart paths
                    for ticker in tickers:
                        chart_path = memory.get(f"{ticker}_chart_path")
                        if chart_path:
                            chart_entries.append({
                                "ticker": ticker,
                                "path": chart_path,
                            })

                    # Collect comparison chart if it exists
                    comparison_chart_path = memory.get("comparison_chart_path")

                    # Collect optional LLM summaries
                    for ticker in tickers:
                        llm_text = memory.get(f"{ticker}_llm_summary")
                        if llm_text:
                            llm_summaries.append({
                                "title": f"{ticker} LLM Summary",
                                "text": llm_text,
                            })

                    comparison_llm = memory.get("comparison_llm_summary")
                    if comparison_llm:
                        llm_summaries.append({
                            "title": "Comparison LLM Summary",
                            "text": comparison_llm,
                        })

            except Exception as e:
                error = str(e)

    recent_runs = load_recent_history(limit=5)

    return render_template(
        "index.html",
        result=result,
        error=error,
        user_input=user_input,
        recent_runs=recent_runs,
        chart_entries=chart_entries,
        comparison_chart_path=comparison_chart_path,
        llm_summaries=llm_summaries,
    )

if __name__ == "__main__":
    app.run(debug=True)