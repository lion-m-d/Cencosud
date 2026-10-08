"""Valida Silver o Gold dentro del build de DBT y deja el veredicto en DynamoDB."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from reconciliation.adapters.dynamo_store import DynamoControlStore
from reconciliation.adapters.yaml_catalog import YamlRuleCatalog
from reconciliation.application.validate_run import ValidateRun


def main() -> None:
    store = DynamoControlStore(
        table_name=os.environ["CONTROL_TABLE"],
        region=os.environ.get("AWS_REGION", "us-east-2"),
    )
    log_path = os.environ.get("DBT_LOG")
    if log_path and Path(log_path).is_file():
        logged = Path(log_path).read_text(encoding="utf-8", errors="replace")
        store.save_logged_metrics(logged)
        store.save_logged_rejects(logged)
    ValidateRun(YamlRuleCatalog(os.environ["RULES_PATH"]), store, store).assert_passed(
        os.environ["RUN_ID"],
        date.fromisoformat(os.environ["LOAD_DATE"]),
        stage=os.environ["STAGE"],
    )


if __name__ == "__main__":
    main()
