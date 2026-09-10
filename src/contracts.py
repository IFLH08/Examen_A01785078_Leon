"""Comprobaciones estructurales de la salida curada."""


CURATED_REQUIRED_COLUMNS = [
    "run_id",
    "appointment_id",
    "patient_id",
    "clinic_code",
    "specialty",
    "scheduled_at",
    "duration_min",
    "status",
    "amount_charged",
    "payment_method",
    "created_at",
    "tarifa_base",
    "vigencia_desde",
    "patient_age_at_visit",
    "is_no_show",
    "revenue_gap",
]


def enforce_curated_contract(data):
    """Falla antes de LOAD si la transformación viola el contrato mínimo."""
    missing = [column for column in CURATED_REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError("Columnas curadas faltantes: " + ", ".join(missing))

    null_columns = data[CURATED_REQUIRED_COLUMNS].columns[
        data[CURATED_REQUIRED_COLUMNS].isna().any()
    ].tolist()
    if null_columns:
        raise ValueError("Nulos no permitidos en salida curada: " + ", ".join(null_columns))

    if data["appointment_id"].duplicated().any():
        raise ValueError("appointment_id duplicado en salida curada")

    if not data["is_no_show"].isin([0, 1]).all():
        raise ValueError("is_no_show fuera del dominio 0/1")

    return data
