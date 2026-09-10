"""Agregación equivalente en pandas y PySpark para SaludNorte."""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"


def pandas_aggregate(data):
    frame = data.copy()
    frame["month"] = pd.to_datetime(frame["scheduled_at"]).dt.strftime("%Y-%m")
    return (
        frame.groupby(["clinic_code", "specialty", "month"], as_index=False)
        .agg(
            revenue=("amount_charged", "sum"),
            no_show_rate=("is_no_show", "mean"),
        )
        .assign(
            revenue=lambda value: value["revenue"].round(2),
            no_show_rate=lambda value: (value["no_show_rate"] * 100).round(4),
        )
    )


def create_spark_session(app_name="SaludNorteAggregation"):
    from pyspark.sql import SparkSession

    java_check = subprocess.run(
        ["java", "-version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    java_text = java_check.stderr + java_check.stdout
    version_match = re.search(r'version "(?:(1)\.)?(\d+)', java_text)
    if not version_match:
        raise RuntimeError("No se pudo determinar la versión de Java requerida por Spark")
    java_major = int(version_match.group(2))
    if java_major < 17:
        raise RuntimeError(f"PySpark 4.2 requiere Java 17 o posterior; se detectó Java {java_major}")

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    spark = (
        SparkSession.builder
        .master("local[*]")
        .appName(app_name)
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def spark_aggregate(data):
    from pyspark.sql import functions as functions

    prepared = data.withColumn(
        "month",
        functions.date_format(functions.to_timestamp("scheduled_at"), "yyyy-MM"),
    )
    return (
        prepared.groupBy("clinic_code", "specialty", "month")
        .agg(
            functions.round(functions.sum("amount_charged"), 2).alias("revenue"),
            functions.round(functions.avg("is_no_show") * 100, 4).alias("no_show_rate"),
        )
        .orderBy("clinic_code", "specialty", "month")
    )


def main():
    parser = argparse.ArgumentParser(description="Agregación PySpark de appointments_curated")
    parser.add_argument("--explain", action="store_true", help="Muestra el plan físico, incluido el Exchange del shuffle.")
    args = parser.parse_args()

    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    database = ROOT / config["paths"]["database"]
    with sqlite3.connect(database) as connection:
        data = pd.read_sql_query(
            f"SELECT clinic_code, specialty, scheduled_at, amount_charged, is_no_show FROM {config['tables']['curated']}",
            connection,
        )

    spark = create_spark_session()
    try:
        spark_data = spark.createDataFrame(data)
        result = spark_aggregate(spark_data)
        if args.explain:
            result.explain(mode="formatted")
        result.show(40, truncate=False)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
