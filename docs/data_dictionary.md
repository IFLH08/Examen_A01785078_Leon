# Diccionario de datos

Este documento describe las columnas, tipos y reglas de las fuentes del proyecto SaludNorte.

## Fuente: `clinica.db` — Tabla `patients`

| Columna | Tipo | Dominio válido | ¿Permite nulos? | Origen | Defecto relacionado |
|---|---|---|---|---|---|
| `patient_id` | TEXT | `P` seguido de 6 dígitos; valor único | No | SQLite: `patients` | Ninguno |
| `birth_date` | TEXT | Fecha `YYYY-MM-DD` entre 1940-01-01 y 2015-12-31 | No | SQLite: `patients` | Ninguno |
| `sex` | TEXT | `F` o `M` | No | SQLite: `patients` | Ninguno |
| `city` | TEXT | Una de las 6 ciudades definidas | No | SQLite: `patients` | Ninguno |
| `insurance` | TEXT | `ninguno`, `basico` o `premium` | No | SQLite: `patients` | Ninguno |
| `registered_at` | TEXT | Fecha `YYYY-MM-DD` entre 2022-01-01 y 2023-12-31 | No | SQLite: `patients` | D7 |

## Fuente: `clinica.db` — Tabla `appointments`

| Columna | Tipo | Dominio válido | ¿Permite nulos? | Origen | Defecto relacionado |
|---|---|---|---|---|---|
| `appointment_id` | TEXT | `A` seguido de 7 dígitos; debe ser único | No | SQLite: `appointments` | D4 |
| `patient_id` | TEXT | Debe existir en `patients.patient_id` | No | SQLite: `appointments` | D1 |
| `clinic_code` | TEXT | `CL01`, `CL02`, `CL03`, `CL04` o `CL05` | No | SQLite: `appointments` | D6 |
| `specialty` | TEXT | Una de las 8 especialidades autorizadas | No | SQLite: `appointments` | D3, D5 |
| `scheduled_at` | TEXT | Fecha y hora válida entre 2024-01-01 y 2025-12-31 | No | SQLite: `appointments` | D6, D7 |
| `duration_min` | INTEGER | `15`, `20`, `30`, `45` o `60` | No | SQLite: `appointments` | D7 |
| `status` | TEXT | `completada`, `no_show` o `cancelada` | No | SQLite: `appointments` | Ninguno |
| `amount_charged` | REAL | Valor entre `0.0` y `3520.0` | No | SQLite: `appointments` | D2, D3, D4, D7 |
| `payment_method` | TEXT | `efectivo`, `tarjeta`, `transferencia` o `aseguradora` | No | SQLite: `appointments` | Ninguno |
| `created_at` | TEXT | Fecha y hora válida, anterior a `scheduled_at` | No | SQLite: `appointments` | Ninguno |

## Fuente: `tarifas_especialidad.csv`

| Columna | Tipo | Dominio válido | ¿Permite nulos? | Origen | Defecto relacionado |
|---|---|---|---|---|---|
| `clinic_code` | TEXT | `CL01`, `CL02`, `CL03`, `CL04` o `CL05` | No | CSV de Finanzas | Ninguno |
| `specialty` | TEXT | Una de las 8 especialidades autorizadas | No | CSV de Finanzas | Ninguno |
| `tarifa_base` | INTEGER | Entre 450 y 2200; múltiplo de 50 | No | CSV de Finanzas | Ninguno |
| `moneda` | TEXT | Siempre `MXN` | No | CSV de Finanzas | Ninguno |
| `vigencia_desde` | TEXT | `2024-01-01` o `2025-01-01` | No | CSV de Finanzas | Ninguno |

## Fuente: `catalogo_clinicas.json`

| Campo | Tipo | Dominio válido | ¿Permite nulos? | Origen | Defecto relacionado |
|---|---|---|---|---|---|
| `clinicas[].clinic_code` | TEXT | Código único entre `CL01` y `CL05` | No | JSON de catálogo | D6 |
| `clinicas[].nombre` | TEXT | Nombre oficial de la clínica | No | JSON de catálogo | Ninguno |
| `clinicas[].ciudad` | TEXT | Ciudad donde está la clínica | No | JSON de catálogo | Ninguno |
| `clinicas[].zona` | TEXT | Zona correspondiente a la clínica | No | JSON de catálogo | Ninguno |
| `clinicas[].aliases` | ARRAY | Al menos 3 alias por clínica | No | JSON de catálogo | D6 |
| `especialidad_aliases` | OBJECT | Las 8 especialidades con al menos 2 alias cada una | No | JSON de catálogo | D5 |