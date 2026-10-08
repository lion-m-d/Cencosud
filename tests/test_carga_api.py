import pytest

from carga.aws import S3CsvStore
from carga.sales_file import csv_from_request, original_file_name, resolve_load_date


def test_csv_request_is_accepted() -> None:
    event = {
        "headers": {"content-type": "text/csv", "x-load-date": "2026-10-07"},
        "body": "ticket_id,tienda_id,fecha_venta,monto\nT-001,S-01,2026-10-07,10.50\n",
    }
    csv_text = csv_from_request(event)
    assert "T-001" in csv_text
    assert resolve_load_date(event, csv_text) == "2026-10-07"


def test_json_request_becomes_csv() -> None:
    event = {
        "headers": {"content-type": "application/json"},
        "body": '{"records":[{"ticket_id":"T-010","tienda_id":"S-03","fecha_venta":"2026-10-08","monto":"55.00"}]}',
    }
    csv_text = csv_from_request(event)
    assert csv_text.startswith("ticket_id,tienda_id,fecha_venta,monto")
    assert resolve_load_date(event, csv_text) == "2026-10-08"


def test_postman_file_upload_is_accepted() -> None:
    event = {
        "headers": {"content-type": "multipart/form-data; boundary=PostmanBoundary"},
        "body": (
            "--PostmanBoundary\r\n"
            'Content-Disposition: form-data; name="file"; filename="ventas.csv"\r\n'
            "Content-Type: text/csv\r\n"
            "\r\n"
            "ticket_id,tienda_id,fecha_venta,monto\r\n"
            "T-001,S-01,2026-10-07,10.50\r\n"
            "--PostmanBoundary--\r\n"
        ),
    }
    csv_text = csv_from_request(event)
    assert csv_text.startswith("ticket_id,tienda_id,fecha_venta,monto\n")
    assert "T-001,S-01,2026-10-07,10.50" in csv_text
    assert "PostmanBoundary" not in csv_text
    assert "--" not in csv_text.split("\n", 1)[-1]
    assert original_file_name(event) == "ventas.csv"


def test_semicolon_csv_is_normalized() -> None:
    event = {
        "headers": {"content-type": "text/csv"},
        "body": "ticket_id;tienda_id;fecha_venta;monto\nT-002;S-02;2026-10-07;14.75\n",
    }
    csv_text = csv_from_request(event)
    assert "T-002,S-02,2026-10-07,14.75" in csv_text


def test_postman_path_reference_is_rejected() -> None:
    event = {"headers": {"content-type": "text/csv"}, "body": "@demo/data/ventas.csv"}
    with pytest.raises(ValueError, match="form-data"):
        csv_from_request(event)


class _Missing(Exception):
    def __init__(self) -> None:
        self.response = {"Error": {"Code": "404"}}


class _Bucket:
    def __init__(self, names: set[str]) -> None:
        self.names = set(names)
        self.saved = ""

    def head_object(self, Bucket: str, Key: str) -> dict:
        if Key not in self.names:
            raise _Missing()
        return {}

    def put_object(self, **kwargs) -> dict:
        self.saved = kwargs["Key"]
        return {}


def test_upload_keeps_the_original_name() -> None:
    bucket = _Bucket(set())
    uri, stored = S3CsvStore(bucket, "s3-bucket-carga-data", "raw/").put_csv("a\n", "ventas_error.csv")
    assert stored == "ventas_error.csv"
    assert uri == "s3://s3-bucket-carga-data/raw/ventas_error.csv"
    assert bucket.saved == "raw/ventas_error.csv"


def test_repeated_name_uses_the_next_suffix() -> None:
    bucket = _Bucket({"raw/ventas.csv", "raw/ventas_1.csv"})
    _uri, stored = S3CsvStore(bucket, "s3-bucket-carga-data", "raw/").put_csv("a\n", "ventas.csv")
    assert stored == "ventas_2.csv"
    assert bucket.saved == "raw/ventas_2.csv"


def test_missing_column_is_rejected() -> None:
    event = {"headers": {"content-type": "text/csv"}, "body": "ticket_id,monto\nT-001,10\n"}
    with pytest.raises(ValueError, match="tienda_id"):
        csv_from_request(event)
