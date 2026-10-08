"""Fachada estable. El dominio no se importa desde la infraestructura al revés."""

from .adapters.yaml_catalog import find_rule, load_rules
from .application.evaluate import evaluate
from .domain.models import Check, Metrics, Result, Rule, Severity, Status

__all__ = [
    "Check",
    "Metrics",
    "Result",
    "Rule",
    "Severity",
    "Status",
    "evaluate",
    "find_rule",
    "load_rules",
]
