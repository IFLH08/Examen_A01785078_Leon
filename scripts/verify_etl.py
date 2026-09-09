#================= IMPORTACIONES =================

import json
import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"


def main():  # Consulta e imprime los resultados del ETL
    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    database = ROOT / config["paths"]["database"]

    with sqlite3.connect(database) as connection:
        curated_count = connection.execute(f"SELECT COUNT(*) FROM {config['tables']['curated']}").fetchone()[0]
        rejects_count = connection.execute(f"SELECT COUNT(*) FROM {config['tables']['rejects']}").fetchone()[0]
        latest_run = pd.read_sql_query(f"SELECT * FROM {config['tables']['etl_runs']} ORDER BY started_at DESC LIMIT 1", connection)
        reject_reasons = pd.read_sql_query(f"SELECT reject_reason, COUNT(*) AS rows, ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM {config['tables']['rejects']}), 2) AS percentage FROM {config['tables']['rejects']} GROUP BY reject_reason ORDER BY rows DESC", connection)

    print("Filas en appointments_curated:", curated_count)
    print("Filas en appointments_rejects:", rejects_count)
    print("\nÚltima corrida:")
    print(latest_run.to_string(index=False))
    print("\nRechazos por motivo:")
    print(reject_reasons.to_string(index=False))


if __name__ == "__main__":
    main()
