"""01-pyspark-pipeline: extrae el CSV, lo deja en bronze y valida esa capa."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

from reconciliation.adapters.dynamo_store import DynamoControlStore
from reconciliation.adapters.spark_store import collect_metrics
from reconciliation.adapters.yaml_catalog import YamlRuleCatalog
from reconciliation.application.validate_run import ValidateRun


REQUIRED_ARGS = [
    "JOB_NAME",
    "RUN_ID",
    "INPUT_PATH",
    "PIPELINE",
    "TARGET_TABLE",
    "LOAD_DATE",
    "RULES_URI",
    "CONTROL_TABLE",
]


def iceberg_table_exists(spark, target: str) -> bool:
    catalog, database, table = target.split(".")
    rows = spark.sql(f"SHOW TABLES IN {catalog}.{database}").collect()
    return any(row.tableName == table for row in rows)


def localize(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    parsed = urlparse(uri)
    destination = Path("/tmp") / Path(parsed.path).name
    boto3.client("s3").download_file(parsed.netloc, parsed.path.lstrip("/"), str(destination))
    return str(destination)


def write_bronze(prepared, target: str) -> None:
    writer = prepared.writeTo(target).using("iceberg").tableProperty("format-version", "2")
    if iceberg_table_exists(prepared.sparkSession, target):
        writer.append()
        return
    try:
        writer.create()
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise
        prepared.writeTo(target).using("iceberg").append()


def main() -> None:
    args = getResolvedOptions(sys.argv, REQUIRED_ARGS)
    glue_context = GlueContext(SparkContext.getOrCreate())
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    controls = DynamoControlStore(args["CONTROL_TABLE"])

    raw = spark.read.option("header", True).option("inferSchema", True).csv(args["INPUT_PATH"])
    input_count = raw.count()
    prepared = (
        raw.withColumn("fecha_carga", F.to_date(F.lit(args["LOAD_DATE"])))
        .withColumn("_ingested_at", F.lit(datetime.utcnow()))
        .withColumn("_run_id", F.lit(args["RUN_ID"]))
    )
    target = args["TARGET_TABLE"]
    database = target.split(".")[-2]
    spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{database}")
    write_bronze(prepared, target)

    current_run = spark.table(target).where(F.col("_run_id") == args["RUN_ID"])
    metrics = collect_metrics(
        current_run,
        run_id=args["RUN_ID"],
        pipeline=args["PIPELINE"],
        layer="bronze",
        table_name=target.replace("glue_catalog.", ""),
        grain=("ticket_id",),
        load_date_column="fecha_carga",
        input_count=input_count,
    )
    controls.save_metrics(metrics)
    ValidateRun(
        YamlRuleCatalog(localize(args["RULES_URI"])),
        controls,
        controls,
    ).assert_passed(args["RUN_ID"], date.fromisoformat(args["LOAD_DATE"]), stage="bronze")
    job.commit()


if __name__ == "__main__":
    main()
