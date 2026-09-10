# Contrato de datos de `appointments_curated`

La tabla curada contiene una fila por `appointment_id`. Todas las columnas son obligatorias: una fila que no puede homologarse o validarse se conserva en `appointments_rejects` con un motivo tipificado; no se imputa información clínica o financiera.

| Columna | Tipo esperado | Rango o dominio válido | Nulable | Acción si falla | Razón de negocio |
|---|---|---|---|---|---|
| `run_id` | TEXT (UUID) | UUID único de la corrida que cargó la fila | No | Fallar la carga | Permite rastrear cada registro hasta una ejecución auditada. |
| `appointment_id` | TEXT | `A` seguido de 7 dígitos; único | No | Rechazar duplicados; conservar la primera aparición | Evita contar dos veces una misma cita. |
| `patient_id` | TEXT | `P` seguido de 6 dígitos y existente en `patients` | No | Rechazar como `ORPHAN_PATIENT` | No se puede atribuir ingreso ni historial a un paciente inexistente. |
| `clinic_code` | TEXT | `CL01`–`CL05`, después de homologar con el catálogo | No | Normalizar alias; si no existe, rechazar como `UNKNOWN_CLINIC` | Las métricas por sucursal requieren una clave canónica. |
| `specialty` | TEXT | Una de las 8 especialidades canónicas del catálogo | No | Normalizar alias; si falta o no existe, rechazar | Evita fragmentar indicadores por variantes ortográficas. |
| `scheduled_at` | TEXT datetime | Fecha válida entre 2024-01-01 y 2025-12-31; posterior a `registered_at` | No | Normalizar formato; rechazar si no parsea o antecede al registro | Una cita previa al alta no es físicamente confiable. |
| `duration_min` | INTEGER | 15, 20, 30, 45 o 60 | No | Rechazar | Duraciones fuera del catálogo distorsionan capacidad y productividad. |
| `status` | TEXT | `completada`, `no_show` o `cancelada` | No | Rechazar | Determina ingreso y tasa de inasistencia. |
| `amount_charged` | REAL | 0.00–3520.00 MXN | No | Rechazar valores nulos, negativos o extremos | Protege los indicadores financieros de importes imposibles. |
| `payment_method` | TEXT | `efectivo`, `tarjeta`, `transferencia` o `aseguradora` | No | Rechazar | Permite conciliación por canal de cobro. |
| `created_at` | TEXT datetime | Fecha parseable y anterior a `scheduled_at` | No | Rechazar | Es la marca de agua del incremental; una fecha inválida puede omitir o repetir datos. |
| `tarifa_base` | REAL | 450–2200 MXN, múltiplo de 50 y combinación clínica-especialidad existente | No | Rechazar como `MISSING_RATE` | Sin tarifa no puede calcularse la brecha de ingreso. |
| `vigencia_desde` | TEXT date | `2024-01-01` o `2025-01-01` según Finanzas | No | Rechazar junto con la tarifa faltante | Conserva la referencia temporal de la tarifa aplicada. |
| `patient_age_at_visit` | INTEGER | 0–120 | No | Rechazar como `INVALID_PATIENT_AGE` | Edades imposibles vuelven poco fiables los análisis clínicos. |
| `is_no_show` | INTEGER | 0 o 1 | No | Fallar la transformación | Es el indicador binario usado en la tasa de inasistencia. |
| `revenue_gap` | REAL | `amount_charged - tarifa_base`, redondeado a 2 decimales | No | Fallar la transformación | Cuantifica subcobro o sobrecobro contra la referencia financiera. |

## Tratamiento explícito de D1–D7

| Defecto | Detección | Tratamiento |
|---|---|---|
| D1: FK huérfana | `LEFT JOIN` sin coincidencia en `patients` | Rechazo `ORPHAN_PATIENT`; no se inventa un paciente. |
| D2: monto inválido | Monto negativo o mayor que el máximo configurable | Rechazo `INVALID_AMOUNT`. |
| D3: nulo relevante | `specialty` o `amount_charged` nulo | Rechazo `NULL_SPECIALTY` o `NULL_AMOUNT`. |
| D4: duplicado | Fila exacta o `appointment_id` repetido | Conserva la primera fila y rechaza las posteriores como `DUPLICATE_EXACT` o `DUPLICATE_ID`. |
| D5: nomenclatura | Alias de especialidad definido en el JSON | Normalización al nombre canónico antes de integrar. |
| D6: defecto silencioso | Código con comillas/espacios o fecha en formato alterno | Normalización del código con el catálogo y parseo explícito de ambos formatos de fecha. |
| D7: regla física | Duración cero con cobro o cita anterior al registro | Rechazo `ZERO_DURATION_WITH_CHARGE` o `APPOINTMENT_BEFORE_REGISTRATION`. |

El ETL usa `LEFT JOIN` para que las faltas de paciente o tarifa sean observables y `validate="many_to_one"` para fallar si una dimensión deja de ser única.
