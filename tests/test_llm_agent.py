from unittest.mock import patch

import pytest

import llm_agent
from llm_agent import LLMAgentError, run_llm_agent
from tests.fake_openai import FakeClient, assistant_turn, tool_call
from tools import agent_tools


@pytest.fixture
def patched_tools(price_data, tmp_path):
    """Route every yfinance/matplotlib-touching call to fast fakes."""
    with patch.object(agent_tools.data_fetch, "fetch_price_history",
                      return_value=price_data), \
         patch.object(agent_tools.charts, "plot_close_price_line",
                      return_value=tmp_path / "chart.png"), \
         patch.object(agent_tools.charts, "plot_comparison_normalized",
                      return_value=tmp_path / "compare.png"), \
         patch.object(agent_tools.analyst, "fetch_analyst_view",
                      return_value={"ticker": "X", "available": False}), \
         patch.object(agent_tools.fundamentals, "fetch_company_fundamentals",
                      return_value={"ticker": "X", "available": False}), \
         patch.object(agent_tools.earnings, "fetch_earnings_snapshot",
                      return_value={"ticker": "X", "available": False}), \
         patch.object(agent_tools.news, "fetch_stock_news", return_value=[]):
        yield


def test_happy_path_single_ticker(memory, tracer, patched_tools):
    client = FakeClient([
        assistant_turn([tool_call("c1", "fetch_price_history", ticker="AAPL", period="1y")]),
        assistant_turn([tool_call("c2", "compute_metrics", ticker="AAPL"),
                        tool_call("c3", "render_chart", ticker="AAPL"),
                        tool_call("c4", "fetch_news", ticker="AAPL")]),
        assistant_turn([tool_call("c5", "fetch_analyst_view", ticker="AAPL"),
                        tool_call("c6", "fetch_fundamentals", ticker="AAPL"),
                        tool_call("c7", "fetch_earnings", ticker="AAPL")]),
        assistant_turn([tool_call("c8", "finish", tickers=["AAPL"], period="1y",
                                  use_llm_summary=True)]),
    ])
    meta = run_llm_agent("Analyze AAPL", memory, tracer, client=client)
    assert meta == {"tickers": ["AAPL"], "period": "1y", "use_llm_summary": True}
    assert memory.get("AAPL_metrics") is not None
    assert memory.get("use_llm_summary") is True
    # every scripted response consumed, tool results fed back as tool messages
    final_messages = client.requests[-1]["messages"]
    assert any(m.get("role") == "tool" for m in final_messages if isinstance(m, dict))


def test_completion_check_backfills_skipped_steps(memory, tracer, patched_tools):
    # Model fetches and immediately finishes; code must backfill the rest.
    client = FakeClient([
        assistant_turn([tool_call("c1", "fetch_price_history", ticker="AAPL", period="1y"),
                        tool_call("c2", "fetch_price_history", ticker="NVDA", period="1y")]),
        assistant_turn([tool_call("c3", "finish", tickers=["AAPL", "NVDA"], period="1y",
                                  use_llm_summary=True)]),
    ])
    meta = run_llm_agent("Compare AAPL and NVDA", memory, tracer, client=client)
    assert meta["tickers"] == ["AAPL", "NVDA"]
    for ticker in ("AAPL", "NVDA"):
        assert memory.get(f"{ticker}_metrics") is not None
        assert memory.get(f"{ticker}_chart_path") is not None
        assert memory.get(f"{ticker}_news") is not None
        assert memory.get(f"{ticker}_analyst_view") is not None
    assert memory.get("comparison") is not None
    assert any(e["label"].startswith("Backfill:") for e in tracer.events)


def test_round_cap_stops_loop_and_backfills(memory, tracer, patched_tools):
    fetch_round = assistant_turn(
        [tool_call("c1", "fetch_price_history", ticker="AAPL", period="1y")])
    chatter = assistant_turn([tool_call("cx", "fetch_news", ticker="AAPL")])
    client = FakeClient([fetch_round] + [chatter] * 20)
    meta = run_llm_agent("Analyze AAPL", memory, tracer, client=client, max_rounds=3)
    assert len(client.requests) == 3
    assert meta["tickers"] == ["AAPL"]
    assert memory.get("AAPL_metrics") is not None  # backfilled


def test_finish_is_exempt_from_tool_budget(memory, tracer, patched_tools):
    # Budget of 1 is spent on the fetch; finish must still be allowed through.
    client = FakeClient([
        assistant_turn([tool_call("c1", "fetch_price_history", ticker="AAPL", period="1y")]),
        assistant_turn([tool_call("c2", "fetch_news", ticker="AAPL"),
                        tool_call("c3", "finish", tickers=["AAPL"], period="1y",
                                  use_llm_summary=True)]),
    ])
    meta = run_llm_agent("Analyze AAPL", memory, tracer, client=client, max_tool_calls=1)
    assert meta == {"tickers": ["AAPL"], "period": "1y", "use_llm_summary": True}
    # the over-budget news call was refused, so the backfill supplied it
    assert memory.get("AAPL_news") is not None


def test_no_tickers_raises(memory, tracer, patched_tools):
    client = FakeClient([assistant_turn(content="I cannot help with that.")])
    with pytest.raises(LLMAgentError):
        run_llm_agent("What's the weather?", memory, tracer, client=client)


def test_api_failure_raises_llm_agent_error(memory, tracer, patched_tools):
    client = FakeClient([RuntimeError("api down")])
    with pytest.raises(LLMAgentError):
        run_llm_agent("Analyze AAPL", memory, tracer, client=client)


def test_finish_defaults_derived_when_model_never_finishes(memory, tracer, patched_tools):
    client = FakeClient([
        assistant_turn([tool_call("c1", "fetch_price_history", ticker="AAPL", period="6mo")]),
        assistant_turn(content="All done."),
    ])
    meta = run_llm_agent("Analyze AAPL for 6 months no summary", memory, tracer,
                         client=client)
    assert meta["tickers"] == ["AAPL"]
    assert meta["period"] == "6mo"
    assert meta["use_llm_summary"] is False  # "no summary" honored by fallback parse
