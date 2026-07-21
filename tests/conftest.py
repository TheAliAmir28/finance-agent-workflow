import pandas as pd
import pytest

from memory.store import MemoryStore
from agent_trace import AgentTracer


@pytest.fixture
def memory():
    return MemoryStore()


@pytest.fixture
def tracer():
    return AgentTracer()


@pytest.fixture
def price_data():
    dates = pd.date_range("2025-01-02", periods=60, freq="B")
    closes = [100 + i * 0.5 for i in range(60)]
    return pd.DataFrame({"Close": closes}, index=dates)
