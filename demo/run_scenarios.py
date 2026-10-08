"""Runs the rule engine locally without AWS credentials."""

from __future__ import annotations

from datetime import date

from reconciliation import Metrics, Status, evaluate, find_rule, load_rules


LOAD_DATE = date(2026, 10, 7)


def metric(layer: str, count: int, previous: int | None = None) -> Metrics:
    return Metrics(
        run_id=f"demo-{layer}-{count}",
        pipeline="ventas",
        layer=layer,
        table_name=f"{layer}.ventas",
        output_count=count,
        grain_count=count,
        previous_count=previous,
        max_load_date=LOAD_DATE,
    )


def run(name: str, source_count: int, target_count: int, previous: int | None = None) -> Status:
    rule = find_rule(load_rules("config/reconciliation_rules.yml"), "ventas_bronze_silver")
    source = metric("bronze", source_count)
    target = metric("silver", target_count, previous)
    # Both sides of one execution must carry the orchestrator's run id.
    target = Metrics(**{**target.__dict__, "run_id": source.run_id})
    result = evaluate(rule, source, target, LOAD_DATE)
    print(f"{name:18} status={result.status.value:4} ratio={result.ratio} {result.message}")
    return result.status


if __name__ == "__main__":
    assert run("normal", 100, 98) == Status.PASS
    assert run("empty", 100, 0) == Status.FAIL
    assert run("abnormal_drop", 60, 60, previous=100) == Status.FAIL
