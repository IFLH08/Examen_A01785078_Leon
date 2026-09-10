"""Benchmark reproducible de la agregación SaludNorte en pandas y Spark."""

import argparse
import contextlib
import io
import json
import statistics
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from generate_data import SPECIALTIES, build_amount_charged, build_patients, build_tarifas, normalize


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"
sys.path.insert(0, str(ROOT))


def build_benchmark_frame(seed, rows, patient_count):
    """Construye en memoria solo las columnas necesarias, sin alterar data/."""
    rng = np.random.default_rng(seed)
    rates = build_tarifas(rng)
    patients = build_patients(rng, patient_count)
    weights = normalize(rng.lognormal(0, 1.1, patient_count))
    patient_ids = rng.choice(patients["patient_id"].to_numpy(), size=rows, p=weights)
    clinic_codes = rng.choice(["CL01", "CL02", "CL03", "CL04", "CL05"], size=rows, p=[0.30, 0.25, 0.20, 0.15, 0.10])
    specialties = rng.choice(SPECIALTIES, size=rows, p=[0.125] * len(SPECIALTIES))
    status = rng.choice(["completada", "no_show", "cancelada"], size=rows, p=[0.78, 0.13, 0.09])
    amounts = build_amount_charged(rng, clinic_codes, specialties, status, rates)
    month_numbers = rng.integers(0, 23, size=rows)
    scheduled_at = (
        pd.Timestamp("2024-01-01") + pd.to_timedelta(month_numbers * 30, unit="D")
    ).strftime("%Y-%m-%d 09:00:00")

    return pd.DataFrame({
        "patient_id": patient_ids,
        "clinic_code": clinic_codes,
        "specialty": specialties,
        "scheduled_at": scheduled_at,
        "amount_charged": amounts,
        "is_no_show": (status == "no_show").astype(int),
    })


def patient_skew_metrics(data, patient_count):
    counts = data["patient_id"].value_counts().reindex(
        ["P" + str(index).zfill(6) for index in range(1, patient_count + 1)],
        fill_value=0,
    ).sort_values(ascending=False)
    top_rows = counts.head(int(patient_count * 0.30)).sum()
    return round(top_rows * 100.0 / len(data), 2)


def grouping_skew_ratio(data):
    sizes = data.assign(
        month=pd.to_datetime(data["scheduled_at"]).dt.strftime("%Y-%m")
    ).groupby(["clinic_code", "specialty", "month"]).size()
    return round(float(sizes.max() / sizes.median()), 3)


def parse_args(config):
    parser = argparse.ArgumentParser()
    parser.add_argument("--volumes", nargs="+", type=int, default=config["benchmark"]["volumes"])
    parser.add_argument("--repetitions", type=int, default=config["benchmark"]["repetitions"])
    parser.add_argument("--pandas-only", action="store_true", help="Mide pandas cuando Spark no está disponible.")
    return parser.parse_args()


def main():
    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)
    args = parse_args(config)

    from src.spark_agg import create_spark_session, pandas_aggregate, spark_aggregate

    spark = None
    spark_startup_seconds = None
    spark_error = None
    if not args.pandas_only:
        try:
            started = time.perf_counter()
            spark = create_spark_session("SaludNorteBenchmark")
            spark.range(1).count()
            spark_startup_seconds = time.perf_counter() - started
        except Exception as error:  # El CSV conserva evidencia del bloqueo real.
            spark_error = f"{type(error).__name__}: {error}"

    results = []
    explain_text = ""
    for rows in args.volumes:
        data = build_benchmark_frame(config["seed"], rows, config["n_patients"])
        pandas_times = []
        spark_times = []

        for _ in range(args.repetitions):
            started = time.perf_counter()
            pandas_aggregate(data)
            pandas_times.append(time.perf_counter() - started)

        if spark is not None:
            for _ in range(args.repetitions):
                started = time.perf_counter()
                spark_result = spark_aggregate(spark.createDataFrame(data))
                spark_result.collect()
                spark_times.append(time.perf_counter() - started)

            if not explain_text:
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    spark_result.explain(mode="formatted")
                explain_text = buffer.getvalue()

        results.append({
            "rows": rows,
            "repetitions": args.repetitions,
            "pandas_median_seconds": statistics.median(pandas_times),
            "spark_median_seconds": statistics.median(spark_times) if spark_times else None,
            "spark_startup_seconds": spark_startup_seconds,
            "patient_top_30_pct": patient_skew_metrics(data, config["n_patients"]),
            "group_max_to_median_ratio": grouping_skew_ratio(data),
            "spark_status": "OK" if spark is not None else (spark_error or "SKIPPED_BY_OPTION"),
        })
        del data

    if spark is not None:
        spark.stop()

    results_frame = pd.DataFrame(results)
    results_path = ROOT / config["benchmark"]["results_csv"]
    chart_path = ROOT / config["benchmark"]["chart_png"]
    explain_path = ROOT / config["benchmark"]["spark_explain"]
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_frame.to_csv(results_path, index=False)
    explain_path.write_text(explain_text or (spark_error or "Spark omitido mediante --pandas-only") + "\n", encoding="utf-8")

    plt.figure(figsize=(8, 5))
    plt.plot(results_frame["rows"], results_frame["pandas_median_seconds"], marker="o", label="pandas")
    if results_frame["spark_median_seconds"].notna().any():
        plt.plot(results_frame["rows"], results_frame["spark_median_seconds"], marker="o", label="Spark")
    plt.xlabel("Filas")
    plt.ylabel("Mediana (segundos)")
    plt.title("SaludNorte: tiempo de agregación por volumen")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()

    print(results_frame.to_string(index=False))
    print(f"Resultados: {results_path}")
    print(f"Gráfica: {chart_path}")
    print(f"Plan Spark: {explain_path}")


if __name__ == "__main__":
    main()
