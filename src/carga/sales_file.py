"""Traduce el cuerpo HTTP a un CSV de ventas. No conoce S3 ni Step Functions."""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import date

REQUIRED_COLUMNS = ("ticket_id", "tienda_id", "fecha_venta", "monto")


def _headers(event: dict) -> dict[str, str]:
    return {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}


def decode_body(event: dict) -> str:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8-sig")
    if isinstance(body, bytes):
        body = body.decode("utf-8-sig")
    return str(body).lstrip("\ufeff")


def _header_cells(line: str) -> tuple[list[str], str] | None:
    for delimiter in (",", ";", "\t", "|"):
        cells = [cell.strip().strip('"').lstrip("\ufeff") for cell in line.split(delimiter)]
        if all(column in cells for column in REQUIRED_COLUMNS):
            return cells, delimiter
    return None


def _csv_section(body: str) -> str:
    """Localiza la fila de cabecera aunque Postman envíe multipart o una línea previa."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if _header_cells(line):
            return "\n".join(lines[index:]).strip()
    preview = next((line.strip() for line in lines if line.strip()), "")[:120]
    raise ValueError(
        "Faltan columnas: "
        + ", ".join(REQUIRED_COLUMNS)
        + (f". Primera línea recibida: {preview}" if preview else "")
    )


def _is_transport_line(value: str) -> bool:
    text = value.strip().strip('"')
    return text.startswith("--") or text.lower().startswith("content-")


def _normalize_csv(text: str) -> str:
    header = _header_cells(text.split("\n", 1)[0])
    if header is None:
        raise ValueError("Faltan columnas: " + ", ".join(REQUIRED_COLUMNS))
    _names, delimiter = header
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(REQUIRED_COLUMNS), lineterminator="\n")
    writer.writeheader()
    wrote = False
    for row in reader:
        cleaned = {(key or "").strip().strip('"').lstrip("\ufeff"): value for key, value in row.items()}
        ticket = (cleaned.get("ticket_id") or "").strip()
        if not ticket or _is_transport_line(ticket):
            continue
        writer.writerow({column: cleaned[column] for column in REQUIRED_COLUMNS})
        wrote = True
    if not wrote:
        raise ValueError("El CSV no contiene registros")
    return stream.getvalue()


def csv_from_request(event: dict) -> str:
    content_type = _headers(event).get("content-type", "text/csv")
    body = decode_body(event).strip()
    if not body:
        raise ValueError("El cuerpo de la petición está vacío")
    if body.lstrip().startswith("@"):
        raise ValueError(
            "El Body trae la ruta del archivo, no su contenido. "
            "En Postman abre Body, elige form-data, tipo File, y selecciona demo/data/ventas.csv."
        )
    if "application/json" in content_type and not body.startswith("--"):
        payload = json.loads(body)
        rows = payload.get("records", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            raise ValueError("JSON debe contener una lista de registros")
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(REQUIRED_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in REQUIRED_COLUMNS})
        body = stream.getvalue()
    return _normalize_csv(_csv_section(body))


def resolve_load_date(event: dict, csv_text: str) -> str:
    query = event.get("queryStringParameters") or {}
    raw_date = query.get("load_date") or _headers(event).get("x-load-date")
    if not raw_date:
        raw_date = next(csv.DictReader(io.StringIO(csv_text)))["fecha_venta"]
    return date.fromisoformat(str(raw_date)[:10]).isoformat()
