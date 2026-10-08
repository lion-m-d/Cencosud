"""Contratos pequeños. Cada caso de uso depende solo de los que usa."""

from __future__ import annotations

from typing import Protocol

from .domain.models import Metrics, Result, Rule


class RuleSource(Protocol):
    def all(self) -> list[Rule]:
        """Reglas vigentes del catálogo."""


class MetricsReader(Protocol):
    def read(self, run_id: str, layer: str, table_name: str, grain: tuple[str, ...]) -> Metrics:
        """Métricas de una capa, contadas en el grano indicado."""


class ResultWriter(Protocol):
    def save(self, result: Result) -> None:
        """Persiste el veredicto de una regla."""


class MetricsWriter(Protocol):
    def save(self, metrics: Metrics) -> None:
        """Persiste la medición de una capa."""
