from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class Severity(str, Enum):
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pipeline: str
    source_layer: str
    target_layer: str
    source_table: str
    target_table: str
    grain: tuple[str, ...] = ()
    min_rows: int = 1
    min_ratio: float | None = None
    max_ratio: float | None = None
    max_drop_pct: float | None = None
    load_date_column: str | None = None
    severity: Severity = Severity.FAIL
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Rule":
        payload = dict(value)
        payload["grain"] = tuple(payload.get("grain") or ())
        payload["severity"] = Severity(payload.get("severity", Severity.FAIL))
        return cls(**payload)


@dataclass(frozen=True)
class Metrics:
    run_id: str
    pipeline: str
    layer: str
    table_name: str
    output_count: int
    input_count: int | None = None
    grain_count: int | None = None
    max_load_date: date | None = None
    previous_count: int | None = None
    snapshot_id: str | None = None
    measured_at: datetime = field(default_factory=datetime.utcnow)
    grain_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    actual: str
    expected: str
    message: str


@dataclass(frozen=True)
class Result:
    run_id: str
    rule_id: str
    status: Status
    source_count: int
    target_count: int
    ratio: float | None
    checks: tuple[Check, ...]

    @property
    def message(self) -> str:
        return "; ".join(check.message for check in self.checks if check.status != Status.PASS)
