#================= IMPORTACIONES =================

import json
import logging
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"

APPOINTMENT_COLUMNS = ["appointment_id", "patient_id", "clinic_code", "specialty", "scheduled_at", "duration_min", "status", "amount_charged", "payment_method", "created_at"]
CURATED_COLUMNS = ["run_id", "appointment_id", "patient_id", "clinic_code", "specialty", "scheduled_at", "duration_min", "status", "amount_charged", "payment_method", "created_at", "tarifa_base", "vigencia_desde", "patient_age_at_visit", "is_no_show", "revenue_gap"]
REJECT_COLUMNS = ["run_id", "source_rowid"] + APPOINTMENT_COLUMNS + ["reject_reason", "rejected_at"]


#================= DEFINE =================

def define():  # Lee la configuración y prepara las rutas
    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    paths = {
        "database": ROOT / config["paths"]["database"],
        "rates": ROOT / config["paths"]["rates_csv"],
        "catalog": ROOT / config["paths"]["clinics_json"],
        "log": ROOT / config["paths"]["etl_log"],
    }

    paths["log"].parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=paths["log"], level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", encoding="utf-8", force=True)

    return config, paths


def now():  # Devuelve la fecha actual en formato estable
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


#================= AUDIT =================

def audit(database, table, run_id, started_at, finished_at=None, rows_read=0, rows_loaded=0, rows_rejected=0, status="RUNNING", watermark_before=None, watermark_after=None, error_message=None):  # Registra el estado de la corrida
    with sqlite3.connect(database) as connection:
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                rows_read INTEGER NOT NULL,
                rows_loaded INTEGER NOT NULL,
                rows_rejected INTEGER NOT NULL,
                status TEXT NOT NULL,
                watermark_before TEXT,
                watermark_after TEXT,
                error_message TEXT
            )
        """)

        connection.execute(f"""
            INSERT INTO {table} (run_id, started_at, finished_at, rows_read, rows_loaded, rows_rejected, status, watermark_before, watermark_after, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                finished_at=excluded.finished_at,
                rows_read=excluded.rows_read,
                rows_loaded=excluded.rows_loaded,
                rows_rejected=excluded.rows_rejected,
                status=excluded.status,
                watermark_before=excluded.watermark_before,
                watermark_after=excluded.watermark_after,
                error_message=excluded.error_message
        """, (run_id, started_at, finished_at, rows_read, rows_loaded, rows_rejected, status, watermark_before, watermark_after, error_message))


def get_watermark(database, table):  # Lee la última marca de agua exitosa
    with sqlite3.connect(database) as connection:
        exists = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()

        if not exists:
            return "1900-01-01 00:00:00"

        value = connection.execute(f"SELECT MAX(watermark_after) FROM {table} WHERE status='SUCCESS'").fetchone()[0]

    return value or "1900-01-01 00:00:00"


#================= EXTRACT =================

def extract(config, paths, watermark):  # Extrae solo las citas posteriores al watermark
    with sqlite3.connect(paths["database"]) as connection:
        patients = pd.read_sql_query(f"SELECT * FROM {config['tables']['patients']}", connection)
        appointments = pd.read_sql_query(f"SELECT rowid AS source_rowid, * FROM {config['tables']['appointments']} WHERE datetime(created_at) > datetime(?) ORDER BY rowid", connection, params=(watermark,))

    rates = pd.read_csv(paths["rates"])

    with paths["catalog"].open(encoding="utf-8") as file:
        catalog = json.load(file)

    return appointments, patients, rates, catalog


#================= STAGE =================

def stage(appointments, run_id):  # Crea una copia de trabajo sin alterar la fuente
    data = appointments.copy()
    data["run_id"] = run_id
    data["ingested_at"] = now()
    return data


#================= VALIDATE =================

def validate(data):  # Separa defectos básicos y duplicados
    reason = pd.Series(pd.NA, index=data.index, dtype="object")
    exact = data.duplicated(subset=APPOINTMENT_COLUMNS, keep="first")
    repeated_id = data.duplicated(subset=["appointment_id"], keep="first") & ~exact

    reason.loc[exact] = "DUPLICATE_EXACT"
    reason.loc[reason.isna() & repeated_id] = "DUPLICATE_ID"
    reason.loc[reason.isna() & data["specialty"].isna()] = "NULL_SPECIALTY"
    reason.loc[reason.isna() & data["amount_charged"].isna()] = "NULL_AMOUNT"
    reason.loc[reason.isna() & (data["amount_charged"].lt(0) | data["amount_charged"].gt(3520))] = "INVALID_AMOUNT"
    reason.loc[reason.isna() & data["duration_min"].eq(0) & data["amount_charged"].gt(0)] = "ZERO_DURATION_WITH_CHARGE"
    reason.loc[reason.isna() & ~data["duration_min"].isin([15, 20, 30, 45, 60])] = "INVALID_DURATION"
    reason.loc[reason.isna() & ~data["status"].isin(["completada", "no_show", "cancelada"])] = "INVALID_STATUS"
    reason.loc[reason.isna() & ~data["payment_method"].isin(["efectivo", "tarjeta", "transferencia", "aseguradora"])] = "INVALID_PAYMENT_METHOD"

    rejected = data.loc[reason.notna()].copy()
    rejected["reject_reason"] = reason.loc[reason.notna()]
    accepted = data.loc[reason.isna()].copy()

    return accepted, rejected


#================= TRANSFORM =================

def key(value):  # Normaliza texto para comparar alias
    if pd.isna(value):
        return None

    text = str(value).strip().strip("'\"").strip().replace("_", " ")
    text = "".join(character for character in unicodedata.normalize("NFKD", text) if not unicodedata.combining(character))
    return " ".join(text.lower().split())


def transform(data, catalog):  # Homologa clínicas, especialidades y fechas
    clinic_map = {}
    specialty_map = {}

    for clinic in catalog["clinicas"]:
        for value in [clinic["clinic_code"]] + clinic["aliases"]:
            clinic_map[key(value)] = clinic["clinic_code"]

    for specialty, aliases in catalog["especialidad_aliases"].items():
        for value in [specialty] + aliases:
            specialty_map[key(value)] = specialty

    clean_clinic = data["clinic_code"].map(lambda value: clinic_map.get(key(value)))
    clean_specialty = data["specialty"].map(lambda value: specialty_map.get(key(value)))
    slash_date = data["scheduled_at"].astype(str).str.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$", na=False)
    scheduled = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns, UTC]")
    scheduled.loc[slash_date] = pd.to_datetime(data.loc[slash_date, "scheduled_at"], format="%d/%m/%Y %H:%M", errors="coerce", utc=True)
    scheduled.loc[~slash_date] = pd.to_datetime(data.loc[~slash_date, "scheduled_at"], format="mixed", errors="coerce", utc=True)
    scheduled = scheduled.dt.tz_convert(None)
    created = pd.to_datetime(data["created_at"], format="mixed", errors="coerce", utc=True).dt.tz_convert(None)

    reason = pd.Series(pd.NA, index=data.index, dtype="object")
    reason.loc[clean_clinic.isna()] = "UNKNOWN_CLINIC"
    reason.loc[reason.isna() & clean_specialty.isna()] = "UNKNOWN_SPECIALTY"
    reason.loc[reason.isna() & scheduled.isna()] = "INVALID_SCHEDULED_AT"
    reason.loc[reason.isna() & created.isna()] = "INVALID_CREATED_AT"
    reason.loc[reason.isna() & created.ge(scheduled)] = "CREATED_AFTER_SCHEDULED"

    rejected = data.loc[reason.notna()].copy()
    rejected["reject_reason"] = reason.loc[reason.notna()]
    accepted = data.loc[reason.isna()].copy()
    accepted["clinic_code"] = clean_clinic.loc[accepted.index]
    accepted["specialty"] = clean_specialty.loc[accepted.index]
    accepted["scheduled_at_dt"] = scheduled.loc[accepted.index]
    accepted["created_at_dt"] = created.loc[accepted.index]
    accepted["scheduled_at"] = accepted["scheduled_at_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    accepted["created_at"] = accepted["created_at_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return accepted, rejected


#================= INTEGRATE =================

def integrate(data, patients, rates):  # Integra pacientes y tarifas y calcula variables derivadas
    patient_columns = patients[["patient_id", "birth_date", "registered_at"]]
    merged = data.merge(patient_columns, on="patient_id", how="left", validate="many_to_one")
    merged = merged.merge(rates, on=["clinic_code", "specialty"], how="left", validate="many_to_one")

    registered = pd.to_datetime(merged["registered_at"], errors="coerce")
    birth = pd.to_datetime(merged["birth_date"], errors="coerce")
    scheduled = pd.to_datetime(merged["scheduled_at_dt"], errors="coerce")
    reason = pd.Series(pd.NA, index=merged.index, dtype="object")

    reason.loc[merged["registered_at"].isna()] = "ORPHAN_PATIENT"
    reason.loc[reason.isna() & merged["tarifa_base"].isna()] = "MISSING_RATE"
    reason.loc[reason.isna() & scheduled.lt(registered)] = "APPOINTMENT_BEFORE_REGISTRATION"

    ages = np.floor((scheduled - birth).dt.days / 365.2425)
    reason.loc[reason.isna() & (ages.isna() | ages.lt(0) | ages.gt(120))] = "INVALID_PATIENT_AGE"

    rejected = merged.loc[reason.notna()].copy()
    rejected["reject_reason"] = reason.loc[reason.notna()]
    curated = merged.loc[reason.isna()].copy()
    curated["patient_age_at_visit"] = ages.loc[curated.index].astype(int)
    curated["is_no_show"] = curated["status"].eq("no_show").astype(int)
    curated["revenue_gap"] = (curated["amount_charged"] - curated["tarifa_base"]).round(2)
    curated = curated[CURATED_COLUMNS]

    return curated, rejected


def prepare_rejects(frames):  # Une todos los rechazos con un formato común
    valid_frames = [frame for frame in frames if not frame.empty]

    if not valid_frames:
        return pd.DataFrame(columns=REJECT_COLUMNS)

    rejected = pd.concat(valid_frames, ignore_index=True)
    rejected["rejected_at"] = now()

    for column in REJECT_COLUMNS:
        if column not in rejected.columns:
            rejected[column] = None

    return rejected[REJECT_COLUMNS]


#================= QUALITY GATE =================

def quality_gate(rows_read, rows_rejected, max_reject_pct):  # Detiene la carga si hay demasiados rechazos
    reject_pct = rows_rejected / rows_read if rows_read else 0.0

    if reject_pct > max_reject_pct:
        raise RuntimeError(f"Quality gate falló: {reject_pct:.2%} supera {max_reject_pct:.2%}")

    return reject_pct


#================= LOAD =================

def load(database, curated_table, rejects_table, curated, rejected):  # Carga con UPSERT dentro de una transacción
    curated_sql = f"""
        CREATE TABLE IF NOT EXISTS {curated_table} (
            run_id TEXT NOT NULL,
            appointment_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            clinic_code TEXT NOT NULL,
            specialty TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            duration_min INTEGER NOT NULL,
            status TEXT NOT NULL,
            amount_charged REAL NOT NULL,
            payment_method TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tarifa_base REAL NOT NULL,
            vigencia_desde TEXT NOT NULL,
            patient_age_at_visit INTEGER NOT NULL,
            is_no_show INTEGER NOT NULL,
            revenue_gap REAL NOT NULL
        )
    """

    rejects_sql = f"""
        CREATE TABLE IF NOT EXISTS {rejects_table} (
            run_id TEXT NOT NULL,
            source_rowid INTEGER NOT NULL,
            appointment_id TEXT,
            patient_id TEXT,
            clinic_code TEXT,
            specialty TEXT,
            scheduled_at TEXT,
            duration_min INTEGER,
            status TEXT,
            amount_charged REAL,
            payment_method TEXT,
            created_at TEXT,
            reject_reason TEXT NOT NULL,
            rejected_at TEXT NOT NULL,
            UNIQUE(source_rowid, reject_reason)
        )
    """

    curated_insert = f"""
        INSERT INTO {curated_table} ({', '.join(CURATED_COLUMNS)})
        VALUES ({', '.join(['?'] * len(CURATED_COLUMNS))})
        ON CONFLICT(appointment_id) DO UPDATE SET
            run_id=excluded.run_id,
            patient_id=excluded.patient_id,
            clinic_code=excluded.clinic_code,
            specialty=excluded.specialty,
            scheduled_at=excluded.scheduled_at,
            duration_min=excluded.duration_min,
            status=excluded.status,
            amount_charged=excluded.amount_charged,
            payment_method=excluded.payment_method,
            created_at=excluded.created_at,
            tarifa_base=excluded.tarifa_base,
            vigencia_desde=excluded.vigencia_desde,
            patient_age_at_visit=excluded.patient_age_at_visit,
            is_no_show=excluded.is_no_show,
            revenue_gap=excluded.revenue_gap
    """

    reject_insert = f"""
        INSERT INTO {rejects_table} ({', '.join(REJECT_COLUMNS)})
        VALUES ({', '.join(['?'] * len(REJECT_COLUMNS))})
        ON CONFLICT(source_rowid, reject_reason) DO UPDATE SET run_id=excluded.run_id, rejected_at=excluded.rejected_at
    """

    curated_rows = [tuple(None if pd.isna(value) else value for value in row) for row in curated[CURATED_COLUMNS].itertuples(index=False, name=None)]
    reject_rows = [tuple(None if pd.isna(value) else value for value in row) for row in rejected[REJECT_COLUMNS].itertuples(index=False, name=None)]

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN")
        connection.execute(curated_sql)
        connection.execute(rejects_sql)

        if curated_rows:
            connection.executemany(curated_insert, curated_rows)

        if reject_rows:
            connection.executemany(reject_insert, reject_rows)


#================= EJECUCIÓN PRINCIPAL =================

def main():  # Ejecuta DEFINE hasta AUDIT y controla cualquier falla
    run_id = str(uuid4())
    started_at = now()
    rows_read = 0
    rows_loaded = 0
    rows_rejected = 0
    watermark_before = None
    watermark_after = None
    database = None
    audit_table = None

    try:
        config, paths = define()
        database = paths["database"]
        audit_table = config["tables"]["etl_runs"]
        watermark_before = get_watermark(database, audit_table)
        audit(database, audit_table, run_id, started_at, status="RUNNING", watermark_before=watermark_before)
        logging.info("Run %s iniciado con watermark %s", run_id, watermark_before)

        appointments, patients, rates, catalog = extract(config, paths, watermark_before)
        rows_read = len(appointments)

        if appointments.empty:
            watermark_after = watermark_before
            audit(database, audit_table, run_id, started_at, now(), 0, 0, 0, "SUCCESS", watermark_before, watermark_after)
            logging.info("Run %s sin filas nuevas", run_id)
            return

        watermark_after = pd.to_datetime(appointments["created_at"], errors="coerce").max().strftime("%Y-%m-%d %H:%M:%S")
        staged = stage(appointments, run_id)
        valid_1, rejected_1 = validate(staged)
        valid_2, rejected_2 = transform(valid_1, catalog)
        curated, rejected_3 = integrate(valid_2, patients, rates)
        rejected = prepare_rejects([rejected_1, rejected_2, rejected_3])
        rows_loaded = len(curated)
        rows_rejected = len(rejected)
        reject_pct = quality_gate(rows_read, rows_rejected, config["max_reject_pct"])
        load(database, config["tables"]["curated"], config["tables"]["rejects"], curated, rejected)
        audit(database, audit_table, run_id, started_at, now(), rows_read, rows_loaded, rows_rejected, "SUCCESS", watermark_before, watermark_after)
        logging.info("Run %s exitoso: leídas=%s cargadas=%s rechazadas=%s rechazo=%.2f%%", run_id, rows_read, rows_loaded, rows_rejected, reject_pct * 100)

    except Exception as error:
        logging.exception("Run %s falló", run_id)

        if database is not None and audit_table is not None:
            audit(database, audit_table, run_id, started_at, now(), rows_read, 0, rows_rejected, "FAILED", watermark_before, watermark_after, str(error))

        raise


if __name__ == "__main__":
    main()
