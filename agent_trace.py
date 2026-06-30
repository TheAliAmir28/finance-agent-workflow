import time

"""
Lightweight execution tracer.

The planner and agent record every step they take here — with real wall-clock
timing and an ok/warn/skip/error status — so the UI can replay the agent loop
as a live, transparent trace instead of a black box.
"""


class AgentTracer:
    # Maps each tool to the high-level pipeline stage it belongs to. Keeps the
    # agent code terse and lets the UI light up the Planner -> Agent -> Tools
    # pipeline as work flows through it.
    STAGE_FOR_TOOL = {
        "planner":      "Planner",
        "data":         "Market Data",
        "metrics":      "Analytics",
        "charts":       "Analytics",
        "analyst":      "Enrichment",
        "fundamentals": "Enrichment",
        "earnings":     "Enrichment",
        "news":         "Enrichment",
        "compare":      "Synthesis",
    }

    def __init__(self, on_record=None):
        self._events = []
        self._seq = 0
        # Optional callback invoked with each event as it is recorded, so a
        # background job can stream steps to the browser in real time.
        self._on_record = on_record

    @staticmethod
    def now():
        """Start marker for manual timing of a step."""
        return time.perf_counter()

    @staticmethod
    def elapsed_ms(start):
        return (time.perf_counter() - start) * 1000

    def record(self, tool, label, status="ok", detail="", ticker=None, duration_ms=None):
        """Append one executed step to the trace.

        status is one of: "ok", "warn" (ran but data unavailable),
        "skip" (not applicable), or "error" (the call failed).
        """
        self._seq += 1
        event = {
            "seq": self._seq,
            "tool": tool,
            "stage": self.STAGE_FOR_TOOL.get(tool, "Agent"),
            "label": label,
            "ticker": ticker,
            "status": status,
            "detail": detail or "",
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        }
        self._events.append(event)
        if self._on_record is not None:
            # Streaming must never break a run — swallow any listener error.
            try:
                self._on_record(dict(event))
            except Exception:
                pass

    @property
    def events(self):
        return list(self._events)

    def export(self):
        """Serialize the trace plus rolled-up summary stats for the UI."""
        total_ms = sum(event["duration_ms"] or 0 for event in self._events)
        statuses = [event["status"] for event in self._events]

        tools_used = []
        for event in self._events:
            if event["tool"] not in tools_used:
                tools_used.append(event["tool"])

        stage_order = ["Planner", "Market Data", "Analytics", "Enrichment", "Synthesis"]
        stages = [stage for stage in stage_order if any(e["stage"] == stage for e in self._events)]

        return {
            "events": self.events,
            "stages": stages,
            "summary": {
                "step_count": len(self._events),
                "tool_count": len(tools_used),
                "total_ms": round(total_ms, 1),
                "ok": statuses.count("ok"),
                "warn": statuses.count("warn"),
                "skip": statuses.count("skip"),
                "error": statuses.count("error"),
            },
        }
