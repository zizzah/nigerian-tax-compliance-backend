"""
FX Rate Service
Location: app/services/fx_rates.py

Fetches indicative NGN exchange rates with a 1-hour in-memory cache.
Uses the free exchangerate-api.com endpoint (no API key needed).
"""
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Simple in-process cache — resets on server restart
_cache: dict = {"rates": {}, "updated_at": None}

_RATE_API_URL = "https://api.exchangerate-api.com/v4/latest/NGN"

# Hardcoded fallback rates (approximate, Mar 2026)
_FALLBACK_RATES = {
    "USD": 0.00065,
    "GBP": 0.00052,
    "EUR": 0.00060,
    "NGN": 1.0,
}


def get_fx_rates() -> dict[str, float]:
    """
    Return NGN exchange rates (units of foreign currency per 1 NGN).
    Results are cached for 1 hour.
    """
    now = datetime.now(timezone.utc)
    if _cache["updated_at"] and (now - _cache["updated_at"]) < timedelta(hours=1):
        return _cache["rates"]

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(_RATE_API_URL)
            data = r.json()
            # The API returns rates relative to NGN as base (e.g. USD rate = USD per NGN)
            base_rates = data.get("rates", {})
            rates = {
                "USD": float(base_rates.get("USD", _FALLBACK_RATES["USD"])),
                "GBP": float(base_rates.get("GBP", _FALLBACK_RATES["GBP"])),
                "EUR": float(base_rates.get("EUR", _FALLBACK_RATES["EUR"])),
                "NGN": 1.0,
            }
            _cache["rates"] = rates
            _cache["updated_at"] = now
            logger.info("FX rates refreshed from API")
            return rates
    except Exception as e:
        logger.warning(f"FX rate fetch failed ({e}), using fallback rates")
        return _FALLBACK_RATES.copy()


def convert_to_ngn(amount: float, currency: str) -> float:
    """Convert an amount in foreign currency to NGN."""
    if currency.upper() == "NGN":
        return amount
    rates = get_fx_rates()
    rate = rates.get(currency.upper(), 1.0)
    # rate = foreign per NGN → NGN = amount / rate
    return amount / rate if rate > 0 else amount


def get_exchange_rate(from_currency: str, to_currency: str = "NGN") -> float:
    """Get exchange rate from one currency to another."""
    rates = get_fx_rates()
    if from_currency.upper() == to_currency.upper():
        return 1.0
    from_rate = rates.get(from_currency.upper(), 1.0)
    to_rate = rates.get(to_currency.upper(), 1.0)
    return to_rate / from_rate if from_rate > 0 else 1.0