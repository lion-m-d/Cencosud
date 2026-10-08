from datetime import date

import pytest

from reconciliation import Metrics, Rule, Severity, Status, evaluate


def metrics(layer: str, count: int, **overrides) -> Metrics:
    values = {
        "run_id": "run-001",
        "pipeline": "ventas",
        "layer": layer,
        "table_name": f"{layer}.ventas",
        "output_count": count,
        "grain_count": count,
        "max_load_date": date(2026, 10, 7),
    }
    values.update(overrides)
    return Metrics(**values)


def rule(**overrides) -> Rule:
    values = {
        "rule_id": "bronze_silver",
        "pipeline": "ventas",
        "source_layer": "bronze",
        "target_layer": "silver",
        "source_table": "bronze.ventas",
        "target_table": "silver.ventas",
        "min_rows": 1,
        "min_ratio": 0.95,
        "max_ratio": 1.0,
        "max_drop_pct": 0.30,
        "load_date_column": "fecha_carga",
    }
    values.update(overrides)
    return Rule(**values)


def test_valid_load_passes() -> None:
    result = evaluate(rule(), metrics("bronze", 100), metrics("silver", 98), date(2026, 10, 7))
    assert result.status == Status.PASS
    assert result.ratio == pytest.approx(0.98)


def test_empty_target_fails() -> None:
    result = evaluate(rule(), metrics("bronze", 100), metrics("silver", 0), date(2026, 10, 7))
    assert result.status == Status.FAIL
    assert {item.name for item in result.checks if item.status == Status.FAIL} == {
        "minimum_rows",
        "layer_ratio",
    }


def test_historical_drop_fails() -> None:
    target = metrics("silver", 60, previous_count=100)
    assert evaluate(rule(), metrics("bronze", 60), target).status == Status.FAIL


def test_wrong_freshness_fails() -> None:
    target = metrics("silver", 98, max_load_date=date(2026, 10, 6))
    assert evaluate(rule(), metrics("bronze", 100), target, date(2026, 10, 7)).status == Status.FAIL


def test_warning_rule_does_not_hard_fail() -> None:
    warning = rule(severity=Severity.WARN)
    assert evaluate(warning, metrics("bronze", 100), metrics("silver", 0)).status == Status.WARN


def test_mapped_rejects_keep_the_valid_rows() -> None:
    target = metrics(
        "silver",
        18,
        rejected_count=4,
        rejected_grain=("ticket_id",),
    )
    result = evaluate(
        rule(grain=("ticket_id",)),
        metrics("bronze", 22),
        target,
        date(2026, 10, 7),
    )
    assert result.status == Status.PASS
    assert result.ratio == pytest.approx(1.0)


def test_unexplained_loss_still_fails() -> None:
    target = metrics("silver", 18, rejected_count=0, rejected_grain=("ticket_id",))
    result = evaluate(rule(grain=("ticket_id",)), metrics("bronze", 22), target)
    assert result.status == Status.FAIL


def test_rejects_do_not_change_another_grain() -> None:
    source = metrics("silver", 6, grain_count=6, output_count=18)
    target = metrics(
        "gold",
        6,
        grain_count=6,
        output_count=6,
        rejected_count=4,
        rejected_grain=("ticket_id",),
    )
    result = evaluate(
        rule(grain=("tienda_id", "fecha_venta"), min_ratio=0.98, max_ratio=1.02, source_layer="silver", target_layer="gold"),
        source,
        target,
    )
    assert result.ratio == pytest.approx(1.0)
    assert result.status == Status.PASS


def test_different_runs_are_rejected() -> None:
    target = metrics("silver", 10, run_id="another-run")
    with pytest.raises(ValueError, match="run_id"):
        evaluate(rule(), metrics("bronze", 10), target)
