#================= IMPORTACIONES =================

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from generate_data import build_appointments, inject_defects, normalize


#================= 3.9 LOTE INCREMENTAL =================

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"
N = 2500


def main():  # Agrega un lote nuevo sin modificar las filas existentes
    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    rng = np.random.default_rng(config["seed"])
    database = ROOT / config["paths"]["database"]
    rates_path = ROOT / config["paths"]["rates_csv"]
    catalog_path = ROOT / config["paths"]["clinics_json"]
    profile_path = ROOT / config["paths"]["data_profile"]

    with sqlite3.connect(database) as connection:
        patients = pd.read_sql_query(f"SELECT * FROM {config['tables']['patients']}", connection)
        existing = pd.read_sql_query(f"SELECT appointment_id, created_at FROM {config['tables']['appointments']}", connection)

    rates = pd.read_csv(rates_path)

    with catalog_path.open(encoding="utf-8") as file:
        catalog = json.load(file)

    last_id = existing["appointment_id"].str[1:].astype(int).max()
    last_created = pd.to_datetime(existing["created_at"], errors="coerce").max()
    weights = normalize(rng.lognormal(0, 1.1, len(patients)))
    clean_batch = build_appointments(rng, N, patients, weights, rates, last_id + 1, "2025-12-01", "2025-12-31")

    scheduled = pd.to_datetime(clean_batch["scheduled_at"])
    available_days = (np.ceil((scheduled - last_created).dt.total_seconds() / 86400).astype(int) - 1).clip(lower=1, upper=44)
    days_before = np.array([rng.integers(1, days + 1) for days in available_days])
    clean_batch["created_at"] = (scheduled - pd.to_timedelta(days_before, unit="D")).dt.strftime("%Y-%m-%d %H:%M:%S")

    new_batch, new_counts = inject_defects(rng, clean_batch, patients, catalog)

    old_created = pd.to_datetime(new_batch["created_at"], errors="coerce").le(last_created)
    original = clean_batch.set_index("appointment_id")

    for row in new_batch.index[old_created]:
        appointment_id = new_batch.at[row, "appointment_id"]
        new_batch.at[row, "scheduled_at"] = original.at[appointment_id, "scheduled_at"]
        new_batch.at[row, "created_at"] = original.at[appointment_id, "created_at"]
        new_batch.at[row, "duration_min"] = 0
        new_batch.at[row, "amount_charged"] = max(abs(float(new_batch.at[row, "amount_charged"])), 1.0)

    with sqlite3.connect(database) as connection:
        new_batch.to_sql(config["tables"]["appointments"], connection, if_exists="append", index=False)

    with profile_path.open(encoding="utf-8") as file:
        profile = json.load(file)

    profile["row_counts"]["appointments"] = len(existing) + len(new_batch)

    for defect, count in new_counts.items():
        profile["defect_counts"][defect] += count

    with profile_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(profile, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print("Citas que había:", len(existing))
    print("Citas nuevas limpias:", len(clean_batch))
    print("Citas nuevas después de D4:", len(new_batch))
    print("Total de citas:", len(existing) + len(new_batch))
    print("Filas nuevas posteriores al watermark:", pd.to_datetime(new_batch["created_at"], errors="coerce").gt(last_created).sum())


if __name__ == "__main__":
    main()
