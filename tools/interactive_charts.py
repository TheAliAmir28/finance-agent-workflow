from __future__ import annotations

import json

import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder


CHART_COLORS = ["#38bdf8", "#f97316"]


def _figure_to_json(fig: go.Figure) -> str:
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def _apply_layout(fig: go.Figure, title: str) -> None:
    fig.update_layout(
        title={
            "text": title,
            "x": 0,
            "y": 0.98,
            "xanchor": "left",
            "yanchor": "top",
            "font": {"size": 18, "color": "#f4f8ff"},
        },
        paper_bgcolor="#0f1625",
        plot_bgcolor="#0f1625",
        font={"color": "#dbe7ff", "family": "Inter, Segoe UI, system-ui, sans-serif", "size": 14},
        margin={"l": 42, "r": 18, "t": 104, "b": 38},
        hovermode="closest",
        hoverlabel={
            "bgcolor": "#111827",
            "bordercolor": "rgba(125,211,252,0.35)",
            "font": {"color": "#e8eefc", "size": 14},
        },
        xaxis={
            "showgrid": False,
            "showline": True,
            "linecolor": "rgba(255,255,255,0.16)",
            "tickfont": {"color": "#a9b4d0", "size": 14},
            "showspikes": False,
            "rangeslider": {"visible": False},
            "fixedrange": True,
        },
        yaxis={
            "gridcolor": "rgba(255,255,255,0.08)",
            "zeroline": False,
            "tickfont": {"color": "#a9b4d0", "size": 14},
            "separatethousands": True,
            "showspikes": False,
            "fixedrange": True,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        dragmode=False,
    )


def build_price_chart_json(price_data, ticker: str, period: str) -> str:
    if price_data is None or price_data.empty or "Close" not in price_data.columns:
        raise ValueError("price_data must include Close prices for an interactive chart.")

    ticker = ticker.upper()
    close = price_data["Close"]
    start_price = close.iloc[0]
    returns = (close / start_price - 1) * 100

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=price_data.index,
            y=close,
            mode="lines",
            name=ticker,
            line={"color": CHART_COLORS[0], "width": 2.4},
            customdata=returns,
            hoverinfo="none",
        )
    )

    _apply_layout(fig, f"{ticker} Close Price ({period})")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _figure_to_json(fig)


def build_comparison_chart_json(
    price_data_a,
    price_data_b,
    ticker_a: str,
    ticker_b: str,
    period: str,
) -> str:
    if price_data_a is None or price_data_b is None:
        raise ValueError("Both price series are required for an interactive comparison chart.")

    ticker_a = ticker_a.upper()
    ticker_b = ticker_b.upper()

    fig = go.Figure()
    for idx, (ticker, close_prices) in enumerate(
        (
            (ticker_a, price_data_a["Close"]),
            (ticker_b, price_data_b["Close"]),
        )
    ):
        growth = (close_prices / close_prices.iloc[0] - 1) * 100
        fig.add_trace(
            go.Scatter(
                x=close_prices.index,
                y=growth,
                mode="lines",
                name=ticker,
                line={"color": CHART_COLORS[idx], "width": 2.4},
                hoverinfo="none",
                customdata=close_prices,
            )
        )

    _apply_layout(fig, f"{ticker_a} vs {ticker_b} Growth Comparison ({period})")
    fig.update_yaxes(title_text="Growth", ticksuffix="%", tickformat=",.0f")
    return _figure_to_json(fig)
