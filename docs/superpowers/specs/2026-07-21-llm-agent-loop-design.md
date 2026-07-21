# LLM Tool-Calling Agent Loop — Design

**Date:** 2026-07-21
**Status:** Approved

## Goal

Replace the regex/keyword planner + fixed-task executor as the *primary* analysis
path with a genuine LLM tool-calling agent loop: the model decides which research
tools to invoke, in what order, and when the workspace is complete. The existing
regex path is retained as a fallback so the app keeps working with no API key.

## Decisions (locked)

- **Provider:** OpenAI, `gpt-4o-mini` (already used for summaries; same key/SDK).
- **No-key mode:** preserved — regex `Planner` + old `Agent` remain the fallback.
- **Ticker cap:** the existing 2-ticker limit stays, enforced in code.
- **Memory contract:** the memory keys written by the current pipeline
  (`{ticker}_data`, `{ticker}_status`, `{ticker}_period`, `{ticker}_metrics`,
  `{ticker}_chart_path`, `{ticker}_analyst_view`, `{ticker}_fundamentals`,
  `{ticker}_earnings`, `{ticker}_news`, `comparison`, `comparison_chart_path`,
  `use_llm_summary`) are unchanged, so the dashboard builder, report
  synthesizer, result context, and history all work without modification.

## Architecture

```
user request
   │
   ├─ OPENAI_API_KEY set? ──no──→ regex Planner + old Agent (unchanged fallback)
   │
   yes
   ↓
llm_agent.run_llm_agent()
   │  gpt-4o-mini + tool schemas, loop until finish() or iteration cap
   │  each tool call → dispatch → real tool → MemoryStore write → compact result to model
   ↓
completion check (plain code)
   │  verifies required memory keys per ticker; backfills any missing step
   ↓
dashboard + report + history (unchanged)
```

If the OpenAI API itself fails mid-loop, the per-run memory is cleared and the
request reruns through the regex fallback so the user still gets a result.

## New components

### `tools/symbol_search.py` (extraction refactor)

The Yahoo symbol lookup currently embedded in `app.py`'s `/api/symbol-search`
route moves here (including its TTL cache), so the route and the new
`resolve_symbol` tool share one implementation. Route behavior unchanged.

### `tools/agent_tools.py` (tool registry)

For each tool: an OpenAI function schema + a dispatch wrapper that

1. calls the existing tool implementation,
2. writes memory keys exactly as `agent.py` does today,
3. records a tracer event (same tool ids/labels the trace UI already knows),
4. returns a **compact JSON summary** to the model (never a DataFrame).

Toolset:

| Tool | Wraps | Notes |
| --- | --- | --- |
| `resolve_symbol(query)` | Yahoo symbol search | Resolves company names/typos to validated tickers |
| `fetch_price_history(ticker, period, start_date?, end_date?)` | `tools/data_fetch.py` | Writes `_data`/`_status`/`_period`; refuses a 3rd distinct ticker |
| `compute_metrics(ticker)` | `tools/metrics.py` | Errors back to the model if data missing |
| `render_chart(ticker)` | `tools/charts.py` | Writes `_chart_path` |
| `fetch_analyst_view(ticker)` | `tools/analyst.py` | Model instructed to skip for crypto |
| `fetch_fundamentals(ticker)` | `tools/fundamentals.py` | Skip for crypto |
| `fetch_earnings(ticker)` | `tools/earnings.py` | Skip for crypto |
| `fetch_news(ticker)` | `tools/news.py` | |
| `compare_tickers(ticker_a, ticker_b)` | `tools/metrics.compare_metrics` + comparison chart | Explicit args; degrades gracefully if one ticker failed |
| `finish(tickers, period, use_llm_summary)` | — | Required terminal call; supplies run metadata to `main.py` |

Crypto tickers get the same treatment as today: analyst/fundamentals/earnings
recorded as unavailable/skipped.

### `llm_agent.py` (the loop)

- `run_llm_agent(user_input, memory, tracer, *, client=None, max_rounds=10, max_tool_calls=16)`.
- System prompt states the job: build a complete research workspace — per
  ticker fetch → metrics → chart → analyst/fundamentals/earnings/news (skip the
  three for crypto), compare when exactly two tickers, honor "no summary",
  at most two tickers, call `finish` when done.
- OpenAI chat-completions API with `tools=`, parallel tool calls enabled,
  client timeout ~30s per round.
- Tool errors are returned to the model as error payloads (it can retry or
  move on) *and* written to memory as error status, matching today's behavior.
- Loop ends on `finish`, on a response with no tool calls, or at the caps.
- `client` is injectable for tests.

### Completion check

After the loop, plain code walks the run's tickers and directly invokes the
dispatch wrapper for any required step whose memory key is missing. Backfilled
steps are recorded in the trace under a distinct `backfill` tool id (honestly
labeled in the UI). Guarantees the dashboard is never half-empty.

## Guardrails

- Iteration cap (~10 model rounds) and total tool-call budget (~16).
- 2-ticker cap enforced in `fetch_price_history` dispatch, not just the prompt.
- Per-round client timeout so a hung API call cannot pin the job thread.
- Whole-loop failure → clear memory → regex fallback rerun.
- A failed ticker no longer aborts a comparison run: `compare_tickers` reports
  the problem and the run completes with the surviving ticker (fixes the
  existing partial-failure crash).

## Integration points

- `main.py::run_analysis_from_request` routes: LLM path when a key is present,
  regex path otherwise or on LLM failure. Run metadata (`tickers`, `period`)
  comes from `finish` (LLM path) or the task list (fallback path).
- `app.py`: import symbol search from `tools/symbol_search.py`; add
  `backfill` (and an `agent` planner-round label) to `TOOL_LABELS`. No other
  route/template changes.

## Trace UI

Each model round records a `planner`-style event describing what the model
chose (e.g. `→ fetch_price_history(NVDA, 1y)`), and each tool execution records
the same events the UI shows today. Backfill steps are visibly labeled.

## Testing

New test suite (pytest, first tests in the repo), all offline:

- Fake OpenAI client injected into the loop: scripted tool-call sequences.
- Covers: dispatch + memory writes per tool; iteration/budget cap enforcement;
  2-ticker refusal; `finish` metadata plumbing; tool-error propagation to both
  model and memory; completion-check backfill; crypto skip behavior;
  no-key fallback routing; LLM-failure fallback rerun.
- yfinance-touching functions are mocked; no network in tests.

## Out of scope

- N-ticker support (follow-up), PDF export, persistence changes, auth,
  any dashboard/template redesign, changes to the summary generator.
