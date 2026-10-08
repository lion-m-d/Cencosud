from __future__ import annotations

from datetime import date

from ..domain.checks import DEFAULT_CHECKS, ControlCheck
from ..domain.models import Metrics, Result, Rule, Status


def evaluate(
    rule: Rule,
    source: Metrics,
    target: Metrics,
    expected_load_date: date | None = None,
    checks: tuple[ControlCheck, ...] = DEFAULT_CHECKS,
) -> Result:
    """Cierra el veredicto de una frontera. Los controles llegan por composición."""
    if source.run_id != target.run_id:
        raise ValueError("Las métricas de origen y destino deben pertenecer al mismo run_id")
    if not rule.enabled:
        return Result(
            source.run_id,
            rule.rule_id,
            Status.PASS,
            source.output_count,
            target.output_count,
            None,
            (),
        )

    produced = tuple(
        check
        for item in checks
        if (check := item.apply(rule, source, target, expected_load_date)) is not None
    )
    if any(item.status == Status.FAIL for item in produced):
        status = Status.FAIL
    elif any(item.status == Status.WARN for item in produced):
        status = Status.WARN
    else:
        status = Status.PASS
    source_count = source.grain_count if source.grain_count is not None else source.output_count
    target_count = target.grain_count if target.grain_count is not None else target.output_count
    ratio = target_count / source_count if source_count > 0 else None
    return Result(source.run_id, rule.rule_id, status, source_count, target_count, ratio, produced)
