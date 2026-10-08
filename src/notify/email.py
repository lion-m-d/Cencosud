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
    layers = event.get("layers") or []
    rejects = event.get("rejects") or []
    trace = _trace(layers)
    omitted = _omitted(layers, rejects)
    archive = _archive(event, layers, rejects)
    if event.get("outcome") == "PASS":
        lines = [f"{index}. {label} — validado" for index, (_, label) in enumerate(STEPS, start=1)]
        sent, processed, missing = _file_counts(layers, rejects)
        subject = "Pipeline validado en us-east-2"
        summary = "La carga concuerda con las reglas."
        if missing and sent is not None and processed is not None:
            subject = f"Se procesaron {processed} de {sent} registros"
            summary = "La data correcta quedó en Silver y Gold."
        elif missing:
            summary = "La data correcta quedó en Silver y Gold."
        return (
            subject,
            "\n".join(
                [
                    "Resultado: VALIDADO",
                    f"run_id: {run_id}",
                    f"load_date: {load_date}",
                    *archive,
                    summary,
                    "",
                    "Pasos registrados:",
                    *lines,
                    *trace,
                    *omitted,
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
                    *archive,
                    "El pipeline se detuvo antes de cerrar la validación.",
                    *trace,
                    *omitted,
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
                *archive,
                "La carga nueva no concuerda con la capa anterior o con la carga previa.",
                "",
                "Pasos registrados:",
                *lines,
                *trace,
                *omitted,
                "",
                "Detalle:",
                detail,
            ]
        ),
    )


def _archive(event: dict, layers: list, rejects: list) -> list[str]:
    name = str(event.get("file_name") or "").strip() or "sin nombre"
    sent, _processed, missing = _file_counts(layers, rejects)
    lines = [f"Archivo procesado: {name}"]
    if event.get("outcome") == "FAIL" or missing > 0:
        if missing > 0 and sent is not None:
            lines.append(f"El archivo {name} falló en los registros: no se procesaron {missing} de {sent}.")
        elif missing > 0:
            lines.append(f"El archivo {name} falló en los registros: no se procesaron {missing}.")
        else:
            lines.append(f"El archivo {name} falló en los registros.")
    return lines


def _is_transport_ticket(ticket: str) -> bool:
    text = ticket.strip()
    return text.startswith("--") or text.lower().startswith("content-")


def _real_rejects(rejects: list) -> list:
    return [item for item in rejects if not _is_transport_ticket(str(item.get("ticket_id") or ""))]


def _file_counts(layers: list, rejects: list) -> tuple[int | None, int | None, int]:
    by_layer = {item.get("layer"): item for item in layers}
    bronze = by_layer.get("bronze") or {}
    silver = by_layer.get("silver") or {}
    sent = bronze.get("output_count")
    if sent is None:
        sent = bronze.get("input_count")
    if sent is None:
        sent = silver.get("input_count")
    real = _real_rejects(rejects)
    noise = len(rejects) - len(real)
    if sent is not None and noise:
        sent -= noise
    if rejects:
        missing = len(real)
    else:
        missing = silver.get("rejected_count")
        if missing is None:
            missing = 0
    processed = silver.get("output_count")
    return sent, processed, int(missing or 0)


def _omitted(layers: list, rejects: list) -> list[str]:
    sent, processed, missing = _file_counts(layers, rejects)
    if missing <= 0:
        return []
    processed_text = str(processed) if processed is not None else "los válidos"
    omitted = f"No se procesaron {missing} registros enviados."
    if sent is not None:
        omitted = f"No se procesaron {missing} de {sent} registros enviados."
    lines = [
        "",
        omitted,
        f"Se procesaron {processed_text} registros correctos.",
        "",
        "Registros no procesados:",
    ]
    shown = _real_rejects(rejects)[:30]
    for item in shown:
        ticket = item.get("ticket_id") or "sin ticket_id"
        reason = item.get("reason") or "dato inválido"
        lines.append(f"- {ticket}: {reason}")
    extra = missing - len(shown)
    if extra > 0:
        lines.append(f"- y {extra} registros más")
    return lines


def _trace(layers: list) -> list[str]:
    if not layers:
        return []
    lines = ["", "Registros por capa:"]
    for item in layers:
        lines.append(
            f"- {item.get('layer')}: entraron {item.get('input_count')}, salieron {item.get('output_count')}"
        )
    return lines


def _phase_messages(payload: dict) -> list[str]:
    found: list[str] = []
    direct = payload.get("ErrorMessage") or payload.get("errorMessage")
    if direct:
        found.append(str(direct))
    containers = [payload]
    build = payload.get("Build") or payload.get("build")
    if isinstance(build, dict):
        containers.append(build)
    for container in containers:
        phases = container.get("Phases") or container.get("phases") or []
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            status = str(phase.get("PhaseStatus") or phase.get("phaseStatus") or "")
            if status and status not in {"FAILED", "FAULT", "CLIENT_ERROR"}:
                continue
            for context in phase.get("Contexts") or phase.get("contexts") or []:
                if not isinstance(context, dict):
                    continue
                message = context.get("Message") or context.get("message") or ""
                if message:
                    found.append(str(message))
    return found


def _detail(cause: str) -> str:
    text = cause.strip() or "Sin detalle"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:1500]
    if not isinstance(payload, dict):
        return text[:1500]
    messages = _phase_messages(payload)
    if messages:
        return messages[-1][:1500]
    return text[:1500]


def handler(event: dict, _context) -> dict:
    import boto3

    notice = dict(event)
    layers, rejects = _control(str(event.get("run_id") or ""))
    notice["layers"] = layers
    notice["rejects"] = rejects
    subject, message = build_notice(notice)
    boto3.client("sns").publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject=subject[:100],
        Message=message,
    )
    return {"subject": subject}


def _control(run_id: str) -> tuple[list[dict], list[dict]]:
    table_name = os.environ.get("CONTROL_TABLE")
    if not table_name or not run_id:
        return [], []
    try:
        import boto3
        from boto3.dynamodb.conditions import Key

        response = boto3.resource("dynamodb").Table(table_name).query(
            KeyConditionExpression=Key("run_id").eq(run_id)
        )
    except Exception:
        return [], []
    items = response.get("Items", [])
    return _layers(items), _rejects(items)


def _layers(items: list[dict]) -> list[dict]:
    order = {"bronze": 0, "silver": 1, "gold": 2}
    metrics = [item for item in items if item.get("record_type") == "metrics"]
    metrics.sort(key=lambda item: order.get(str(item.get("layer")), 9))
    return [
        {
            "layer": item.get("layer"),
            "input_count": int(item["input_count"]) if item.get("input_count") is not None else None,
            "output_count": int(item["output_count"]) if item.get("output_count") is not None else None,
            "rejected_count": int(item["rejected_count"]) if item.get("rejected_count") is not None else None,
        }
        for item in metrics
    ]


def _rejects(items: list[dict]) -> list[dict]:
    rows = [item for item in items if item.get("record_type") == "reject"]
    rows.sort(key=lambda item: str(item.get("sk") or ""))
    return [
        {
            "ticket_id": item.get("ticket_id") or "",
            "reason": item.get("reason") or "dato inválido",
        }
        for item in rows
    ]
