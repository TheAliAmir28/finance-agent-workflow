import re
from calendar import monthrange
from datetime import date
from tools.crypto import CRYPTO_NAME_TO_SYMBOL, normalize_crypto_symbol

MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTH_STOP_WORDS = {month.upper() for month in MONTH_NAMES}

COMPANY_TO_TICKER = {
    "apple": "AAPL",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "netflix": "NFLX",
    "amd": "AMD",
}

def _parse_date_phrase(raw_phrase, use_month_end=False):
    phrase = raw_phrase.strip(" ,.;")

    iso_match = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", phrase)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = int(iso_match.group(3)) if iso_match.group(3) else 1
        if use_month_end and not iso_match.group(3):
            day = monthrange(year, month)[1]
        return date(year, month, day)

    compact_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", phrase)
    if compact_match:
        month = int(compact_match.group(1))
        day = int(compact_match.group(2))
        year = int(compact_match.group(3))
        return date(year, month, day)

    parts = phrase.lower().replace(",", " ").split()
    if len(parts) < 2:
        raise ValueError(f"Could not parse date: {raw_phrase}")

    month = MONTH_NAMES.get(parts[0])
    if month is None:
        raise ValueError(f"Could not parse date: {raw_phrase}")

    day = None
    year = None
    for part in parts[1:]:
        cleaned = part.strip(" ,.;")
        if not cleaned.isdigit():
            continue

        value = int(cleaned)
        if value > 31:
            year = value
        elif day is None:
            day = value

    if year is None:
        raise ValueError(f"Could not parse date: {raw_phrase}")

    if day is None:
        day = monthrange(year, month)[1] if use_month_end else 1

    return date(year, month, day)

def _parse_custom_date_range(text):
    range_match = re.search(
        r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:with|no)\s+summary\b|$)",
        text,
    )
    if not range_match:
        return None

    start_date = _parse_date_phrase(range_match.group(1), use_month_end=False)
    end_date = _parse_date_phrase(range_match.group(2), use_month_end=True)

    if start_date >= end_date:
        raise ValueError("Start date must be before end date.")

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "period": f"{start_date.isoformat()} to {end_date.isoformat()}",
    }

class Planner:
    def __init__(self):
        pass

    # create_plan: Converts user request into a list of tasks
    def create_plan(self, user_input):
        # lowercase entire input for easier keyword detection
        text = user_input.lower()

        # LLM summary mode will be ON by default. Manual request will be needed to turn it off.
        use_llm_summary = True

        # Explicit user control over LLM summary mode
        if "no summary" in text:
            use_llm_summary = False
        elif "with summary" in text:
            use_llm_summary = True

        # Get tickers
        tickers = []

        # First pass: detect company names from natural language
        for company_name, ticker_symbol in COMPANY_TO_TICKER.items():
            if company_name in text:
                if ticker_symbol not in tickers:
                    tickers.append(ticker_symbol)

        crypto_name_spans = []
        crypto_name_matches = []
        for crypto_name, crypto_symbol in sorted(
            CRYPTO_NAME_TO_SYMBOL.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            for match in re.finditer(rf"(?<![\w-]){re.escape(crypto_name)}(?![\w-])", text):
                start, end = match.span()
                overlaps_existing = any(start < span_end and end > span_start for span_start, span_end in crypto_name_spans)
                if overlaps_existing:
                    continue
                crypto_name_spans.append((start, end))
                crypto_name_matches.append((start, crypto_symbol))

        for _, crypto_symbol in sorted(crypto_name_matches):
            if crypto_symbol not in tickers:
                tickers.append(crypto_symbol)

        # Second pass: detect direct ticker symbols from user input
        upper_text = user_input.upper()
        tokens = upper_text.replace(",", " ").split()

        # Words that should NOT be treated as stock tickers
        # This prevents phrases like "WITH" or "SUMMARY" from being misread as symbols
        stop_words = {
            "ANALYZE", "COMPARE", "CHECK", "FOR", "OVER", "LAST", "PAST",
            "YEAR", "YEARS", "MONTH", "MONTHS", "DAY", "DAYS",
            "AND", "THE", "PLEASE", "STOCK", "STOCKS", "ME", "MY",
            "WITH", "SUMMARY", "NO", "FROM", "TO", "CASH", "CRYPTO", "USD",
        } | MONTH_STOP_WORDS

        for token in tokens:
            # Remove punctuation around the token
            cleaned_token = token.strip("()[]{}:;.!?\"'")
            cleaned_token_lower = cleaned_token.lower()
            normalized_crypto_token = normalize_crypto_symbol(cleaned_token)

            # Skip tokens that are already known company names
            if cleaned_token_lower in COMPANY_TO_TICKER or cleaned_token_lower in CRYPTO_NAME_TO_SYMBOL:
                continue

            is_stock_symbol = 1 <= len(cleaned_token) <= 5 and cleaned_token.isalpha()
            is_crypto_pair = (
                normalized_crypto_token.endswith("-USD")
                and 5 <= len(normalized_crypto_token) <= 9
            )

            if (is_stock_symbol or is_crypto_pair) and cleaned_token not in stop_words:
                ticker_symbol = normalized_crypto_token if normalized_crypto_token.endswith("-USD") else cleaned_token
                if ticker_symbol not in tickers:
                    tickers.append(ticker_symbol)

        # Get period
        period = "1y"  # default period
        custom_range = _parse_custom_date_range(text)

        words = text.split()

        # Case 1: compact periods like "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"
        compact_period = re.search(r"\b(\d+)(d|mo|y)\b", text)
        if compact_period:
            period = f"{compact_period.group(1)}{compact_period.group(2)}"

        # Case 2: phrases like "last year", "past year", "last month", "past month"
        for i, word in enumerate(words):
            if word in {"last", "past"} and i + 1 < len(words):
                next_word = words[i + 1]

                if "year" in next_word:
                    period = "1y"
                elif "month" in next_word:
                    period = "1mo"
                elif "day" in next_word:
                    period = "1d"

        # Case 3: phrases like "last 6 months", "past 2 years"
        for i, word in enumerate(words):
            if word in {"last", "past"} and i + 2 < len(words):
                number_word = words[i + 1]
                unit_word = words[i + 2]

                if number_word.isdigit():
                    if "year" in unit_word:
                        period = f"{number_word}y"
                    elif "month" in unit_word:
                        period = f"{number_word}mo"
                    elif "day" in unit_word:
                        period = f"{number_word}d"

        # Case 4: original support for "1 year", "6 months"
        for i, word in enumerate(words):
            if word.isdigit() and i + 1 < len(words):
                unit = words[i + 1]

                if "year" in unit:
                    period = f"{word}y"
                elif "month" in unit:
                    period = f"{word}mo"
                elif "day" in unit:
                    period = f"{word}d"

        if custom_range:
            period = custom_range["period"]

        # Validate tickers
        # At least one ticker is required
        if len(tickers) == 0:
            raise ValueError("No valid ticker symbols found in input.")
        # System will take at most two tickers
        if len(tickers) > 2:
            raise ValueError("Please specify at most two tickers.")

        # Construct task plan
        tasks = []

        for ticker in tickers:
            # Get historical price data
            fetch_task = {"task" : "fetch_data", "ticker" : ticker, "period" : period}
            if custom_range:
                fetch_task["start_date"] = custom_range["start_date"]
                fetch_task["end_date"] = custom_range["end_date"]
            tasks.append(fetch_task)
            # Calculate performance metrics
            tasks.append({"task" : "compute_metrics", "ticker" : ticker})
        # If exactly two stocks were provided, then compare them
        if len(tickers) == 2:
            tasks.append({"task" : "compare_metrics"})
        # Return both the task list and the LLM summary control flag
        return {"tasks": tasks, "use_llm_summary": use_llm_summary}
