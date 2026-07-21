from unittest.mock import patch

from tools import agent_tools
from tools.agent_tools import ToolExecutor


def _fetch(executor, ticker, price_data):
    with patch.object(agent_tools.data_fetch, "fetch_price_history", return_value=price_data):
        executor.execute("fetch_price_history", {"ticker": ticker, "period": "1y"})


def test_analyst_view_stored_and_summarized(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    _fetch(executor, "AAPL", price_data)
    view = {"ticker": "AAPL", "available": True, "recommendation": "buy",
            "analyst_count": 30, "upside": 0.12}
    with patch.object(agent_tools.analyst, "fetch_analyst_view", return_value=view):
        result = executor.execute("fetch_analyst_view", {"ticker": "AAPL"})
    assert memory.get("AAPL_analyst_view") is view
    assert result["recommendation"] == "buy"


def test_enrichment_failure_writes_unavailable(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    _fetch(executor, "AAPL", price_data)
    with patch.object(agent_tools.fundamentals, "fetch_company_fundamentals",
                      side_effect=RuntimeError("throttled")):
        result = executor.execute("fetch_fundamentals", {"ticker": "AAPL"})
    assert "error" in result
    assert memory.get("AAPL_fundamentals")["available"] is False


def test_crypto_enrichment_is_skipped(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    _fetch(executor, "BTC-USD", price_data)
    for tool, key in (("fetch_analyst_view", "BTC-USD_analyst_view"),
                      ("fetch_fundamentals", "BTC-USD_fundamentals"),
                      ("fetch_earnings", "BTC-USD_earnings")):
        result = executor.execute(tool, {"ticker": "BTC-USD"})
        assert result["skipped"] == "crypto"
        assert memory.get(key) == {"ticker": "BTC-USD", "available": False}


def test_news_stored(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    _fetch(executor, "AAPL", price_data)
    items = [{"title": "Apple ships thing"}]
    with patch.object(agent_tools.news, "fetch_stock_news", return_value=items):
        result = executor.execute("fetch_news", {"ticker": "AAPL"})
    assert memory.get("AAPL_news") is items
    assert result["headline_count"] == 1


def test_compare_tickers_happy_path(memory, tracer, price_data, tmp_path):
    executor = ToolExecutor(memory, tracer)
    for ticker in ("AAPL", "NVDA"):
        _fetch(executor, ticker, price_data)
        executor.execute("compute_metrics", {"ticker": ticker})
    with patch.object(agent_tools.charts, "plot_comparison_normalized",
                      return_value=tmp_path / "compare.png"):
        result = executor.execute("compare_tickers", {"ticker_a": "AAPL", "ticker_b": "NVDA"})
    assert memory.get("comparison")["winner"] in ("AAPL", "NVDA", "Tie", None)
    assert memory.get("comparison_chart_path", "").endswith("compare.png")
    assert "winner" in result


def test_compare_tickers_degrades_when_one_side_missing(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    _fetch(executor, "AAPL", price_data)
    executor.execute("compute_metrics", {"ticker": "AAPL"})
    result = executor.execute("compare_tickers", {"ticker_a": "AAPL", "ticker_b": "NVDA"})
    assert "error" in result           # reported to the model...
    assert memory.get("comparison") is None  # ...but nothing raised, run continues
