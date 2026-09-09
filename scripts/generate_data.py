#================= IMPORTACIONES =================

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

#================= 3.1 SEMILLA =================

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"



#================= 3.3 TABLA PATIENTS =================

CITIES = ["Monterrey", "San Nicolás", "Guadalupe", "Apodaca", "Escobedo", "Santa Catarina"]


def build_dates(rng, start, end, n):  # Genera fechas aleatorias dentro de un rango
    start_date = np.datetime64(start, "D")
    end_date = np.datetime64(end, "D")
    days = int((end_date - start_date).astype(int)) + 1
    offsets = rng.integers(0, days, size=n)

    return start_date + offsets.astype("timedelta64[D]")


def build_patients(rng, n):  # Genera los datos de los pacientes
    ids = ["P" + str(i).zfill(6) for i in range(1, n + 1)]
    birth_dates = build_dates(rng, "1940-01-01", "2015-12-31", n)
    registered_dates = build_dates(rng, "2022-01-01", "2023-12-31", n)

    return pd.DataFrame({
        "patient_id": ids,
        "birth_date": pd.to_datetime(birth_dates).strftime("%Y-%m-%d"),
        "sex": rng.choice(["F", "M"], size=n, p=[0.54, 0.46]),
        "city": rng.choice(CITIES, size=n, p=[0.28, 0.22, 0.18, 0.14, 0.11, 0.07]),
        "insurance": rng.choice(["ninguno", "basico", "premium"], size=n, p=[0.45, 0.40, 0.15]),
        "registered_at": pd.to_datetime(registered_dates).strftime("%Y-%m-%d"),
    })


#================= 3.4 TABLA APPOINTMENTS =================

CLINICS = ["CL01", "CL02", "CL03", "CL04", "CL05"]

SPECIALTIES = [
    "Medicina General",
    "Pediatría",
    "Traumatología",
    "Cardiología",
    "Dermatología",
    "Ginecología",
    "Odontología",
    "Oftalmología",
]

SPECIALTY_P = [0.125] * 8


#================= 3.4.1 DISTRIBUCIÓN DE PACIENTES =================

def normalize(values):  # Normaliza los pesos para que sumen 1
    return values / values.sum()


#================= 3.4.2 FECHAS Y HORAS =================

def build_scheduled_at(rng, n, start="2024-01-01", end="2025-11-30"):  # Genera las fechas y horas de las citas
    dates = []

    while len(dates) < n:
        missing = n - len(dates)
        sample = build_dates(rng, start, end, max(missing * 2, 100))
        weekdays = pd.to_datetime(sample).dayofweek
        prob = np.where(weekdays < 5, 1.0, np.where(weekdays == 5, 0.4, 0.05))
        accepted = sample[rng.random(len(sample)) < prob]
        dates.extend(accepted.tolist())

    dates = np.array(dates[:n], dtype="datetime64[D]")
    peak_hours = np.arange(9 * 60, 13 * 60 + 1, 15)
    other_hours = np.concatenate([np.arange(8 * 60, 9 * 60, 15), np.arange(13 * 60 + 15, 19 * 60, 15)])

    peak = np.zeros(n, dtype=bool)
    peak[:int(n * 0.55)] = True
    rng.shuffle(peak)

    minutes = np.empty(n, dtype=int)
    minutes[peak] = rng.choice(peak_hours, size=peak.sum())
    minutes[~peak] = rng.choice(other_hours, size=(~peak).sum())

    date_times = pd.to_datetime(dates) + pd.to_timedelta(minutes, unit="m")

    return date_times.strftime("%Y-%m-%d %H:%M:%S")


#================= 3.4.3 MONTO COBRADO =================

def build_amount_charged(rng, clinics, specialties, status, rates):  # Calcula el monto cobrado
    rates_map = rates.set_index(["clinic_code", "specialty"])["tarifa_base"].to_dict()
    tarifa = np.array([rates_map[(clinic, specialty)] for clinic, specialty in zip(clinics, specialties)], dtype=float)

    factor = rng.normal(loc=1.0, scale=0.12, size=len(status))
    factor = np.clip(factor, 0.7, 1.6)
    amount = np.round(tarifa * factor, 2)

    canceled = status == "cancelada"
    amount[canceled] = 0.0

    no_show = status == "no_show"
    no_show_positions = np.where(no_show)[0]
    amount[no_show] = 0.0

    charge = rng.random(len(no_show_positions)) < 0.15
    charge_positions = no_show_positions[charge]
    amount[charge_positions] = np.round(tarifa[charge_positions] * 0.30, 2)

    return amount


def build_appointments(rng, n, patients, weights, rates, start_id=1, start="2024-01-01", end="2025-11-30"):  # Genera las citas limpias
    appointment_ids = ["A" + str(i).zfill(7) for i in range(start_id, start_id + n)]    
    patient_ids = rng.choice(patients["patient_id"].to_numpy(), size=n, p=weights)
    clinic_codes = rng.choice(CLINICS, size=n, p=[0.30, 0.25, 0.20, 0.15, 0.10])
    specialties = rng.choice(SPECIALTIES, size=n, p=SPECIALTY_P)
    scheduled_at = build_scheduled_at(rng, n, start, end)
    durations = rng.choice([15, 20, 30, 45, 60], size=n, p=[0.30, 0.25, 0.25, 0.15, 0.05])
    status = rng.choice(["completada", "no_show", "cancelada"], size=n, p=[0.78, 0.13, 0.09])
    amounts = build_amount_charged(rng, clinic_codes, specialties, status, rates)
    payment_methods = rng.choice(["efectivo", "tarjeta", "transferencia", "aseguradora"], size=n, p=[0.30, 0.35, 0.15, 0.20])
    days_before = rng.integers(1, 45, size=n)
    created_at = (pd.to_datetime(scheduled_at) - pd.to_timedelta(days_before, unit="D")).strftime("%Y-%m-%d %H:%M:%S")

    return pd.DataFrame({
        "appointment_id": appointment_ids,
        "patient_id": patient_ids,
        "clinic_code": clinic_codes,
        "specialty": specialties,
        "scheduled_at": scheduled_at,
        "duration_min": durations,
        "status": status,
        "amount_charged": amounts,
        "payment_method": payment_methods,
        "created_at": created_at,
    })


#================= 3.5 TARIFAS =================

def build_tarifas(rng):  # Genera las 40 tarifas
    rows = []
    dates = np.array(["2024-01-01"] * 32 + ["2025-01-01"] * 8)
    rng.shuffle(dates)

    i = 0

    for clinic in CLINICS:
        for specialty in SPECIALTIES:
            value = int(rng.integers(450, 2200))
            rate = ((value + 25) // 50) * 50

            rows.append({
                "clinic_code": clinic,
                "specialty": specialty,
                "tarifa_base": rate,
                "moneda": "MXN",
                "vigencia_desde": dates[i],
            })

            i += 1

    return pd.DataFrame(rows)


#================= 3.6 CATÁLOGO DE CLÍNICAS =================

def build_catalogo():  # Genera el catálogo y sus alias
    return {
        "clinicas": [
            {"clinic_code": "CL01", "nombre": "SaludNorte Centro", "ciudad": "Monterrey", "zona": "norte", "aliases": ["CL-01", "cl01", "Clinica Centro"]},
            {"clinic_code": "CL02", "nombre": "SaludNorte San Nicolás", "ciudad": "San Nicolás", "zona": "norte", "aliases": ["CL-02", "cl02", "Clinica San Nicolas"]},
            {"clinic_code": "CL03", "nombre": "SaludNorte Guadalupe", "ciudad": "Guadalupe", "zona": "oriente", "aliases": ["CL-03", "cl03", "Clinica Guadalupe"]},
            {"clinic_code": "CL04", "nombre": "SaludNorte Apodaca", "ciudad": "Apodaca", "zona": "noreste", "aliases": ["CL-04", "cl04", "Clinica Apodaca"]},
            {"clinic_code": "CL05", "nombre": "SaludNorte Santa Catarina", "ciudad": "Santa Catarina", "zona": "poniente", "aliases": ["CL-05", "cl05", "Clinica Santa Catarina"]},
        ],
        "especialidad_aliases": {
            "Medicina General": ["med gral", "MEDICINA_GENERAL", "medicina general "],
            "Pediatría": ["pediatria", "PEDIATRIA"],
            "Traumatología": ["traumatologia", "TRAUMA"],
            "Cardiología": ["cardiologia", "CARDIO"],
            "Dermatología": ["dermatologia", "DERMA"],
            "Ginecología": ["ginecologia", "GINE"],
            "Odontología": ["odontologia", "ODONTO"],
            "Oftalmología": ["oftalmologia", "OFTALMO"],
        },
    }


#================= 3.7 DEFECTOS =================

def inject_defects(rng, appointments, patients, catalog):  # Inyecta D1-D7
    data = appointments.copy()
    counts = {}

    base_n = len(data)
    rows = rng.permutation(data.index.to_numpy())
    position = 0

    #================= D1 FK HUÉRFANA =================

    n_d1 = int(base_n * 0.02)
    d1_rows = rows[position:position + n_d1]
    position += n_d1

    fake_numbers = rng.integers(0, 100000, size=n_d1)
    fake_ids = ["P9" + str(number).zfill(5) for number in fake_numbers]
    data.loc[d1_rows, "patient_id"] = fake_ids
    counts["D1"] = n_d1

    #================= D2 MONTO INVÁLIDO =================

    n_d2 = int(base_n * 0.01)
    d2_rows = rows[position:position + n_d2]
    position += n_d2

    half = n_d2 // 2
    negative_rows = d2_rows[:half]
    extreme_rows = d2_rows[half:]

    data.loc[negative_rows, "amount_charged"] = -(data.loc[negative_rows, "amount_charged"].abs() + 1)
    data.loc[extreme_rows, "amount_charged"] = 999999.0
    counts["D2"] = n_d2

    #================= D3 NULO RELEVANTE =================

    n_d3 = int(base_n * 0.03)
    d3_rows = rows[position:position + n_d3]
    position += n_d3

    half = n_d3 // 2
    data.loc[d3_rows[:half], "specialty"] = None
    data.loc[d3_rows[half:], "amount_charged"] = np.nan
    counts["D3"] = n_d3

    #================= D4 DUPLICADOS =================

    n_d4 = int(base_n * 0.02)
    d4_rows = rows[position:position + n_d4]
    position += n_d4

    half = n_d4 // 2
    exact_duplicates = data.loc[d4_rows[:half]].copy()
    almost_duplicates = data.loc[d4_rows[half:]].copy()
    almost_duplicates["amount_charged"] += 1.0

    data = pd.concat([data, exact_duplicates, almost_duplicates], ignore_index=True)
    counts["D4"] = n_d4

    #================= D5 NOMENCLATURA =================

    n_d5 = int(base_n * 0.05)
    d5_rows = rows[position:position + n_d5]
    position += n_d5

    aliases = catalog["especialidad_aliases"]

    for row in d5_rows:
        specialty = data.at[row, "specialty"]
        data.at[row, "specialty"] = rng.choice(aliases[specialty])

    counts["D5"] = n_d5

    #================= D6 DEFECTO SILENCIOSO =================

    n_d6 = int(base_n * 0.04)
    d6_rows = rows[position:position + n_d6]
    position += n_d6

    half = n_d6 // 2
    dirty_clinic_rows = d6_rows[:half]
    different_date_rows = d6_rows[half:]

    for row in dirty_clinic_rows:
        clinic = data.at[row, "clinic_code"]
        data.at[row, "clinic_code"] = f" '{clinic}' "

    date_half = len(different_date_rows) // 2
    ddmm_rows = different_date_rows[:date_half]
    iso_rows = different_date_rows[date_half:]

    ddmm_dates = pd.to_datetime(data.loc[ddmm_rows, "scheduled_at"])
    iso_dates = pd.to_datetime(data.loc[iso_rows, "scheduled_at"])

    data.loc[ddmm_rows, "scheduled_at"] = ddmm_dates.dt.strftime("%d/%m/%Y %H:%M")
    data.loc[iso_rows, "scheduled_at"] = iso_dates.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    counts["D6"] = n_d6

    #================= D7 REGLA FÍSICA IMPOSIBLE =================

    n_d7 = int(base_n * 0.005)
    d7_rows = rows[position:position + n_d7]

    half = n_d7 // 2
    zero_duration_rows = d7_rows[:half]
    early_date_rows = d7_rows[half:]

    data.loc[zero_duration_rows, "duration_min"] = 0
    current_amounts = data.loc[zero_duration_rows, "amount_charged"].fillna(0).abs()
    data.loc[zero_duration_rows, "amount_charged"] = np.maximum(current_amounts, 1.0)

    registered_map = patients.set_index("patient_id")["registered_at"].to_dict()
    registered_dates = pd.to_datetime([registered_map[data.at[row, "patient_id"]] for row in early_date_rows])
    days_before = rng.integers(1, 45, size=len(early_date_rows))
    bad_dates = registered_dates - pd.to_timedelta(days_before, unit="D")

    data.loc[early_date_rows, "scheduled_at"] = bad_dates.strftime("%Y-%m-%d %H:%M:%S")
    data.loc[early_date_rows, "created_at"] = (bad_dates - pd.to_timedelta(1, unit="D")).strftime("%Y-%m-%d %H:%M:%S")
    counts["D7"] = n_d7

    return data, counts

#================= 3.8 MANIFIESTO DE VERIFICACIÓN =================

def write_data_profile(config, patients, appointments, defect_counts):  # Guarda los resultados reales de la generación
    profile = {
        "seed": config["seed"],
        "row_counts": {
            "patients": len(patients),
            "appointments": len(appointments),
        },
        "defect_counts": defect_counts,
    }

    profile_path = ROOT / config["paths"]["data_profile"]
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    with profile_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(profile, file, ensure_ascii=False, indent=2)
        file.write("\n")


#================= 3.10 ESCALAMIENTO =================

def parse_rows():  # Lee la cantidad de citas indicada con --rows
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int)
    return parser.parse_args().rows


#================= 3.12 CHECKS DE ACEPTACIÓN =================

def calculate_sha256(paths, n, profile_path):  # Calcula y compara la huella SHA256
    h = hashlib.sha256()

    for path in paths:
        h.update(path.name.encode("utf-8"))

        with path.open("rb") as file:
            while True:
                block = file.read(1024 * 1024)

                if not block:
                    break

                h.update(block)

    current_hash = h.hexdigest()
    hash_path = profile_path.parent / ("sha256_" + str(n) + ".txt")

    if not hash_path.exists():
        hash_path.write_text(current_hash + "\n", encoding="utf-8")
        return current_hash, True, True

    previous_hash = hash_path.read_text(encoding="utf-8").strip()
    return current_hash, current_hash == previous_hash, False


def acceptance_checks(n, patients, clean_appointments, appointments, rates, catalog, defect_counts, current_hash, hash_ok, first_hash):  # Ejecuta los checks obligatorios
    appointments_per_patient = clean_appointments["patient_id"].value_counts()
    top_30 = int(len(patients) * 0.30)
    concentration = appointments_per_patient.head(top_30).sum() / len(clean_appointments) * 100

    targets = {"D1": 2.0, "D2": 1.0, "D3": 3.0, "D4": 2.0, "D5": 5.0, "D6": 4.0, "D7": 0.5}
    defects_ok = all(abs((defect_counts[d] / n * 100) - targets[d]) <= 0.3 for d in targets)
    catalog_clinics = {clinic["clinic_code"] for clinic in catalog["clinicas"]}
    appointment_clinics = set(appointments["clinic_code"].dropna())

    checks = {
        "8,000 pacientes e IDs únicos": len(patients) == 8000 and patients["patient_id"].is_unique,
        "Cantidad correcta de appointments": len(appointments) >= n,
        "Concentración del top 30%": 65 <= concentration <= 75,
        "Porcentajes de D1-D7": defects_ok,
        "40 tarifas sin nulos": len(rates) == 40 and rates["tarifa_base"].notna().all(),
        "Todas las clínicas aparecen": catalog_clinics.issubset(appointment_clinics),
        "SHA256 reproducible": hash_ok,
    }

    print("\nRESUMEN DE GENERACIÓN")
    print(f"Pacientes: {len(patients)} | Citas limpias: {len(clean_appointments)} | Citas finales: {len(appointments)}")
    print(f"Tarifas: {len(rates)} | Concentración del top 30%: {concentration:.2f}%")
    print("Defectos inyectados:", ", ".join(f"{defect}: {defect_counts[defect]}" for defect in targets))
    print("SHA256:", current_hash)

    print("\nCHECKS DE ACEPTACIÓN 3.12")

    for name, result in checks.items():
        print(f"{name}: {'OK' if result else 'ERROR'}")

    if first_hash:
        print("Estado SHA256: huella inicial guardada")
    elif hash_ok:
        print("Estado SHA256: coincide con la ejecución anterior")
    else:
        print("Estado SHA256: no coincide con la ejecución anterior")

    failed = [name for name, result in checks.items() if not result]

    if failed:
        raise RuntimeError("Fallaron los checks: " + ", ".join(failed))

    print("\nRESULTADO FINAL: TODOS LOS CHECKS PASARON")


#================= EJECUCIÓN PRINCIPAL =================

def main():  # Genera y guarda las tres fuentes

    rows = parse_rows()

    with CONFIG.open(encoding="utf-8") as file:
        config = json.load(file)

    n = rows if rows is not None else config["n_appointments"]

    if n<=0:
        raise ValueError("El número de citas debe ser mayor que cero.")

    rng = np.random.default_rng(config["seed"])

    # Orden indicado en el pseudocódigo 3.11
    catalog = build_catalogo()
    rates = build_tarifas(rng)
    patients = build_patients(rng, config["n_patients"])
    weights = normalize(rng.lognormal(0, 1.1, len(patients)))
    clean_appointments = build_appointments(rng, n, patients, weights, rates)
    appointments, defect_counts = inject_defects(rng, clean_appointments, patients, catalog)

    #================= GUARDAR SQLITE =================

    database = ROOT / config["paths"]["database"]
    database.parent.mkdir(parents=True, exist_ok=True)

    if database.exists():
        database.unlink()

    with sqlite3.connect(database) as connection:
        patients.to_sql(config["tables"]["patients"], connection, if_exists="replace", index=False)
        appointments.to_sql(config["tables"]["appointments"], connection, if_exists="replace", index=False)

    #================= GUARDAR CSV =================

    rates_path = ROOT / config["paths"]["rates_csv"]
    rates_path.parent.mkdir(parents=True, exist_ok=True)
    rates.to_csv(rates_path, index=False, encoding="utf-8", lineterminator="\n")

    #================= GUARDAR JSON =================

    catalog_path = ROOT / config["paths"]["clinics_json"]
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    with catalog_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(catalog, file, ensure_ascii=False, indent=2)
        file.write("\n")

    #================= GUARDAR MANIFIESTO 3.8 =================

    write_data_profile(config, patients, appointments, defect_counts)

    #================= EJECUTAR CHECKS 3.12 =================

    profile_path = ROOT / config["paths"]["data_profile"]
    current_hash, hash_ok, first_hash = calculate_sha256([database, rates_path, catalog_path, profile_path], n, profile_path)
    acceptance_checks(n, patients, clean_appointments, appointments, rates, catalog, defect_counts, current_hash, hash_ok, first_hash)


if __name__ == "__main__":
    main()
