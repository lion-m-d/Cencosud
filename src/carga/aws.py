"""Adaptadores AWS del contexto de carga."""

from __future__ import annotations

import json
import os


class S3CsvStore:
    def __init__(self, client, bucket: str, key: str) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key

    def put_csv(self, content: str) -> str:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key,
            Body=content.encode("utf-8"),
            ContentType="text/csv",
        )
        return f"s3://{self._bucket}/{self._key}"


class StepFunctionsRunner:
    def __init__(self, client, state_machine_arn: str) -> None:
        self._client = client
        self._state_machine_arn = state_machine_arn

    def start(self, input_path: str, load_date: str) -> str:
        execution = self._client.start_execution(
            stateMachineArn=self._state_machine_arn,
            input=json.dumps({"input_path": input_path, "load_date": load_date}),
        )
        return execution["executionArn"]


def aws_accept_load():
    import boto3

    from .accept_load import AcceptLoad

    return AcceptLoad(
        S3CsvStore(boto3.client("s3"), os.environ["BUCKET_NAME"], os.environ["OBJECT_KEY"]),
        StepFunctionsRunner(boto3.client("stepfunctions"), os.environ["STATE_MACHINE_ARN"]),
    )
