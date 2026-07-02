from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

from tools.crypto import is_crypto_symbol


CHART_COLORS = ["#0EA5E9", "#F97316", "#7C3AED", "#10B981"]

_BG      = "#F8FBFF"
_GRID    = "rgba(0,0,0,0.055)"
_LINE    = "rgba(2,132,199,0.18)"
_TICK    = "#64748B"
_TEXT_FG = "#334155"


def _close_series(price_data):
    close = pd.to_numeric(price_data["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("price_data must include valid numeric Close prices.")
    return close


def _figure_to_json(fig: go.Figure) -> str:
    return json.dumps(fig, cls=PlotlyJSONEncoder)


def _padded_x_range(*indexes, frac: float = 0.025):
    """Return an [min, max] x-range with a small symmetric horizontal pad.

    Without this, Plotly fits the axis exactly to the data so the line sits
    flush against the y-axis. A small pad on both sides gives the chart a clean,
    professional gap. Returns ISO date strings; None if there's nothing to plot.
    """
    starts = [idx[0] for idx in indexes if len(idx)]
    ends   = [idx[-1] for idx in indexes if len(idx)]
    if not starts or not ends:
        return None

    x_min = min(starts)
    x_max = max(ends)
    pad = (x_max - x_min) * frac
    return [(x_min - pad).isoformat(), (x_max + pad).isoformat()]


def _apply_layout(fig: go.Figure, *, top_margin: int = 18) -> None:
    fig.update_layout(
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font={"color": _TEXT_FG, "family": "'IBM Plex Sans', 'IBM Plex Mono', monospace", "size": 12},
        margin={"l": 54, "r": 14, "t": top_margin, "b": 36},
        hovermode="closest",
        hoverlabel={
            "bgcolor": "rgba(255,255,255,0.95)",
            "bordercolor": "rgba(2,132,199,0.30)",
            "font": {"color": "#0A1B30", "size": 12},
        },
        xaxis={
            "showgrid": False,
            "showline": True,
            "linecolor": _LINE,
            "tickfont": {"color": _TICK, "size": 11},
            "showspikes": False,
            "rangeslider": {"visible": False},
            "fixedrange": True,
            "ticks": "outside",
            "tickcolor": _LINE,
            "ticklen": 4,
        },
        yaxis={
            "gridcolor": _GRID,
            "gridwidth": 1,
            "zeroline": False,
            "tickfont": {"color": _TICK, "size": 11},
            "separatethousands": True,
            "showspikes": False,
            "fixedrange": True,
            "showline": False,
            "nticks": 8,
        },
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.08,
            "xanchor": "left",
            "x": 0,
            "bgcolor": "rgba(255,255,255,0.0)",
            "borderwidth": 0,
            "font": {"color": _TEXT_FG, "size": 12},
        },
        dragmode=False,
    )


def _apply_rangebreaks(fig: go.Figure, period: str, *tickers: str) -> None:
    """Hide non-trading hours and weekends for US equity intraday charts.

    Skipped for crypto (24/7 markets) and non-intraday periods.
    Timestamps are stored as US/Eastern naive values, so bounds are ET hours.
    """
    if period not in ("1d", "5d"):
        return
    if any(is_crypto_symbol(t) for t in tickers):
        return

    rangebreaks: list[dict] = [
        # Hide 4:00 PM to 9:30 AM ET (non-trading hours every day)
        dict(bounds=[16, 9.5], pattern="hour"),
    ]
    if period == "5d":
        # Also hide Saturday and Sunday for multi-day views
        rangebreaks.append(dict(bounds=["sat", "mon"]))

    fig.update_xaxes(rangebreaks=rangebreaks)


def build_price_chart_json(price_data, ticker: str, period: str) -> str:
    if price_data is None or price_data.empty or "Close" not in price_data.columns:
        raise ValueError("price_data must include Close prices for an interactive chart.")

    ticker = ticker.upper()
    close = _close_series(price_data)
    start_price = close.iloc[0]
    returns = (close / start_price - 1) * 100

    c_min = float(close.min())
    c_max = float(close.max())
    pad   = max((c_max - c_min) * 0.07, abs(c_max) * 0.01, 1)

    fig = go.Figure()

    # Single price trace. fill='tozeroy' with an explicit y-axis range:
    # Plotly clips the fill at the visible bottom edge, so it looks like a
    # proper area chart without needing a separate baseline trace.
    fig.add_trace(
        go.Scatter(
            x=close.index,
            y=close,
            mode="lines",
            name=ticker,
            line={"color": CHART_COLORS[0], "width": 2.0, "shape": "spline", "smoothing": 0.35},
            fill="tozeroy",
            fillcolor="rgba(14,165,233,0.08)",
            customdata=returns,
            hoverinfo="none",
        )
    )

    _apply_layout(fig)
    fig.update_yaxes(
        tickprefix="$",
        tickformat=",.0f",
        range=[c_min - pad, c_max + pad],
    )
    x_range = _padded_x_range(close.index)
    if x_range:
        fig.update_xaxes(range=x_range)
    _apply_rangebreaks(fig, period, ticker)
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
    for i, (ticker, close_prices) in enumerate(
        (
            (ticker_a, _close_series(price_data_a)),
            (ticker_b, _close_series(price_data_b)),
        )
    ):
        growth = (close_prices / close_prices.iloc[0] - 1) * 100
        fig.add_trace(
            go.Scatter(
                x=close_prices.index,
                y=growth,
                mode="lines",
                name=ticker,
                line={"color": CHART_COLORS[i], "width": 2.2},
                hoverinfo="none",
                customdata=close_prices,
            )
        )

    # Place the legend in its own band above the plot so it never collides with
    # the x-axis date labels at the bottom. The extra top margin gives it room.
    _apply_layout(fig, top_margin=40)
    fig.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "bgcolor": "rgba(255,255,255,0.0)",
            "borderwidth": 0,
            "font": {"color": _TEXT_FG, "size": 12.5},
        },
    )
    fig.update_yaxes(ticksuffix="%", tickformat=",.1f")
    x_range = _padded_x_range(_close_series(price_data_a).index, _close_series(price_data_b).index)
    if x_range:
        fig.update_xaxes(range=x_range)
    _apply_rangebreaks(fig, period, ticker_a, ticker_b)
    return _figure_to_json(fig)
