from __future__ import annotations

from datetime import datetime, timezone

import yfinance as yf
from tools.crypto import normalize_crypto_symbol


def _extract_news_item(raw_item):
    content = raw_item.get("content", raw_item) if isinstance(raw_item, dict) else {}

    title = content.get("title") or raw_item.get("title")
    if not title:
        return None

    publisher = (
        content.get("provider", {}).get("displayName")
        if isinstance(content.get("provider"), dict)
        else None
    ) or content.get("publisher") or raw_item.get("publisher") or "Market news"

    canonical_url = content.get("canonicalUrl")
    click_through_url = content.get("clickThroughUrl")
    link = canonical_url.get("url") if isinstance(canonical_url, dict) else None
    if not link and isinstance(click_through_url, dict):
        link = click_through_url.get("url")
    link = link or content.get("link") or raw_item.get("link")

    published_at = content.get("pubDate") or raw_item.get("providerPublishTime")
    published_label = "Recent"

    if isinstance(published_at, (int, float)):
        published_label = datetime.fromtimestamp(published_at, tz=timezone.utc).strftime("%b %d, %Y")
    elif isinstance(published_at, str) and published_at:
        try:
            published_label = datetime.fromisoformat(published_at.replace("Z", "+00:00")).strftime("%b %d, %Y")
        except ValueError:
            published_label = published_at[:10]

    summary = content.get("summary") or raw_item.get("summary")

    return {
        "title": str(title).strip(),
        "publisher": str(publisher).strip(),
        "link": link,
        "published": published_label,
        "summary": str(summary).strip() if summary else None,
    }


def fetch_stock_news(ticker, limit=3):
    symbol = normalize_crypto_symbol(ticker)

    try:
        raw_news = yf.Ticker(symbol).news or []
    except Exception:
        return []

    news_items = []
    for raw_item in raw_news:
        item = _extract_news_item(raw_item)
        if item:
            news_items.append(item)
        if len(news_items) >= limit:
            break

    return news_items
