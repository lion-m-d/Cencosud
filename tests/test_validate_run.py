from datetime import date

from reconciliation.application.validate_run import ReconciliationFailed, ValidateRun
from reconciliation.domain.models import Metrics, Result, Rule, Status


class MemoryRules:
    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def all(self) -> list[Rule]:
        return self._rules


class MemoryReader:
    def __init__(self, rows: dict[tuple[str, str], Metrics]) -> None:
        self._rows = rows

    def read(self, run_id: str, layer: str, table_name: str, grain: tuple[str, ...]) -> Metrics:
        del run_id, grain
        return self._rows[(layer, table_name)]


class MemoryWriter:
    def __init__(self) -> None:
        self.saved: list[Result] = []

    def save(self, result: Result) -> None:
        self.saved.append(result)


def metric(layer: str, table: str, count: int) -> Metrics:
    return Metrics("run-1", "ventas", layer, table, count, grain_count=count, max_load_date=date(2026, 10, 7))


def test_use_case_persists_without_spark() -> None:
    rule = Rule("border", "ventas", "bronze", "silver", "bronze.ventas", "silver.ventas", min_ratio=0.95, max_ratio=1)
    reader = MemoryReader({
        ("bronze", "bronze.ventas"): metric("bronze", "bronze.ventas", 100),
        ("silver", "silver.ventas"): metric("silver", "silver.ventas", 98),
    })
    writer = MemoryWriter()
    results = ValidateRun(MemoryRules([rule]), reader, writer).execute("run-1", date(2026, 10, 7))
    assert results[0].status == Status.PASS
    assert writer.saved[0].rule_id == "border"


def test_stage_runs_only_its_rules() -> None:
    bronze = Rule("ventas_bronze", "ventas", "bronze", "bronze", "bronze.ventas", "bronze.ventas")
    silver = Rule("ventas_silver", "ventas", "bronze", "silver", "bronze.ventas", "silver.ventas", min_ratio=1, max_ratio=1)
    reader = MemoryReader({
        ("bronze", "bronze.ventas"): metric("bronze", "bronze.ventas", 10),
        ("silver", "silver.ventas"): metric("silver", "silver.ventas", 10),
    })
    writer = MemoryWriter()
    ValidateRun(MemoryRules([bronze, silver]), reader, writer).assert_passed(
        "run-1",
        date(2026, 10, 7),
        stage="bronze",
    )
    assert [item.rule_id for item in writer.saved] == ["ventas_bronze"]


def test_use_case_rejects_empty_target() -> None:
    rule = Rule("border", "ventas", "bronze", "silver", "bronze.ventas", "silver.ventas")
    reader = MemoryReader({
        ("bronze", "bronze.ventas"): metric("bronze", "bronze.ventas", 10),
        ("silver", "silver.ventas"): metric("silver", "silver.ventas", 0),
    })
    try:
        ValidateRun(MemoryRules([rule]), reader, MemoryWriter()).assert_passed("run-1", date(2026, 10, 7))
    except ReconciliationFailed as exc:
        assert "border" in str(exc)
    else:
        raise AssertionError("debía fallar")
