from pathlib import Path
from unittest.mock import patch

from tools import agent_tools
from tools.agent_tools import ToolExecutor, TOOL_SCHEMAS


def test_schemas_cover_all_tools():
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert names == {
        "resolve_symbol", "fetch_price_history", "compute_metrics", "render_chart",
        "fetch_analyst_view", "fetch_fundamentals", "fetch_earnings", "fetch_news",
        "compare_tickers", "finish",
    }


def test_resolve_symbol_uses_search(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    hits = [{"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ", "type": "Equity"}]
    with patch.object(agent_tools, "search_symbols", return_value=hits):
        result = executor.execute("resolve_symbol", {"query": "nvidia"})
    assert result["results"][0]["symbol"] == "NVDA"


def test_resolve_symbol_prefers_crypto_alias(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    result = executor.execute("resolve_symbol", {"query": "bitcoin"})
    assert result["results"][0]["symbol"] == "BTC-USD"


def test_fetch_price_history_writes_memory_contract(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    with patch.object(agent_tools.data_fetch, "fetch_price_history", return_value=price_data):
        result = executor.execute("fetch_price_history", {"ticker": "AAPL", "period": "1y"})
    assert memory.get("AAPL_status") == "ok"
    assert memory.get("AAPL_period") == "1y"
    assert memory.get("AAPL_data") is price_data
    assert result["rows"] == 60
    assert executor.tickers == ["AAPL"]


def test_fetch_price_history_error_is_reported_not_raised(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    with patch.object(agent_tools.data_fetch, "fetch_price_history",
                      side_effect=ValueError("No data found for ticker: XXXX")):
        result = executor.execute("fetch_price_history", {"ticker": "XXXX", "period": "1y"})
    assert "error" in result
    assert memory.get("XXXX_status") == "error"
    assert executor.tickers == []


def test_third_distinct_ticker_is_refused(memory, tracer, price_data):
    executor = ToolExecutor(memory, tracer)
    with patch.object(agent_tools.data_fetch, "fetch_price_history", return_value=price_data):
        executor.execute("fetch_price_history", {"ticker": "AAPL", "period": "1y"})
        executor.execute("fetch_price_history", {"ticker": "NVDA", "period": "1y"})
        result = executor.execute("fetch_price_history", {"ticker": "MSFT", "period": "1y"})
    assert "error" in result and "two tickers" in result["error"]
    assert executor.tickers == ["AAPL", "NVDA"]
    assert memory.get("MSFT_status") is None


def test_compute_metrics_requires_fetched_data(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    result = executor.execute("compute_metrics", {"ticker": "AAPL"})
    assert "error" in result


def test_compute_metrics_and_chart(memory, tracer, price_data, tmp_path):
    executor = ToolExecutor(memory, tracer)
    with patch.object(agent_tools.data_fetch, "fetch_price_history", return_value=price_data):
        executor.execute("fetch_price_history", {"ticker": "AAPL", "period": "1y"})
    result = executor.execute("compute_metrics", {"ticker": "AAPL"})
    assert memory.get("AAPL_metrics")["total_return"] is not None
    assert "total_return" in result

    with patch.object(agent_tools.charts, "plot_close_price_line",
                      return_value=tmp_path / "AAPL_1y.png") as plot:
        chart_result = executor.execute("render_chart", {"ticker": "AAPL"})
    plot.assert_called_once()
    assert memory.get("AAPL_chart_path", "").endswith("AAPL_1y.png")
    assert chart_result["chart"] == "saved"


def test_finish_records_metadata(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    result = executor.execute(
        "finish", {"tickers": ["AAPL"], "period": "1y", "use_llm_summary": False})
    assert result == {"ok": True}
    assert executor.finish_args == {
        "tickers": ["AAPL"], "period": "1y", "use_llm_summary": False}


def test_unknown_tool_returns_error(memory, tracer):
    executor = ToolExecutor(memory, tracer)
    assert "error" in executor.execute("launch_missiles", {})
