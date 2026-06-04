from datetime import date, datetime, timezone

import yfinance as yf


def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_call(method, *args, **kwargs):
    if method is None:
        return None

    try:
        return method(*args, **kwargs)
    except Exception:
        return None


def _safe_method(obj, name, *args, **kwargs):
    return _safe_call(getattr(obj, name, None), *args, **kwargs)


def _timestamp_to_iso(value):
    try:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _to_iso_date(value):
    if value is None:
        return None

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def _to_date(value):
    iso_date = _to_iso_date(value)
    if not iso_date:
        return None

    try:
        return datetime.fromisoformat(iso_date).date()
    except ValueError:
        return None


def _normalize_key(key):
    return str(key).strip().lower().replace("_", " ").replace("-", " ")


def _get_any(mapping, names):
    if not mapping:
        return None

    normalized = {_normalize_key(key): value for key, value in dict(mapping).items()}
    for name in names:
        value = normalized.get(_normalize_key(name))
        if value is not None:
            return value

    return None


def _surprise_ratio(actual, estimate, fallback=None):
    fallback_value = _as_float(fallback)
    if fallback_value is not None:
        return fallback_value / 100 if abs(fallback_value) > 1 else fallback_value

    actual = _as_float(actual)
    estimate = _as_float(estimate)
    if actual is None or estimate in (None, 0):
        return None

    return (actual - estimate) / abs(estimate)


def _result_label(actual, estimate):
    actual = _as_float(actual)
    estimate = _as_float(estimate)
    if actual is None or estimate is None:
        return None
    if actual > estimate:
        return "beat"
    if actual < estimate:
        return "miss"
    return "met"


def _fiscal_year_end_month(info):
    fiscal_year_end = (
        _timestamp_to_iso(info.get("lastFiscalYearEnd"))
        or _timestamp_to_iso(info.get("nextFiscalYearEnd"))
    )
    fiscal_year_end_date = _to_date(fiscal_year_end)
    return fiscal_year_end_date.month if fiscal_year_end_date else 12


def _fiscal_period_from_quarter_end(value, fiscal_year_end_month=12):
    quarter_end = _to_date(value)
    if not quarter_end:
        return None

    fiscal_start_month = fiscal_year_end_month % 12 + 1
    fiscal_quarter = ((quarter_end.month - fiscal_start_month) % 12) // 3 + 1
    fiscal_year = quarter_end.year
    if quarter_end.month > fiscal_year_end_month:
        fiscal_year += 1
    return f"Q{fiscal_quarter} {fiscal_year}"


def _latest_history_entry(history):
    if history is None:
        return None

    if hasattr(history, "to_dict"):
        rows = history.reset_index().to_dict("records")
    elif isinstance(history, dict):
        rows = history.get("earningsHistory") or history.get("history") or []
    else:
        rows = history

    if not rows:
        return None

    def sort_key(row):
        period = _get_any(row, ["quarter", "period", "date", "earningsDate", "index"])
        return _to_date(period) or date.min

    try:
        return sorted(rows, key=sort_key)[-1]
    except Exception:
        return rows[0]


def _earnings_dates_snapshot(earnings_dates):
    if earnings_dates is None or not hasattr(earnings_dates, "empty") or earnings_dates.empty:
        return {}

    now = datetime.now(timezone.utc)
    rows = []
    for index, row in earnings_dates.iterrows():
        event_date = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        rows.append((event_date, row.to_dict()))

    past_rows = [item for item in rows if item[0] <= now]
    future_rows = [item for item in rows if item[0] > now]

    snapshot = {}
    if past_rows:
        event_date, row = sorted(past_rows, key=lambda item: item[0])[-1]
        snapshot["last_report_date"] = event_date.date().isoformat()
        snapshot["eps_estimate"] = _as_float(_get_any(row, ["EPS Estimate"]))
        snapshot["eps_actual"] = _as_float(_get_any(row, ["Reported EPS"]))
        snapshot["eps_surprise"] = _surprise_ratio(
            snapshot["eps_actual"],
            snapshot["eps_estimate"],
            _get_any(row, ["Surprise(%)", "Surprise %"]),
        )

    if future_rows:
        event_date, row = sorted(future_rows, key=lambda item: item[0])[0]
        snapshot["next_call_date"] = event_date.date().isoformat()
        snapshot["next_call_date_is_estimate"] = True
        snapshot["next_eps_estimate"] = _as_float(_get_any(row, ["EPS Estimate"]))

    return snapshot


def _history_snapshot(history, info):
    entry = _latest_history_entry(history)
    if not entry:
        return {}

    fiscal_year_end_month = _fiscal_year_end_month(info)
    quarter_end = _get_any(entry, ["quarter", "period", "quarterEndDate", "fiscalDateEnding"])
    report_date = _get_any(entry, ["earningsDate", "reportedDate", "reportDate", "date"])
    eps_actual = _as_float(_get_any(entry, ["epsActual", "actualEps", "reportedEPS", "reportedEps"]))
    eps_estimate = _as_float(_get_any(entry, ["epsEstimate", "estimatedEPS", "epsMeanEstimate", "epsEstimateAvg"]))
    revenue_actual = _as_float(_get_any(entry, [
        "revenueActual",
        "actualRevenue",
        "reportedRevenue",
        "revenue",
        "totalRevenue",
    ]))
    revenue_estimate = _as_float(_get_any(entry, [
        "revenueEstimate",
        "estimatedRevenue",
        "revenueMeanEstimate",
        "revenueEstimateAvg",
        "estimatedRevenueAvg",
        "revenueAvg",
    ]))

    return {
        "last_report_date": _to_iso_date(report_date),
        "quarter_end_date": _to_iso_date(quarter_end),
        "fiscal_period": _fiscal_period_from_quarter_end(quarter_end, fiscal_year_end_month),
        "eps_actual": eps_actual,
        "eps_estimate": eps_estimate,
        "eps_surprise": _surprise_ratio(
            eps_actual,
            eps_estimate,
            _get_any(entry, ["surprisePercent", "epsSurprisePercent", "surprise(%)"]),
        ),
        "revenue_actual": revenue_actual,
        "revenue_estimate": revenue_estimate,
        "revenue_estimate_is_matched": revenue_estimate is not None,
        "revenue_surprise": _surprise_ratio(revenue_actual, revenue_estimate),
    }


def _calendar_next_date(calendar, info):
    today = datetime.now(timezone.utc).date()
    timestamp_date = (
        _timestamp_to_iso(info.get("earningsTimestamp"))
        or _timestamp_to_iso(info.get("earningsTimestampStart"))
        or _timestamp_to_iso(info.get("earningsTimestampEnd"))
    )
    timestamp = _to_date(timestamp_date)
    if timestamp and timestamp >= today:
        return {
            "date": timestamp_date,
            "is_estimate": True,
        }

    if calendar is None:
        return None

    if hasattr(calendar, "to_dict"):
        calendar = calendar.to_dict()

    earnings_date = _get_any(calendar, ["Earnings Date", "earningsDate"])
    if isinstance(earnings_date, (list, tuple)) and earnings_date:
        earnings_date = earnings_date[0]

    calendar_date = _to_iso_date(earnings_date)
    parsed = _to_date(calendar_date)
    if parsed and parsed >= today:
        return {
            "date": calendar_date,
            "is_estimate": True,
        }

    return None


def _get_dataframe_value(frame, row_names, column_date=None):
    if frame is None or not hasattr(frame, "empty") or frame.empty:
        return None

    normalized_rows = {_normalize_key(index): index for index in frame.index}
    row_key = None
    for row_name in row_names:
        row_key = normalized_rows.get(_normalize_key(row_name))
        if row_key is not None:
            break

    if row_key is None:
        return None

    series = frame.loc[row_key]
    if column_date is not None:
        target = _to_date(column_date)
        for column in series.index:
            if _to_date(column) == target:
                return _as_float(series[column])

    for value in series:
        parsed = _as_float(value)
        if parsed is not None:
            return parsed

    return None


def _financials_snapshot(ticker_client, quarter_end_date):
    quarterly_income = _safe_method(ticker_client, "get_income_stmt", freq="quarterly")
    if quarterly_income is None:
        quarterly_income = _safe_method(ticker_client, "get_quarterly_income_stmt")

    return {
        "revenue_actual": _get_dataframe_value(
            quarterly_income,
            ["Total Revenue", "TotalRevenue"],
            quarter_end_date,
        ),
    }


def _revenue_estimate_snapshot(ticker_client):
    revenue_estimate = _safe_method(ticker_client, "get_revenue_estimate")
    if revenue_estimate is None:
        return {}

    if hasattr(revenue_estimate, "empty"):
        if revenue_estimate.empty:
            return {}
        rows = revenue_estimate.reset_index().to_dict("records")
    elif isinstance(revenue_estimate, dict):
        rows = revenue_estimate.get("revenueEstimate") or revenue_estimate.get("estimate") or []
        if isinstance(rows, dict):
            rows = [rows]
    else:
        rows = revenue_estimate

    if not rows:
        return {}

    preferred_rows = []
    fallback_rows = []
    for row in rows:
        period = str(_get_any(row, ["period", "index", "quarter", "date"]) or "").lower()
        if "year" in period or period.endswith("y"):
            fallback_rows.append(row)
        else:
            preferred_rows.append(row)

    for row in preferred_rows + fallback_rows:
        estimate = _as_float(_get_any(row, [
            "avg",
            "average",
            "mean",
            "revenueEstimateAvg",
            "estimatedRevenueAvg",
            "revenueMeanEstimate",
            "estimatedRevenue",
            "revenueEstimate",
        ]))
        if estimate is not None:
            return {
                "revenue_estimate": estimate,
                "revenue_estimate_is_matched": False,
            }

    return {}


def fetch_earnings_snapshot(ticker):
    """
    Fetch last reported earnings and next earnings call date from yfinance.
    Data availability varies by ticker and Yahoo Finance response shape.
    """
    symbol = ticker.upper()
    ticker_client = yf.Ticker(symbol)

    try:
        info = ticker_client.get_info() or {}
    except Exception as exc:
        return {
            "ticker": symbol,
            "available": False,
            "error": str(exc),
        }

    earnings_dates = _safe_method(ticker_client, "get_earnings_dates", limit=12)
    earnings_history = _safe_method(ticker_client, "get_earnings_history")
    calendar = _safe_method(ticker_client, "get_calendar")

    snapshot = {
        "ticker": symbol,
        "available": True,
        "last_report_date": None,
        "last_report_date_is_period_end": False,
        "next_call_date": None,
        "next_call_date_is_estimate": False,
        "quarter_end_date": None,
        "fiscal_period": None,
        "eps_actual": None,
        "eps_estimate": None,
        "eps_surprise": None,
        "eps_result": None,
        "revenue_actual": None,
        "revenue_estimate": None,
        "revenue_estimate_is_matched": False,
        "revenue_surprise": None,
        "revenue_result": None,
    }

    next_call = _calendar_next_date(calendar, info)
    if next_call:
        snapshot["next_call_date"] = next_call["date"]
        snapshot["next_call_date_is_estimate"] = next_call["is_estimate"]

    for source in (
        _earnings_dates_snapshot(earnings_dates),
        _history_snapshot(earnings_history, info),
    ):
        for key, value in source.items():
            if value is not None:
                if key == "last_report_date" and snapshot.get(key) is not None:
                    continue
                snapshot[key] = value

    for key, value in _financials_snapshot(ticker_client, snapshot["quarter_end_date"]).items():
        if snapshot.get(key) is None and value is not None:
            snapshot[key] = value

    for key, value in _revenue_estimate_snapshot(ticker_client).items():
        if snapshot.get(key) in (None, False) and value is not None:
            snapshot[key] = value

    if snapshot.get("last_report_date") is None and snapshot.get("quarter_end_date") is not None:
        snapshot["last_report_date"] = snapshot["quarter_end_date"]
        snapshot["last_report_date_is_period_end"] = True

    if not snapshot.get("revenue_estimate_is_matched"):
        snapshot["revenue_surprise"] = None

    snapshot["eps_result"] = _result_label(snapshot["eps_actual"], snapshot["eps_estimate"])
    snapshot["revenue_result"] = (
        _result_label(snapshot["revenue_actual"], snapshot["revenue_estimate"])
        if snapshot.get("revenue_estimate_is_matched")
        else None
    )

    key_values = [
        snapshot["last_report_date"],
        snapshot["next_call_date"],
        snapshot["eps_actual"],
        snapshot["eps_estimate"],
        snapshot["revenue_actual"],
        snapshot["revenue_estimate"],
    ]
    snapshot["available"] = any(value is not None for value in key_values)

    return snapshot
