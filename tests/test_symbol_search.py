from unittest.mock import patch, MagicMock

from tools import symbol_search


def _mock_search(quotes):
    search = MagicMock()
    search.quotes = quotes
    return MagicMock(return_value=search)


def setup_function():
    symbol_search._cache.clear()


def test_search_returns_normalized_results():
    quotes = [
        {"symbol": "nvda", "quoteType": "EQUITY", "longname": "NVIDIA Corporation",
         "exchDisp": "NASDAQ", "typeDisp": "Equity"},
        {"symbol": "NVDA24.MX", "quoteType": "OPTION"},  # filtered out
    ]
    with patch.object(symbol_search.yf, "Search", _mock_search(quotes)):
        results = symbol_search.search_symbols("nvidia")
    assert results == [{"symbol": "NVDA", "name": "NVIDIA Corporation",
                        "exchange": "NASDAQ", "type": "Equity"}]


def test_blank_query_returns_empty_without_network():
    with patch.object(symbol_search.yf, "Search", side_effect=AssertionError("no network")):
        assert symbol_search.search_symbols("   ") == []


def test_lookup_failure_returns_empty_and_is_not_cached():
    with patch.object(symbol_search.yf, "Search", side_effect=RuntimeError("boom")):
        assert symbol_search.search_symbols("nvidia") == []
    assert symbol_search._cache == {}


def test_results_are_cached_by_query():
    quotes = [{"symbol": "AAPL", "quoteType": "EQUITY", "longname": "Apple Inc.",
               "exchDisp": "NASDAQ", "typeDisp": "Equity"}]
    mock = _mock_search(quotes)
    with patch.object(symbol_search.yf, "Search", mock):
        symbol_search.search_symbols("apple")
        symbol_search.search_symbols("APPLE")
    assert mock.call_count == 1
