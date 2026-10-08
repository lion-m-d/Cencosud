"""Traduce API Gateway al caso de uso AcceptLoad."""

from __future__ import annotations

import json

from .aws import aws_accept_load


def response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def is_notification(event: dict) -> bool:
    return isinstance(event, dict) and event.get("outcome") in {"PASS", "FAIL"}


def handler(event: dict, context) -> dict:
    if is_notification(event):
        from notify.email import handler as notify_handler

        return notify_handler(event, context)
    try:
        accepted = aws_accept_load().execute(event)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        return response(400, {"message": str(exc)})
    bucket, key = accepted.uri.removeprefix("s3://").split("/", 1)
    return response(
        202,
        {
            "message": "Carga recibida. El pipeline inició en us-east-2.",
            "bucket": bucket,
            "key": key,
            "file_name": accepted.file_name,
            "load_date": accepted.load_date,
            "execution_arn": accepted.execution_arn,
        },
    )
