from __future__ import annotations

from datetime import date

from ..domain.checks import DEFAULT_CHECKS, ControlCheck
from ..domain.models import Result, Status
from ..ports import MetricsReader, ResultWriter, RuleSource
from .evaluate import evaluate


class ReconciliationFailed(RuntimeError):
    """Una o más reglas duras no pasaron."""


class ValidateRun:
    """Caso de uso: compara las capas de una ejecución y deja el veredicto."""

    def __init__(
        self,
        rules: RuleSource,
        reader: MetricsReader,
        writer: ResultWriter,
        checks: tuple[ControlCheck, ...] = DEFAULT_CHECKS,
    ) -> None:
        self._rules = rules
        self._reader = reader
        self._writer = writer
        self._checks = checks

    def execute(
        self,
        run_id: str,
        expected_load_date: date,
        stage: str | None = None,
    ) -> tuple[Result, ...]:
        rules = self._rules.all()
        if stage is not None:
            rules = [rule for rule in rules if rule.target_layer == stage]
        if not rules:
            raise ReconciliationFailed(f"No hay reglas para la capa {stage}")
        results = []
        for rule in rules:
            source = self._reader.read(run_id, rule.source_layer, rule.source_table, rule.grain)
            target = self._reader.read(run_id, rule.target_layer, rule.target_table, rule.grain)
            result = evaluate(rule, source, target, expected_load_date, self._checks)
            self._writer.save(result)
            results.append(result)
        return tuple(results)

    def assert_passed(
        self,
        run_id: str,
        expected_load_date: date,
        stage: str | None = None,
    ) -> tuple[Result, ...]:
        results = self.execute(run_id, expected_load_date, stage)
        failed = [item for item in results if item.status == Status.FAIL]
        if failed:
            detail = " | ".join(f"{item.rule_id}: {item.message}" for item in failed)
            raise ReconciliationFailed(f"Reconciliation FAILED | {detail}")
        return results
