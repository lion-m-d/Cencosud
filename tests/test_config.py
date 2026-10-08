from pathlib import Path

import pytest

from reconciliation import find_rule, load_rules


def test_load_example_contracts() -> None:
    rules = load_rules(Path("config/reconciliation_rules.yml"))
    assert len(rules) == 3
    assert find_rule(rules, "ventas_bronze").target_layer == "bronze"
    assert find_rule(rules, "ventas_bronze_silver").grain == ("ticket_id",)


def test_missing_rule_is_explicit() -> None:
    with pytest.raises(KeyError, match="missing"):
        find_rule([], "missing")
