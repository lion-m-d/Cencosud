from datetime import date, datetime

from reconciliation.adapters.dynamo_store import DynamoControlStore, metrics_from_log
from reconciliation.domain.models import Check, Metrics, Result, Status


class MemoryTable:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def put_item(self, Item: dict) -> None:
        self.items[(Item["run_id"], Item["sk"])] = dict(Item)

    def get_item(self, Key: dict, ConsistentRead: bool = False) -> dict:
        del ConsistentRead
        item = self.items.get((Key["run_id"], Key["sk"]))
        return {"Item": item} if item else {}

    def query(self, **kwargs) -> dict:
        entity = kwargs["ExpressionAttributeValues"][":entity"]
        rows = [item for item in self.items.values() if item.get("entity_key") == entity]
        rows.sort(key=lambda item: item["measured_at"], reverse=not kwargs.get("ScanIndexForward", True))
        return {"Items": rows[: kwargs.get("Limit", len(rows))]}


def test_metrics_from_log_ignora_el_prefijo_de_dbt() -> None:
    text = '12:01:00  RECON_METRICS {"run_id":"abc","layer":"silver","output_count":20}\n'
    assert metrics_from_log(text) == [{"run_id": "abc", "layer": "silver", "output_count": 20}]


def test_store_recupera_el_conteo_anterior() -> None:
    table = MemoryTable()
    store = DynamoControlStore("control", table=table)
    store.save_metrics(Metrics(
        run_id="anterior",
        pipeline="ventas",
        layer="bronze",
        table_name="bronze.ventas",
        output_count=20,
        grain_count=20,
        max_load_date=date(2026, 10, 7),
        measured_at=datetime(2026, 10, 7, 12, 0, 0),
    ))
    store.save_metrics(Metrics(
        run_id="actual",
        pipeline="ventas",
        layer="bronze",
        table_name="bronze.ventas",
        output_count=18,
        grain_count=18,
        max_load_date=date(2026, 10, 8),
        measured_at=datetime(2026, 10, 8, 12, 0, 0),
    ))
    current = store.read("actual", "bronze", "bronze.ventas", ("ticket_id",))
    assert current.output_count == 18
    assert current.previous_count == 20


def test_lee_el_grano_de_la_agregacion_y_no_el_de_los_tickets() -> None:
    table = MemoryTable()
    store = DynamoControlStore("control", table=table)
    store.save_metrics(Metrics(
        run_id="actual",
        pipeline="ventas",
        layer="silver",
        table_name="silver.ventas",
        output_count=22,
        grain_count=22,
        grain_counts={"ticket_id": 22, "tienda_id|fecha_venta": 6},
        measured_at=datetime(2026, 10, 8, 12, 0, 0),
    ))
    por_ticket = store.read("actual", "silver", "silver.ventas", ("ticket_id",))
    por_tienda = store.read("actual", "silver", "silver.ventas", ("tienda_id", "fecha_venta"))
    assert por_ticket.grain_count == 22
    assert por_tienda.grain_count == 6


def test_store_guarda_el_veredicto() -> None:
    table = MemoryTable()
    store = DynamoControlStore("control", table=table)
    store.save(Result(
        run_id="actual",
        rule_id="ventas_bronze",
        status=Status.PASS,
        source_count=18,
        target_count=18,
        ratio=1.0,
        checks=(Check("minimum_rows", Status.PASS, "18", ">=1", "minimum_rows: OK"),),
    ))
    item = table.items[("actual", "result#ventas_bronze")]
    assert item["status"] == "PASS"
    assert "minimum_rows" in item["checks_json"]
