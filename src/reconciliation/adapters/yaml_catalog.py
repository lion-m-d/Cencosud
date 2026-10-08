from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..domain.models import Rule


class YamlRuleCatalog:
    """Adaptador del catálogo de contratos versionado en YAML."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def all(self) -> list[Rule]:
        return load_rules(self._path)


def load_rules(path: str | Path) -> list[Rule]:
    with Path(path).open(encoding="utf-8") as stream:
        document: dict[str, Any] = yaml.safe_load(stream) or {}
    rules = [Rule.from_dict(item) for item in document.get("rules", [])]
    identifiers = [rule.rule_id for rule in rules]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Los rule_id deben ser únicos")
    return rules


def find_rule(rules: list[Rule], rule_id: str) -> Rule:
    try:
        return next(rule for rule in rules if rule.rule_id == rule_id)
    except StopIteration as exc:
        raise KeyError(f"No existe la regla {rule_id}") from exc
