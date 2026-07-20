"""Configurable alert rules evaluated against one completed candle."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping

from src.daily_initialization import ResolvedInstrument


ONCE_PER_DAY = "ONCE_PER_DAY"
EVERY_MATCHING_CANDLE = "EVERY_MATCHING_CANDLE"
VALID_REPEAT_MODES = {ONCE_PER_DAY, EVERY_MATCHING_CANDLE}
DEFAULT_POLICIES = {
    "volume_threshold": EVERY_MATCHING_CANDLE,
    "price_low_limit": ONCE_PER_DAY,
    "price_high_limit": ONCE_PER_DAY,
    "ema20": ONCE_PER_DAY,
}


@dataclass(frozen=True)
class RuleEvaluation:
    symbol: str
    rule_id: str
    alert_type: str
    repeat_mode: str
    outcome: str
    reason: str
    comparator: str
    configured_value: Decimal
    observed_value: Decimal


def load_alert_policies(path: Path) -> dict[str, str]:
    """Load and strictly validate repeat policies for every supported rule."""
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ValueError(f"could not read alert policy file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"alert policy file is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("alert policy file must contain a JSON object")
    unknown = set(payload) - set(DEFAULT_POLICIES)
    missing = set(DEFAULT_POLICIES) - set(payload)
    if unknown:
        raise ValueError(f"unknown alert policies: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"missing alert policies: {', '.join(sorted(missing))}")
    policies: dict[str, str] = {}
    for rule_id, mode in payload.items():
        if mode not in VALID_REPEAT_MODES:
            raise ValueError(
                f"invalid repeat mode for {rule_id}: {mode}; expected "
                f"{' or '.join(sorted(VALID_REPEAT_MODES))}"
            )
        policies[rule_id] = mode
    return policies


def _decimal(
    value: Any, label: str, symbol: str, *, allow_zero: bool = False
) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{symbol} has invalid {label}: {value}") from exc
    if result < 0 or (result == 0 and not allow_zero):
        requirement = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{symbol} {label} must be {requirement}")
    return result


def evaluate_rules(
    instrument: ResolvedInstrument,
    candle: list[Any],
    policies: Mapping[str, str],
) -> list[RuleEvaluation]:
    """Evaluate every configured rule independently for one watchlist row."""
    signal = instrument.signal
    try:
        candle_high = _decimal(candle[2], "candle high", signal.symbol)
        candle_low = _decimal(candle[3], "candle low", signal.symbol)
        candle_close = _decimal(candle[4], "candle close", signal.symbol)
        candle_volume = _decimal(
            candle[5], "candle volume", signal.symbol, allow_zero=True
        )
    except IndexError as exc:
        raise ValueError(f"{signal.symbol} candle does not have the expected fields") from exc

    configured: list[tuple[str, str, Decimal, Decimal, str, bool, str, str]] = []
    low_value = signal.price_low_limit or signal.limit_price
    if signal.volume_threshold:
        threshold = _decimal(signal.volume_threshold, "volume_threshold", signal.symbol)
        configured.append((
            "volume_threshold", "VOLUME_THRESHOLD", threshold, candle_volume, ">=",
            candle_volume >= threshold,
            "candle volume reached volume threshold",
            "candle volume is below volume threshold",
        ))
    if low_value:
        threshold = _decimal(low_value, "price_low_limit", signal.symbol)
        configured.append((
            "price_low_limit", "PRICE_LOW_LIMIT", threshold, candle_low, "<=",
            candle_low <= threshold,
            "candle low reached price low limit",
            "candle low is above price low limit",
        ))
    if signal.price_high_limit:
        threshold = _decimal(signal.price_high_limit, "price_high_limit", signal.symbol)
        configured.append((
            "price_high_limit", "PRICE_HIGH_LIMIT", threshold, candle_high, ">=",
            candle_high >= threshold,
            "candle high reached price high limit",
            "candle high is below price high limit",
        ))
    if signal.ema20:
        threshold = _decimal(signal.ema20, "ema20", signal.symbol)
        matched = candle_low <= threshold <= candle_high
        configured.append((
            "ema20", "EMA20_CROSS", threshold, candle_close, "LOW<=EMA20<=HIGH",
            matched,
            "candle crossed or touched supplied EMA20",
            "candle did not cross supplied EMA20",
        ))

    return [
        RuleEvaluation(
            symbol=signal.symbol,
            rule_id=rule_id,
            alert_type=alert_type,
            repeat_mode=policies[rule_id],
            outcome="ENTER" if matched else "WAIT",
            reason=matched_reason if matched else wait_reason,
            comparator=comparator,
            configured_value=threshold,
            observed_value=observed,
        )
        for (
            rule_id,
            alert_type,
            threshold,
            observed,
            comparator,
            matched,
            matched_reason,
            wait_reason,
        ) in configured
    ]
