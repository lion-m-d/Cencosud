"""Adaptadores AWS del contexto de carga."""

from __future__ import annotations

import json
import os


class S3CsvStore:
    def __init__(self, client, bucket: str, prefix: str) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix if prefix.endswith("/") else f"{prefix}/"

    def put_csv(self, content: str, file_name: str) -> tuple[str, str]:
        stored_name = self._available_name(file_name)
        key = f"{self._prefix}{stored_name}"
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/csv",
        )
        return f"s3://{self._bucket}/{key}", stored_name

    def _available_name(self, file_name: str) -> str:
        stem, extension = _stem_and_extension(file_name)
        if not self._exists(f"{stem}{extension}"):
            return f"{stem}{extension}"
        for number in range(1, 1000):
            candidate = f"{stem}_{number}{extension}"
            if not self._exists(candidate):
                return candidate
        raise ValueError(f"No hay un nombre libre para {file_name}")

    def _exists(self, file_name: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=f"{self._prefix}{file_name}")
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = ""
            if isinstance(response, dict):
                code = str(response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True


class StepFunctionsRunner:
    def __init__(self, client, state_machine_arn: str) -> None:
        self._client = client
        self._state_machine_arn = state_machine_arn

    def start(self, input_path: str, load_date: str, file_name: str) -> str:
        execution = self._client.start_execution(
            stateMachineArn=self._state_machine_arn,
            input=json.dumps(
                {"input_path": input_path, "load_date": load_date, "file_name": file_name}
            ),
        )
        return execution["executionArn"]


def _stem_and_extension(file_name: str) -> tuple[str, str]:
    dot = file_name.rfind(".")
    if dot <= 0:
        return file_name, ""
    return file_name[:dot], file_name[dot:]


def aws_accept_load():
    import boto3

    from .accept_load import AcceptLoad

    return AcceptLoad(
        S3CsvStore(boto3.client("s3"), os.environ["BUCKET_NAME"], os.environ.get("RAW_PREFIX", "raw/")),
        StepFunctionsRunner(boto3.client("stepfunctions"), os.environ["STATE_MACHINE_ARN"]),
    )
