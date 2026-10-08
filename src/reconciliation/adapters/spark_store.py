"""Mide un DataFrame de Spark. La traza se guarda en DynamoDB, no en Iceberg."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ..domain.models import Metrics

if TYPE_CHECKING:
    from pyspark.sql import DataFrame


def collect_metrics(
    dataframe: "DataFrame",
    *,
    run_id: str,
    pipeline: str,
    layer: str,
    table_name: str,
    grain: tuple[str, ...] = (),
    load_date_column: str | None = None,
    input_count: int | None = None,
    previous_count: int | None = None,
    snapshot_id: str | None = None,
) -> Metrics:
    from pyspark.sql import functions as F

    output_count = dataframe.count()
    grain_count = dataframe.select(*grain).distinct().count() if grain else None
    grain_counts = {"|".join(grain): grain_count} if grain and grain_count is not None else {}
    max_load_date = None
    if load_date_column and output_count:
        raw_date = dataframe.select(F.max(F.col(load_date_column)).alias("value")).first()["value"]
        if raw_date is not None:
            max_load_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
    return Metrics(
        run_id=run_id,
        pipeline=pipeline,
        layer=layer,
        table_name=table_name,
        input_count=input_count,
        output_count=output_count,
        grain_count=grain_count,
        max_load_date=max_load_date,
        previous_count=previous_count,
        snapshot_id=snapshot_id,
        grain_counts=grain_counts,
    )
