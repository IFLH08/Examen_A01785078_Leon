from uuid import uuid4

import pandas as pd
import pytest

from src.etl import REJECT_COLUMNS, integrate, load, quality_gate, stage, transform, validate


@pytest.fixture
def catalog():
    return {
        "clinicas": [
            {
                "clinic_code": "CL03",
                "nombre": "SaludNorte Guadalupe",
                "ciudad": "Guadalupe",
                "zona": "oriente",
                "aliases": ["CL-03", "cl03", "Clinica Guadalupe"],
            }
        ],
        "especialidad_aliases": {
            "Medicina General": ["med gral", "MEDICINA_GENERAL", "medicina general "]
        },
    }


def appointment_frame(**overrides):
    row = {
        "source_rowid": 1,
        "appointment_id": "A0000001",
        "patient_id": "P000001",
        "clinic_code": "CL03",
        "specialty": "Medicina General",
        "scheduled_at": "2025-06-14 09:00:00",
        "duration_min": 30,
        "status": "completada",
        "amount_charged": 900.0,
        "payment_method": "tarjeta",
        "created_at": "2025-06-01 09:00:00",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def integrated_example(catalog, **overrides):
    staged = stage(appointment_frame(**overrides), str(uuid4()))
    transformed, rejected = transform(staged, catalog)
    assert rejected.empty
    patients = pd.DataFrame(
        [{"patient_id": "P000001", "birth_date": "2000-06-15", "registered_at": "2024-01-01"}]
    )
    rates = pd.DataFrame(
        [{
            "clinic_code": "CL03",
            "specialty": "Medicina General",
            "tarifa_base": 1000,
            "moneda": "MXN",
            "vigencia_desde": "2024-01-01",
        }]
    )
    return integrate(transformed, patients, rates)


def test_patient_age_at_visit_with_known_dates(catalog):
    curated, rejected = integrated_example(catalog)

    assert rejected.empty
    assert curated.iloc[0]["patient_age_at_visit"] == 24


def test_negative_amount_is_rejected():
    staged = stage(appointment_frame(amount_charged=-1.0), str(uuid4()))

    accepted, rejected = validate(staged)

    assert accepted.empty
    assert rejected.iloc[0]["reject_reason"] == "INVALID_AMOUNT"


def test_quality_gate_fails_when_threshold_is_lowered():
    with pytest.raises(RuntimeError, match="Quality gate"):
        quality_gate(rows_read=100, rows_rejected=6, max_reject_pct=0.05)


def test_two_idempotent_loads_keep_same_count(tmp_path, catalog):
    curated, rejected = integrated_example(catalog)
    assert rejected.empty
    empty_rejects = pd.DataFrame(columns=REJECT_COLUMNS)
    database = tmp_path / "test.db"

    load(database, "appointments_curated", "appointments_rejects", curated, empty_rejects)
    first_count = _table_count(database, "appointments_curated")
    load(database, "appointments_curated", "appointments_rejects", curated, empty_rejects)
    second_count = _table_count(database, "appointments_curated")

    assert first_count == second_count == 1


def _table_count(database, table):
    import sqlite3

    with sqlite3.connect(database) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_specialty_alias_is_normalized(catalog):
    staged = stage(appointment_frame(specialty="MEDICINA_GENERAL "), str(uuid4()))

    transformed, rejected = transform(staged, catalog)

    assert rejected.empty
    assert transformed.iloc[0]["specialty"] == "Medicina General"


def test_quoted_clinic_code_is_normalized(catalog):
    staged = stage(appointment_frame(clinic_code=" 'CL03' "), str(uuid4()))

    transformed, rejected = transform(staged, catalog)

    assert rejected.empty
    assert transformed.iloc[0]["clinic_code"] == "CL03"


def test_revenue_gap_uses_matching_rate(catalog):
    curated, rejected = integrated_example(catalog, amount_charged=900.0)

    assert rejected.empty
    assert curated.iloc[0]["revenue_gap"] == pytest.approx(-100.0)
