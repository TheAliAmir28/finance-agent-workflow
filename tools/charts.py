# tools/charts.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
# Use a non-GUI backend so charts can be saved without a display.
# This is important when running on servers or from scripts.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

"""
Make sure a directory exists.
If it already exists, do nothing.
"""
def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_close_price_line(
    price_data,
    ticker: str,
    period: str,
    out_dir: Path,
) -> Path:
    """
    Creates a simple line chart of Close price over time and saves it as a PNG.
    Expects `price_data` to be a DataFrame with a 'Close' column and a datetime index.
    """
    # Make sure the output directory exists before saving
    ensure_dir(out_dir)

    # Basic validation (prevents crashes)
    if price_data is None or len(price_data) == 0:
        raise ValueError("price_data is empty; cannot plot chart.")
    if "Close" not in price_data.columns:
        raise ValueError("price_data must include a 'Close' column.")

    ticker = ticker.upper()
    # Build the output filename and path
    filename = f"{ticker}_{period}.png"
    out_path = out_dir / filename

    # Make the plot
    plt.figure()
    plt.plot(price_data.index, price_data["Close"])
    plt.title(f"{ticker} Close Price ({period})")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.tight_layout()
    # Save the chart as an image file
    plt.savefig(out_path, dpi=150)
    plt.close()

    return out_path

def plot_comparison_normalized(
    price_data_a,
    price_data_b,
    ticker_a: str,
    ticker_b: str,
    period: str,
    out_dir: Path,
) -> Path:
    """
    Plots two tickers on the same chart, normalized to start at 1.0.
    """
    ensure_dir(out_dir)

    if price_data_a is None or price_data_b is None:
        raise ValueError("Price data missing for comparison chart.")

    # Normalize prices
    norm_a = price_data_a["Close"] / price_data_a["Close"].iloc[0]
    norm_b = price_data_b["Close"] / price_data_b["Close"].iloc[0]

    ticker_a = ticker_a.upper()
    ticker_b = ticker_b.upper()
    # Build the output filename and path
    filename = f"compare_{ticker_a}_{ticker_b}_{period}.png"
    out_path = out_dir / filename

    plt.figure()
    plt.plot(norm_a.index, norm_a, label=ticker_a)
    plt.plot(norm_b.index, norm_b, label=ticker_b)
    # Add labels and legend for clarity
    plt.title(f"{ticker_a} vs {ticker_b} (Normalized, {period})")
    plt.xlabel("Date")
    plt.ylabel("Growth (Start = 1.0)")
    plt.legend()
    plt.tight_layout()
    # Save the chart as an image file
    plt.savefig(out_path, dpi=150)
    plt.close()

    return out_path
