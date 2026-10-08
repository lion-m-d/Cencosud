"""Registros de reconciliación en DynamoDB."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from ..domain.models import Metrics, Result

METRICS_PREFIX = "metrics#"
RESULT_PREFIX = "result#"


def checks_payload(result: Result) -> str:
    return json.dumps(
        [
            {
                "name": check.name,
                "status": check.status.value,
                "actual": check.actual,
                "expected": check.expected,
            }
            for check in result.checks
        ],
        ensure_ascii=False,
    )


def metrics_from_log(text: str) -> list[dict]:
    found: list[dict] = []
    marker = "RECON_METRICS "
    for line in text.splitlines():
        start = line.find(marker)
        if start < 0:
            continue
        raw = line[start + len(marker):].strip()
        brace = raw.find("{")
        if brace < 0:
            continue
        found.append(json.loads(raw[brace:]))
    return found


class DynamoControlStore:
    """Implementa la lectura de métricas y la escritura de métricas y veredictos."""

    def __init__(self, table_name: str, region: str = "us-east-2", table=None) -> None:
        self._table_name = table_name
        self._region = region
        self._table = table

    def save_metrics(self, metrics: Metrics) -> None:
        previous = metrics.previous_count
        if previous is None:
            previous = self._previous_output(metrics.layer, metrics.table_name, metrics.run_id)
        measured = metrics.measured_at or datetime.utcnow()
        entity = f"{METRICS_PREFIX}{metrics.layer}#{metrics.table_name}"
        self._table_ref().put_item(Item=_without_empty({
            "run_id": metrics.run_id,
            "sk": entity,
            "entity_key": entity,
            "measured_at": measured.isoformat(timespec="seconds"),
            "record_type": "metrics",
            "pipeline": metrics.pipeline,
            "layer": metrics.layer,
            "table_name": metrics.table_name,
            "input_count": _decimal(metrics.input_count),
            "output_count": _decimal(metrics.output_count),
            "grain_count": _decimal(metrics.grain_count),
            "grain_counts": {key: _decimal(value) for key, value in metrics.grain_counts.items()} or None,
            "max_load_date": metrics.max_load_date.isoformat() if metrics.max_load_date else None,
            "previous_count": _decimal(previous),
            "snapshot_id": metrics.snapshot_id,
        }))

    def save(self, result: Result) -> None:
        evaluated = datetime.utcnow()
        entity = f"{RESULT_PREFIX}{result.rule_id}"
        self._table_ref().put_item(Item=_without_empty({
            "run_id": result.run_id,
            "sk": entity,
            "entity_key": entity,
            "measured_at": evaluated.isoformat(timespec="seconds"),
            "record_type": "result",
            "rule_id": result.rule_id,
            "status": result.status.value,
            "source_count": _decimal(result.source_count),
            "target_count": _decimal(result.target_count),
            "ratio": _decimal(result.ratio),
            "message": result.message,
            "checks_json": checks_payload(result),
        }))

    def read(self, run_id: str, layer: str, table_name: str, grain: tuple[str, ...]) -> Metrics:
        response = self._table_ref().get_item(
            Key={"run_id": run_id, "sk": f"{METRICS_PREFIX}{layer}#{table_name}"},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            raise RuntimeError(f"No existen métricas para {run_id}/{layer}/{table_name}")
        stored = {
            str(key): count
            for key, value in (item.get("grain_counts") or {}).items()
            if (count := _int(value)) is not None
        }
        grain_count = _grain_count(stored, grain, item.get("grain_count"), run_id, layer, table_name)
        return Metrics(
            run_id=item["run_id"],
            pipeline=item["pipeline"],
            layer=item["layer"],
            table_name=item["table_name"],
            input_count=_int(item.get("input_count")),
            output_count=_int(item.get("output_count")) or 0,
            grain_count=grain_count,
            grain_counts=stored,
            max_load_date=_date(item.get("max_load_date")),
            previous_count=_int(item.get("previous_count")),
            snapshot_id=item.get("snapshot_id"),
            measured_at=_timestamp(item["measured_at"]),
        )

    def save_logged_metrics(self, text: str) -> int:
        saved = 0
        for payload in metrics_from_log(text):
            measured = payload.get("measured_at")
            raw_counts = payload.get("grain_counts") or {}
            self.save_metrics(Metrics(
                run_id=str(payload["run_id"]),
                pipeline=str(payload.get("pipeline") or "ventas"),
                layer=str(payload["layer"]),
                table_name=str(payload["table_name"]),
                output_count=_int(payload.get("output_count")) or 0,
                input_count=_int(payload.get("input_count")),
                grain_count=_int(payload.get("grain_count")),
                max_load_date=_date(payload.get("max_load_date")),
                previous_count=_int(payload.get("previous_count")),
                snapshot_id=payload.get("snapshot_id"),
                measured_at=_timestamp(measured) if measured else datetime.utcnow(),
                grain_counts={str(key): count for key, value in raw_counts.items() if (count := _int(value)) is not None},
            ))
            saved += 1
        return saved

    def _previous_output(self, layer: str, table_name: str, run_id: str) -> int | None:
        entity = f"{METRICS_PREFIX}{layer}#{table_name}"
        response = self._table_ref().query(
            IndexName="by_entity",
            KeyConditionExpression="entity_key = :entity",
            ExpressionAttributeValues={":entity": entity},
            ScanIndexForward=False,
            Limit=10,
        )
        for item in response.get("Items", []):
            if item.get("run_id") == run_id:
                continue
            count = _int(item.get("output_count"))
            if count:
                return count
        return None

    def _table_ref(self):
        if self._table is not None:
            return self._table
        self._table = _BotoTable(self._table_name, self._region)
        return self._table


class _BotoTable:
    def __init__(self, table_name: str, region: str) -> None:
        import boto3

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def put_item(self, Item: dict) -> None:
        self._table.put_item(Item=Item)

    def get_item(self, Key: dict, ConsistentRead: bool = False) -> dict:
        return self._table.get_item(Key=Key, ConsistentRead=ConsistentRead)

    def query(self, **kwargs) -> dict:
        from boto3.dynamodb.conditions import Key

        entity = kwargs["ExpressionAttributeValues"][":entity"]
        return self._table.query(
            IndexName=kwargs["IndexName"],
            KeyConditionExpression=Key("entity_key").eq(entity),
            ScanIndexForward=kwargs.get("ScanIndexForward", True),
            Limit=kwargs.get("Limit", 10),
        )


def _grain_count(
    stored: dict[str, int],
    grain: tuple[str, ...],
    fallback: object,
    run_id: str,
    layer: str,
    table_name: str,
) -> int | None:
    if not grain:
        return _int(fallback)
    key = "|".join(grain)
    if key in stored:
        return stored[key]
    if not stored:
        return _int(fallback)
    raise RuntimeError(f"No hay conteo del grano {key} para {run_id}/{layer}/{table_name}")


def _without_empty(item: dict) -> dict:
    return {key: value for key, value in item.items() if value is not None}


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _date(value: object) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", ""))
