from __future__ import annotations

from dataclasses import dataclass

from .ports import ObjectStore, PipelineRunner
from .sales_file import csv_from_request, original_file_name, resolve_load_date


@dataclass(frozen=True)
class AcceptedLoad:
    uri: str
    load_date: str
    execution_arn: str
    file_name: str


class AcceptLoad:
    """Caso de uso: valida el archivo, lo deposita y arranca el pipeline."""

    def __init__(self, store: ObjectStore, runner: PipelineRunner) -> None:
        self._store = store
        self._runner = runner

    def execute(self, event: dict) -> AcceptedLoad:
        csv_text = csv_from_request(event)
        load_date = resolve_load_date(event, csv_text)
        uri, file_name = self._store.put_csv(csv_text, original_file_name(event))
        execution_arn = self._runner.start(uri, load_date, file_name)
        return AcceptedLoad(uri, load_date, execution_arn, file_name)
