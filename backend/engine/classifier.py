"""Map OI change + price change onto build-up / unwinding types."""
from __future__ import annotations

LONG_BUILDUP = "LONG_BUILDUP"
SHORT_BUILDUP = "SHORT_BUILDUP"
SHORT_COVERING = "SHORT_COVERING"
LONG_UNWINDING = "LONG_UNWINDING"
NEUTRAL = "NEUTRAL"

BUY_SIDE = "BUY_SIDE"        # option buying (long build-up)
SELL_SIDE = "SELL_SIDE"      # option writing (short build-up)

PRICE_DEADBAND_PCT = 0.05


def classify(oi_delta: int, price_pct: float) -> str:
    if oi_delta == 0:
        return NEUTRAL
    if abs(price_pct) < PRICE_DEADBAND_PCT:
        return NEUTRAL
    if oi_delta > 0:
        return LONG_BUILDUP if price_pct > 0 else SHORT_BUILDUP
    return SHORT_COVERING if price_pct > 0 else LONG_UNWINDING


def option_side(classification: str) -> str | None:
    """Map an option build-up classification to buy/sell side pressure."""
    if classification == LONG_BUILDUP:
        return BUY_SIDE
    if classification == SHORT_BUILDUP:
        return SELL_SIDE
    return None
