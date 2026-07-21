"""Stateful cumulative-score alert based on price change and volume multiple."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CumulativeScorePolicy:
    alert_threshold: Decimal
    green_threshold: Decimal
    display_decimals: int


@dataclass(frozen=True)
class CumulativeScoreResult:
    trading_date: str
    strategy_id: str
    symbol: str
    candle_start: str
    previous_close: Decimal | None
    current_close: Decimal
    candle_volume: Decimal
    volume_threshold: Decimal
    delta_price_pct: Decimal | None
    volume_multiple: Decimal | None
    score_contribution: Decimal | None
    cumulative_score: Decimal
    harmonic_mean: Decimal | None
    alert_count: int
    alert_sent: bool
    score_history: tuple[Decimal, ...]
    harmonic_history: tuple[Decimal, ...]

    @property
    def is_baseline(self) -> bool:
        return self.delta_price_pct is None

    @property
    def is_new_alert(self) -> bool:
        return self.alert_sent and self.alert_count == 1


@dataclass
class _SymbolState:
    last_close: Decimal
    cumulative_score: Decimal
    alert_count: int
    score_history: list[Decimal]
    harmonic_history: list[Decimal]


def load_cumulative_score_policy(path: Path) -> CumulativeScorePolicy:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ValueError(f"could not read cumulative-score policy {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"cumulative-score policy is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("cumulative-score policy must contain a JSON object")
    try:
        alert_threshold = Decimal(str(payload["alert_threshold"]))
        green_threshold = Decimal(str(payload["green_threshold"]))
        display_decimals = int(payload.get("display_decimals", 2))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("cumulative-score policy contains invalid values") from exc
    if alert_threshold < 0:
        raise ValueError("cumulative-score alert_threshold cannot be negative")
    if green_threshold <= alert_threshold:
        raise ValueError("cumulative-score green_threshold must exceed alert_threshold")
    if not 0 <= display_decimals <= 6:
        raise ValueError("cumulative-score display_decimals must be between 0 and 6")
    return CumulativeScorePolicy(alert_threshold, green_threshold, display_decimals)


def signed_harmonic_mean(
    delta_price_pct: Decimal, volume_multiple: Decimal
) -> Decimal:
    """Return a zero-safe signed harmonic mean of price delta and volume multiple."""
    if delta_price_pct == 0 or volume_multiple == 0:
        return Decimal("0")
    magnitude = Decimal("2") / (
        (Decimal("1") / abs(delta_price_pct))
        + (Decimal("1") / volume_multiple)
    )
    return magnitude if delta_price_pct > 0 else -magnitude


class CumulativeScoreStore:
    """Persist calculations and restore exact per-symbol state after restart."""

    FIELDS = [
        "trading_date",
        "strategy_id",
        "symbol",
        "candle_start",
        "previous_close",
        "current_close",
        "candle_volume",
        "volume_threshold",
        "delta_price_pct",
        "volume_multiple",
        "score_contribution",
        "cumulative_score",
        "harmonic_mean",
        "alert_count",
        "alert_sent",
    ]

    def __init__(
        self, directory: Path, trading_date: str, policy: CumulativeScorePolicy
    ) -> None:
        self.trading_date = trading_date
        self.policy = policy
        self.path = directory / f"cumulative_scores_{trading_date}.csv"
        self._keys: set[tuple[str, str, str]] = set()
        self._states: dict[tuple[str, str], _SymbolState] = {}
        self._load()

    @staticmethod
    def _decimal(value: Any, label: str, *, allow_zero: bool = False) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid {label}: {value}") from exc
        if result < 0 or (result == 0 and not allow_zero):
            requirement = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{label} must be {requirement}")
        return result

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if (reader.fieldnames or []) != self.FIELDS:
                    raise ValueError(
                        f"cumulative-score output has an unsupported schema: {self.path}"
                    )
                for row in reader:
                    strategy = row["strategy_id"]
                    symbol = row["symbol"]
                    candle_start = row["candle_start"]
                    self._keys.add((strategy, symbol, candle_start))
                    identity = (strategy, symbol)
                    previous = self._states.get(identity)
                    scores = list(previous.score_history) if previous else []
                    harmonics = list(previous.harmonic_history) if previous else []
                    if row["delta_price_pct"]:
                        scores.append(Decimal(row["cumulative_score"]))
                    if row["harmonic_mean"]:
                        harmonics.append(Decimal(row["harmonic_mean"]))
                    self._states[identity] = _SymbolState(
                        last_close=Decimal(row["current_close"]),
                        cumulative_score=Decimal(row["cumulative_score"]),
                        alert_count=int(row["alert_count"]),
                        score_history=scores,
                        harmonic_history=harmonics,
                    )
        except (OSError, KeyError, InvalidOperation, ValueError) as exc:
            if isinstance(exc, ValueError) and "unsupported schema" in str(exc):
                raise
            raise ValueError(f"could not load cumulative-score output {self.path}: {exc}") from exc

    def process(
        self,
        strategy_id: str,
        symbol: str,
        candle: list[Any],
        volume_threshold_value: str,
    ) -> CumulativeScoreResult | None:
        candle_start = str(candle[0])
        key = (strategy_id, symbol, candle_start)
        if key in self._keys:
            return None
        try:
            current_close = self._decimal(candle[4], "current close")
            candle_volume = self._decimal(candle[5], "candle volume", allow_zero=True)
        except IndexError as exc:
            raise ValueError(f"{symbol} candle does not have close and volume") from exc
        volume_threshold = self._decimal(
            volume_threshold_value, f"{symbol} volume_threshold"
        )
        identity = (strategy_id, symbol)
        state = self._states.get(identity)

        if state is None:
            result = CumulativeScoreResult(
                self.trading_date,
                strategy_id,
                symbol,
                candle_start,
                None,
                current_close,
                candle_volume,
                volume_threshold,
                None,
                None,
                None,
                Decimal("0"),
                None,
                0,
                False,
                (),
                (),
            )
        else:
            delta_price_pct = (
                (current_close - state.last_close) / state.last_close
            ) * Decimal("100")
            volume_multiple = candle_volume / volume_threshold
            contribution = delta_price_pct * volume_multiple
            cumulative_score = state.cumulative_score + contribution
            harmonic_mean = signed_harmonic_mean(delta_price_pct, volume_multiple)
            alert_sent = cumulative_score > self.policy.alert_threshold
            alert_count = state.alert_count + (1 if alert_sent else 0)
            scores = (*state.score_history, cumulative_score)
            harmonics = (*state.harmonic_history, harmonic_mean)
            result = CumulativeScoreResult(
                self.trading_date,
                strategy_id,
                symbol,
                candle_start,
                state.last_close,
                current_close,
                candle_volume,
                volume_threshold,
                delta_price_pct,
                volume_multiple,
                contribution,
                cumulative_score,
                harmonic_mean,
                alert_count,
                alert_sent,
                scores,
                harmonics,
            )

        self._append(result)
        self._keys.add(key)
        self._states[identity] = _SymbolState(
            last_close=result.current_close,
            cumulative_score=result.cumulative_score,
            alert_count=result.alert_count,
            score_history=list(result.score_history),
            harmonic_history=list(result.harmonic_history),
        )
        return result

    def _append(self, result: CumulativeScoreResult) -> None:
        needs_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDS)
            if needs_header:
                writer.writeheader()
            writer.writerow(
                {
                    "trading_date": result.trading_date,
                    "strategy_id": result.strategy_id,
                    "symbol": result.symbol,
                    "candle_start": result.candle_start,
                    "previous_close": result.previous_close,
                    "current_close": result.current_close,
                    "candle_volume": result.candle_volume,
                    "volume_threshold": result.volume_threshold,
                    "delta_price_pct": result.delta_price_pct,
                    "volume_multiple": result.volume_multiple,
                    "score_contribution": result.score_contribution,
                    "cumulative_score": result.cumulative_score,
                    "harmonic_mean": result.harmonic_mean,
                    "alert_count": result.alert_count,
                    "alert_sent": str(result.alert_sent).lower(),
                }
            )
            handle.flush()
