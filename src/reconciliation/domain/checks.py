"""Cada control es una estrategia. Un control nuevo no modifica los existentes."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import Check, Metrics, Rule, Severity, Status


class ControlCheck(Protocol):
    def apply(
        self,
        rule: Rule,
        source: Metrics,
        target: Metrics,
        expected_load_date: date | None,
    ) -> Check | None:
        """Devuelve None cuando el contrato no activa este control."""


def compared_counts(rule: Rule, source: Metrics, target: Metrics) -> tuple[int, int]:
    """El grano rechazado y mapeado cuenta como explicado, no como pérdida silenciosa."""
    source_count = source.grain_count if source.grain_count is not None else source.output_count
    target_count = target.grain_count if target.grain_count is not None else target.output_count
    if target.rejected_count and rule.grain and rule.grain == target.rejected_grain:
        target_count += target.rejected_count
    return source_count, target_count


def _failure_status(rule: Rule) -> Status:
    return Status.WARN if rule.severity == Severity.WARN else Status.FAIL


def _check(name: str, ok: bool, actual: object, expected: str, rule: Rule) -> Check:
    status = Status.PASS if ok else _failure_status(rule)
    detail = "OK" if ok else f"valor {actual!s} fuera de lo esperado ({expected})"
    return Check(name, status, str(actual), expected, f"{name}: {detail}")


class MinimumRowsCheck:
    def apply(
        self,
        rule: Rule,
        source: Metrics,
        target: Metrics,
        expected_load_date: date | None,
    ) -> Check:
        del source, expected_load_date
        return _check(
            "minimum_rows",
            target.output_count >= rule.min_rows,
            target.output_count,
            f">={rule.min_rows}",
            rule,
        )


class RatioCheck:
    def apply(
        self,
        rule: Rule,
        source: Metrics,
        target: Metrics,
        expected_load_date: date | None,
    ) -> Check | None:
        del expected_load_date
        if rule.min_ratio is None and rule.max_ratio is None:
            return None
        source_count, target_count = compared_counts(rule, source, target)
        ratio = target_count / source_count if source_count > 0 else None
        low = rule.min_ratio if rule.min_ratio is not None else float("-inf")
        high = rule.max_ratio if rule.max_ratio is not None else float("inf")
        return _check(
            "layer_ratio",
            ratio is not None and low <= ratio <= high,
            ratio,
            f"{low}..{high}",
            rule,
        )


class HistoricalDropCheck:
    def apply(
        self,
        rule: Rule,
        source: Metrics,
        target: Metrics,
        expected_load_date: date | None,
    ) -> Check | None:
        del source, expected_load_date
        if rule.max_drop_pct is None or target.previous_count in (None, 0):
            return None
        drop_pct = (target.previous_count - target.output_count) / target.previous_count
        return _check(
            "historical_drop",
            drop_pct <= rule.max_drop_pct,
            round(drop_pct, 6),
            f"<={rule.max_drop_pct}",
            rule,
        )


class FreshnessCheck:
    def apply(
        self,
        rule: Rule,
        source: Metrics,
        target: Metrics,
        expected_load_date: date | None,
    ) -> Check | None:
        del source
        if expected_load_date is None or not rule.load_date_column:
            return None
        return _check(
            "freshness",
            target.max_load_date == expected_load_date,
            target.max_load_date,
            str(expected_load_date),
            rule,
        )


DEFAULT_CHECKS: tuple[ControlCheck, ...] = (
    MinimumRowsCheck(),
    RatioCheck(),
    HistoricalDropCheck(),
    FreshnessCheck(),
)
