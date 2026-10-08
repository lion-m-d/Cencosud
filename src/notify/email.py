"""Arma el correo de reconciliación. No conoce Step Functions."""

from __future__ import annotations

import json
import os

STEPS = (
    ("ventas_bronze", "Bronze"),
    ("ventas_bronze_silver", "Silver"),
    ("ventas_silver_gold", "Gold"),
)


def build_notice(event: dict) -> tuple[str, str]:
    run_id = event.get("run_id") or "sin run_id"
    load_date = event.get("load_date") or "sin fecha"
    trace = _trace(event.get("layers") or [])
    if event.get("outcome") == "PASS":
        lines = [f"{index}. {label} — validado" for index, (_, label) in enumerate(STEPS, start=1)]
        return (
            "Pipeline validado en us-east-2",
            "\n".join(
                [
                    "Resultado: VALIDADO",
                    f"run_id: {run_id}",
                    f"load_date: {load_date}",
                    "La carga concuerda con las reglas.",
                    "",
                    "Pasos registrados:",
                    *lines,
                    *trace,
                ]
            ),
        )

    detail = _detail(event.get("cause") or "")
    failed = None
    for index, (rule, _) in enumerate(STEPS):
        if rule in detail and (failed is None or len(rule) > len(STEPS[failed][0])):
            failed = index
    if failed is None:
        return (
            "Fallo en pipeline us-east-2",
            "\n".join(
                [
                    "Resultado: FALLO",
                    f"run_id: {run_id}",
                    f"load_date: {load_date}",
                    "El pipeline se detuvo antes de cerrar la validación.",
                    *trace,
                    "",
                    "Detalle:",
                    detail,
                ]
            ),
        )

    lines = []
    for index, (_, label) in enumerate(STEPS):
        if index < failed:
            lines.append(f"{index + 1}. {label} — validado")
        elif index == failed:
            lines.append(f"{index + 1}. {label} — no concuerda")
        else:
            lines.append(f"{index + 1}. {label} — no se ejecutó")
    return (
        "La carga no concuerda en us-east-2",
        "\n".join(
            [
                "Resultado: NO CONCUERDA",
                f"run_id: {run_id}",
                f"load_date: {load_date}",
                "La carga nueva no concuerda con la capa anterior o con la carga previa.",
                "",
                "Pasos registrados:",
                *lines,
                *trace,
                "",
                "Detalle:",
                detail,
            ]
        ),
    )


def _trace(layers: list) -> list[str]:
    if not layers:
        return []
    lines = ["", "Registros por capa:"]
    for item in layers:
        lines.append(
            f"- {item.get('layer')}: entraron {item.get('input_count')}, salieron {item.get('output_count')}"
        )
    return lines


def _detail(cause: str) -> str:
    text = cause.strip() or "Sin detalle"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:1500]
    if not isinstance(payload, dict):
        return text[:1500]
    message = payload.get("ErrorMessage")
    if message:
        return str(message)[:1500]
    for phase in payload.get("Phases") or []:
        for context in phase.get("Contexts") or []:
            found = context.get("Message") or ""
            if found:
                return str(found)[:1500]
    return text[:1500]


def handler(event: dict, _context) -> dict:
    import boto3

    notice = dict(event)
    notice["layers"] = _layers(str(event.get("run_id") or ""))
    subject, message = build_notice(notice)
    boto3.client("sns").publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject=subject[:100],
        Message=message,
    )
    return {"subject": subject}


def _layers(run_id: str) -> list[dict]:
    table_name = os.environ.get("CONTROL_TABLE")
    if not table_name or not run_id:
        return []
    try:
        import boto3
        from boto3.dynamodb.conditions import Key

        response = boto3.resource("dynamodb").Table(table_name).query(
            KeyConditionExpression=Key("run_id").eq(run_id)
        )
    except Exception:
        return []
    order = {"bronze": 0, "silver": 1, "gold": 2}
    metrics = [item for item in response.get("Items", []) if item.get("record_type") == "metrics"]
    metrics.sort(key=lambda item: order.get(str(item.get("layer")), 9))
    return [
        {
            "layer": item.get("layer"),
            "input_count": int(item["input_count"]) if item.get("input_count") is not None else None,
            "output_count": int(item["output_count"]) if item.get("output_count") is not None else None,
        }
        for item in metrics
    ]
