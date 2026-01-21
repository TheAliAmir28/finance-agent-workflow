from __future__ import annotations

from pathlib import Path


def _escape_html(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _relpath_str(path_str: str, base_dir: Path) -> str:
    """
    Return a browser-friendly relative path from base_dir to path_str.
    Works on Windows by converting backslashes to forward slashes.
    """
    import os

    p = Path(path_str)

    # If it's not absolute, treat it as relative to the project working directory
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    base = base_dir.resolve()

    rel = os.path.relpath(p, start=base)
    return rel.replace("\\", "/")



def build_dashboard(memory, out_html_path: Path) -> Path:
    """
    Builds output/dashboard/index.html using data already stored in memory:
    - {TICKER}_metrics
    - {TICKER}_chart_path
    - comparison (optional)
    - comparison_chart_path (optional)
    """
    out_html_path.parent.mkdir(parents=True, exist_ok=True)

    # Gather tickers that have metrics
    metric_keys = [k for k in memory._store.keys() if k.endswith("_metrics")]
    tickers = [k.replace("_metrics", "") for k in metric_keys]

    # Sort tickers for stable ordering in the dashboard
    tickers.sort()

    # Prepare sections
    cards_html = []
    charts_html = []

    for t in tickers:
        metrics = memory.get(f"{t}_metrics", {})
        chart_path = memory.get(f"{t}_chart_path", "")

        total_return = metrics.get("total_return", "N/A")
        volatility = metrics.get("volatility", "N/A")
        sharpe = metrics.get("sharpe_ratio", "N/A")

        # Make chart path relative to dashboard folder
        rel_chart = ""
        if chart_path:
            rel_chart = _relpath_str(chart_path, out_html_path.parent)

        cards_html.append(
            f"""
            <div class="card">
              <div class="card-header">
                <h2>{_escape_html(t)}</h2>
                <div class="muted">Period: {_escape_html(memory.get(f"{t}_period", "unknown"))}</div>
              </div>
              <table class="metrics">
                <tr><td>Total return</td><td class="num">{_escape_html(total_return)}</td></tr>
                <tr><td>Volatility</td><td class="num">{_escape_html(volatility)}</td></tr>
                <tr><td>Sharpe ratio</td><td class="num">{_escape_html(sharpe)}</td></tr>
              </table>
            </div>
            """
        )

        if rel_chart:
            charts_html.append(
                f"""
                <div class="chart-block">
                  <h3>{_escape_html(t)} Close Price</h3>
                  <img class="chart" src="{_escape_html(rel_chart)}" alt="{_escape_html(t)} chart" />
                </div>
                """
            )

    # Comparison section (optional)
    comparison = memory.get("comparison")
    comparison_chart_path = memory.get("comparison_chart_path", "")

    comparison_html = ""
    if comparison:
        winner = comparison.get("winner", "N/A")
        reason = comparison.get("reason", "")

        rel_compare_chart = ""
        if comparison_chart_path:
            rel_compare_chart = _relpath_str(comparison_chart_path, out_html_path.parent)

        comparison_html = f"""
        <div class="section">
          <h2>Comparison</h2>
          <div class="card">
            <table class="metrics">
              <tr><td>Winner</td><td class="num">{_escape_html(winner)}</td></tr>
              <tr><td>Reason</td><td class="num">{_escape_html(reason)}</td></tr>
            </table>
          </div>

          {"<div class='chart-block'><h3>Normalized Comparison</h3><img class='chart' src='" + _escape_html(rel_compare_chart) + "' alt='Comparison chart' /></div>" if rel_compare_chart else ""}
        </div>
        """

    # Final HTML
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Finance Agent Dashboard</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      background: #0b0f17;
      color: #e8eefc;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .title {{
      font-size: 22px;
      font-weight: 700;
    }}
    .muted {{
      color: #a9b4d0;
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }}
    .card {{
      background: #121a2a;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.25);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 10px;
    }}
    h2 {{
      margin: 0;
      font-size: 18px;
    }}
    h3 {{
      margin: 0 0 8px 0;
      font-size: 16px;
    }}
    .metrics {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }}
    .metrics td {{
      padding: 8px 6px;
      border-top: 1px solid rgba(255,255,255,0.08);
      font-size: 14px;
    }}
    .metrics td.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .section {{
      margin-top: 26px;
    }}
    .chart-block {{
      margin-top: 14px;
      background: #0f1625;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      padding: 14px;
    }}
    .chart {{
      width: 100%;
      height: auto;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      background: #0b0f17;
    }}
    .footer {{
      margin-top: 22px;
      color: #a9b4d0;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <div class="title">Finance Agent Dashboard</div>
      <div class="muted">Generated locally</div>
    </div>

    <div class="section">
      <h2>Summary</h2>
      <div class="grid">
        {''.join(cards_html)}
      </div>
    </div>

    <div class="section">
      <h2>Charts</h2>
      {''.join(charts_html) if charts_html else "<div class='muted'>No charts found.</div>"}
    </div>

    {comparison_html}

    <div class="footer">
      Tip: keep this page open and re-run the program to refresh charts + metrics.
    </div>
  </div>
</body>
</html>
"""

    out_html_path.write_text(html, encoding="utf-8")
    return out_html_path
