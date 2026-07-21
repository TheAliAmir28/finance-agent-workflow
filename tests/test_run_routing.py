from unittest.mock import patch

import main
from llm_agent import LLMAgentError


def _fake_llm(tickers=("AAPL",), period="1y"):
    def runner(user_input, memory, tracer, **kwargs):
        for ticker in tickers:
            memory.set(f"{ticker}_status", "ok")
        memory.set("use_llm_summary", True)
        return {"tickers": list(tickers), "period": period, "use_llm_summary": True}
    return runner


def _finish_run_stubs():
    """Stub out the heavy tail (dashboard/report/history) shared by both paths."""
    return (
        patch.object(main, "build_dashboard", return_value="output/dashboard/index.html"),
        patch.object(main.ReportSynthesizer, "generate_report", return_value="REPORT"),
        patch.object(main.ReportSynthesizer, "save_report"),
        patch.object(main, "save_run_history", return_value="output/history/run.json"),
    )


def test_llm_path_used_when_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    stubs = _finish_run_stubs()
    with patch.object(main, "run_llm_agent", side_effect=_fake_llm()) as llm, \
         patch.object(main.Planner, "create_plan") as plan, \
         stubs[0], stubs[1], stubs[2], stubs[3]:
        result = main.run_analysis_from_request("Analyze AAPL")
    llm.assert_called_once()
    plan.assert_not_called()
    assert result["tickers"] == ["AAPL"]
    assert result["is_comparison"] is False


def test_regex_path_used_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stubs = _finish_run_stubs()
    with patch.object(main, "run_llm_agent") as llm, \
         patch.object(main.Agent, "run"), \
         stubs[0], stubs[1], stubs[2], stubs[3]:
        result = main.run_analysis_from_request("Analyze AAPL")
    llm.assert_not_called()
    assert result["tickers"] == ["AAPL"]


def test_llm_failure_falls_back_to_regex(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    stubs = _finish_run_stubs()
    with patch.object(main, "run_llm_agent",
                      side_effect=LLMAgentError("api down")) as llm, \
         patch.object(main.Agent, "run") as agent_run, \
         stubs[0], stubs[1], stubs[2], stubs[3]:
        result = main.run_analysis_from_request("Analyze AAPL")
    llm.assert_called_once()
    agent_run.assert_called_once()
    assert result["tickers"] == ["AAPL"]


def test_comparison_flag_from_llm_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    stubs = _finish_run_stubs()
    with patch.object(main, "run_llm_agent",
                      side_effect=_fake_llm(("AAPL", "NVDA"))), \
         stubs[0], stubs[1], stubs[2], stubs[3]:
        result = main.run_analysis_from_request("Compare AAPL and NVDA")
    assert result["is_comparison"] is True
