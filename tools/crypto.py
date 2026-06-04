CRYPTO_ASSETS = {
    "BTC": {"symbol": "BTC-USD", "name": "Bitcoin", "domain": "bitcoin.org"},
    "ETH": {"symbol": "ETH-USD", "name": "Ethereum", "domain": "ethereum.org"},
    "SOL": {"symbol": "SOL-USD", "name": "Solana", "domain": "solana.com"},
    "DOGE": {"symbol": "DOGE-USD", "name": "Dogecoin", "domain": "dogecoin.com"},
    "ADA": {"symbol": "ADA-USD", "name": "Cardano", "domain": "cardano.org"},
    "XRP": {"symbol": "XRP-USD", "name": "XRP", "domain": "xrpl.org"},
    "AVAX": {"symbol": "AVAX-USD", "name": "Avalanche", "domain": "avax.network"},
    "LINK": {"symbol": "LINK-USD", "name": "Chainlink", "domain": "chain.link"},
    "LTC": {"symbol": "LTC-USD", "name": "Litecoin", "domain": "litecoin.org"},
    "BCH": {"symbol": "BCH-USD", "name": "Bitcoin Cash", "domain": "bitcoincash.org"},
}

CRYPTO_NAME_TO_SYMBOL = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "ether": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "cardano": "ADA",
    "ada": "ADA",
    "xrp": "XRP",
    "ripple": "XRP",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "chainlink": "LINK",
    "link": "LINK",
    "litecoin": "LTC",
    "ltc": "LTC",
    "bitcoin cash": "BCH",
    "bch": "BCH",
}


def normalize_crypto_symbol(symbol):
    cleaned = str(symbol or "").strip().upper()
    if cleaned.endswith("-USD"):
        base = cleaned.removesuffix("-USD")
        return cleaned if base in CRYPTO_ASSETS else cleaned

    asset = CRYPTO_ASSETS.get(cleaned)
    return asset["symbol"] if asset else cleaned


def is_crypto_symbol(symbol):
    cleaned = str(symbol or "").strip().upper()
    if cleaned.endswith("-USD"):
        cleaned = cleaned.removesuffix("-USD")
    return cleaned in CRYPTO_ASSETS


def crypto_display_symbol(symbol):
    cleaned = str(symbol or "").strip().upper()
    return cleaned.removesuffix("-USD")


def crypto_domain(symbol):
    cleaned = crypto_display_symbol(symbol)
    asset = CRYPTO_ASSETS.get(cleaned)
    return asset.get("domain") if asset else None
