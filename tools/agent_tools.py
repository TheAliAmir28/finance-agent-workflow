"""OpenAI tool schemas + dispatch layer for the LLM agent loop.

Each wrapper calls the existing tool implementation, writes the exact same
MemoryStore keys the deterministic pipeline writes (so the dashboard, report
synthesizer, and history work unchanged), records a tracer event, and returns
a compact JSON-able summary for the model — never a DataFrame.

execute() never raises: failures come back as {"error": ...} payloads the
model can read and route around, while memory gets the same error status the
old pipeline would have written.
"""

from pathlib import Path
import logging

from tools import charts, data_fetch, metrics
from tools import analyst, earnings, fundamentals, news
from tools.crypto import CRYPTO_NAME_TO_SYMBOL, is_crypto_symbol, normalize_crypto_symbol
from tools.symbol_search import search_symbols

CHARTS_DIR = Path("output") / "charts"

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "resolve_symbol",
        "description": "Resolve a company or asset name (or an unverified ticker) "
                       "to validated ticker symbols. Use this whenever the user "
                       "gives a name, a possible typo, or an unfamiliar symbol.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Company/asset name or candidate ticker."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_price_history",
        "description": "Fetch historical prices for one ticker and store them in the "
                       "workspace. Must be called before any other per-ticker tool. "
                       "At most two distinct tickers per run.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "period": {"type": "string",
                       "description": "Relative window like 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y. "
                                      "Ignored when start_date/end_date are given."},
            "start_date": {"type": "string", "description": "YYYY-MM-DD (custom range only)."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD (custom range only)."},
        }, "required": ["ticker", "period"]},
    }},
    {"type": "function", "function": {
        "name": "compute_metrics",
        "description": "Compute return, volatility, Sharpe, CAGR, max drawdown and "
                       "moving averages for a fetched ticker.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "render_chart",
        "description": "Render and save the close-price chart for a fetched ticker.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_analyst_view",
        "description": "Fetch analyst recommendations and price targets. Stocks only — "
                       "skip for crypto.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_fundamentals",
        "description": "Fetch company fundamentals (valuation, sector, market cap). "
                       "Stocks only — skip for crypto.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_earnings",
        "description": "Fetch the latest earnings snapshot. Stocks only — skip for crypto.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_news",
        "description": "Fetch recent news headlines for a ticker.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
        }, "required": ["ticker"]},
    }},
    {"type": "function", "function": {
        "name": "compare_tickers",
        "description": "Compare two analyzed tickers (winner + normalized growth chart). "
                       "Call only when exactly two tickers have metrics.",
        "parameters": {"type": "object", "properties": {
            "ticker_a": {"type": "string"},
            "ticker_b": {"type": "string"},
        }, "required": ["ticker_a", "ticker_b"]},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call exactly once, last, when the workspace is complete.",
        "parameters": {"type": "object", "properties": {
            "tickers": {"type": "array", "items": {"type": "string"},
                        "description": "The tickers actually analyzed."},
            "period": {"type": "string", "description": "The period label used."},
            "use_llm_summary": {"type": "boolean",
                                "description": "False only if the user asked for no summary."},
        }, "required": ["tickers", "period", "use_llm_summary"]},
    }},
]


class ToolExecutor:
    MAX_TICKERS = 2

    def __init__(self, memory, tracer):
        self.memory = memory
        self.tracer = tracer
        self.tickers = []        # distinct tickers successfully fetched
        self.finish_args = None  # populated by the finish tool
        self._label_prefix = ""

    # ── dispatch ──
    def execute(self, name, args, backfill=False):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}
        self._label_prefix = "Backfill: " if backfill else ""
        try:
            return handler(**(args or {}))
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}
        except Exception as exc:  # a tool bug must never kill the run
            logging.exception("Tool %s failed unexpectedly", name)
            return {"error": f"{name} failed: {exc}"}

    def _record(self, tool, label, status, detail, ticker=None, started=None):
        self.tracer.record(
            tool, self._label_prefix + label, status,
            detail=detail, ticker=ticker,
            duration_ms=self.tracer.elapsed_ms(started) if started is not None else None,
        )

    # ── tools ──
    def _tool_resolve_symbol(self, query):
        started = self.tracer.now()
        cleaned = str(query or "").strip().lower()
        crypto = CRYPTO_NAME_TO_SYMBOL.get(cleaned)
        if crypto:
            results = [{"symbol": normalize_crypto_symbol(crypto), "name": cleaned.title(),
                        "exchange": "Crypto", "type": "Cryptocurrency"}]
        else:
            results = search_symbols(query, max_results=5)
        detail = (f"'{query}' → {results[0]['symbol']}" if results
                  else f"No match for '{query}'")
        self._record("planner", "Resolve symbol", "ok" if results else "warn",
                     detail, started=started)
        return {"results": results}

    def _tool_fetch_price_history(self, ticker, period="1y", start_date=None, end_date=None):
        symbol = normalize_crypto_symbol(str(ticker or "").strip().upper())
        if not symbol:
            return {"error": "ticker is required"}
        if symbol not in self.tickers and len(self.tickers) >= self.MAX_TICKERS:
            return {"error": "At most two tickers per analysis. "
                             f"Already analyzing: {', '.join(self.tickers)}."}
        if start_date and end_date:
            period_label = f"{start_date} to {end_date}"
        else:
            period_label, start_date, end_date = period, None, None

        started = self.tracer.now()
        try:
            price_data = data_fetch.fetch_price_history(symbol, period_label, start_date, end_date)
        except Exception as exc:
            self.memory.set(f"{symbol}_status", "error")
            self.memory.set(f"{symbol}_error", str(exc))
            logging.error(f"Failed to fetch data for {symbol}: {exc}")
            self._record("data", "Fetch price history", "error", str(exc), symbol, started)
            return {"error": f"Could not fetch {symbol}: {exc}"}

        self.memory.set(f"{symbol}_data", price_data)
        self.memory.set(f"{symbol}_status", "ok")
        self.memory.set(f"{symbol}_period", period_label)
        if symbol not in self.tickers:
            self.tickers.append(symbol)

        first = round(float(price_data["Close"].iloc[0]), 2)
        last = round(float(price_data["Close"].iloc[-1]), 2)
        self._record("data", "Fetch price history", "ok",
                     f"{len(price_data)} bars · ${first:,.2f} → ${last:,.2f}", symbol, started)
        return {"ticker": symbol, "rows": len(price_data), "period": period_label,
                "first_close": first, "last_close": last,
                "is_crypto": is_crypto_symbol(symbol)}

    def _require_data(self, ticker):
        symbol = normalize_crypto_symbol(str(ticker or "").strip().upper())
        if self.memory.get(f"{symbol}_status") != "ok":
            return symbol, {"error": f"No price data for {symbol}. "
                                     "Call fetch_price_history first."}
        return symbol, None

    def _tool_compute_metrics(self, ticker):
        symbol, err = self._require_data(ticker)
        if err:
            return err
        started = self.tracer.now()
        computed = metrics.compute_all_metrics(self.memory.get(f"{symbol}_data"))
        self.memory.set(f"{symbol}_metrics", computed)
        detail = (f"Return {computed['total_return'] * 100:+.1f}% · "
                  f"Max DD {(computed['max_drawdown'] or 0) * 100:+.1f}%")
        self._record("metrics", "Compute performance metrics", "ok", detail, symbol, started)
        compact = {}
        for key, value in computed.items():
            compact[key] = round(float(value), 4) if value is not None else None
        return compact

    def _tool_render_chart(self, ticker):
        symbol, err = self._require_data(ticker)
        if err:
            return err
        started = self.tracer.now()
        period = self.memory.get(f"{symbol}_period", "unknown")
        chart_path = charts.plot_close_price_line(
            self.memory.get(f"{symbol}_data"), symbol, period, CHARTS_DIR)
        self.memory.set(f"{symbol}_chart_path", str(Path(chart_path).resolve()))
        self._record("charts", "Render price chart", "ok",
                     "Close-price line chart generated", symbol, started)
        return {"chart": "saved"}

    # Analyst / fundamentals / earnings / news / compare_tickers land in Task 3.
    def _tool_fetch_analyst_view(self, ticker):
        return {"error": "not implemented yet"}

    def _tool_fetch_fundamentals(self, ticker):
        return {"error": "not implemented yet"}

    def _tool_fetch_earnings(self, ticker):
        return {"error": "not implemented yet"}

    def _tool_fetch_news(self, ticker):
        return {"error": "not implemented yet"}

    def _tool_compare_tickers(self, ticker_a, ticker_b):
        return {"error": "not implemented yet"}

    def _tool_finish(self, tickers, period, use_llm_summary):
        cleaned = []
        for ticker in tickers or []:
            symbol = normalize_crypto_symbol(str(ticker or "").strip().upper())
            if symbol and symbol not in cleaned:
                cleaned.append(symbol)
        self.finish_args = {"tickers": cleaned[: self.MAX_TICKERS],
                            "period": str(period or "1y"),
                            "use_llm_summary": bool(use_llm_summary)}
        return {"ok": True}
