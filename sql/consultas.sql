-- 1. Ingreso y ticket promedio por especialidad.
-- Interpretación: permite priorizar capacidad en especialidades con mayor ingreso
-- y revisar precios o mezcla de servicios donde el ticket sea comparativamente bajo.
SELECT
    specialty,
    ROUND(SUM(amount_charged), 2) AS ingreso_total,
    ROUND(AVG(amount_charged), 2) AS ticket_promedio,
    COUNT(*) AS citas
FROM appointments_curated
GROUP BY specialty
ORDER BY ingreso_total DESC;

-- 2. Sucursales cuya tasa de no-show supera el promedio general.
-- Interpretación: estas sucursales son candidatas a recordatorios y confirmación
-- previa porque concentran una inasistencia superior a la referencia de la red.
SELECT
    clinic_code,
    COUNT(*) AS citas,
    ROUND(AVG(is_no_show) * 100.0, 2) AS tasa_no_show_pct
FROM appointments_curated
GROUP BY clinic_code
HAVING AVG(is_no_show) > (
    SELECT AVG(is_no_show)
    FROM appointments_curated
)
ORDER BY tasa_no_show_pct DESC;

-- 3. Ingreso mensual por sucursal y cambio contra el mes anterior.
-- Interpretación: una variación negativa orienta la revisión de agenda, demanda
-- o cobro en la sucursal y mes afectados.
WITH ingreso_mensual AS (
    SELECT
        clinic_code,
        strftime('%Y-%m', scheduled_at) AS mes,
        SUM(amount_charged) AS ingreso
    FROM appointments_curated
    GROUP BY clinic_code, strftime('%Y-%m', scheduled_at)
), comparativo AS (
    SELECT
        clinic_code,
        mes,
        ingreso,
        LAG(ingreso) OVER (
            PARTITION BY clinic_code
            ORDER BY mes
        ) AS ingreso_mes_anterior
    FROM ingreso_mensual
)
SELECT
    clinic_code,
    mes,
    ROUND(ingreso, 2) AS ingreso,
    ROUND(ingreso_mes_anterior, 2) AS ingreso_mes_anterior,
    ROUND(ingreso - ingreso_mes_anterior, 2) AS variacion_mensual
FROM comparativo
ORDER BY clinic_code, mes;

-- 4. Diez pacientes con más citas y su brecha de ingreso acumulada.
-- Interpretación: permite diseñar acciones de retención para pacientes frecuentes
-- y detectar si su atención acumula cobros por debajo de la tarifa base.
SELECT
    patient_id,
    COUNT(*) AS numero_citas,
    ROUND(SUM(revenue_gap), 2) AS revenue_gap_acumulado
FROM appointments_curated
GROUP BY patient_id
ORDER BY numero_citas DESC, patient_id
LIMIT 10;

-- 5. Distribución mensual de motivos de rechazo.
-- Interpretación: tendencias crecientes por motivo señalan qué sistema fuente o
-- regla operativa debe corregirse primero para reducir la cuarentena.
SELECT
    COALESCE(strftime('%Y-%m', scheduled_at), 'fecha_invalida') AS mes,
    reject_reason,
    COUNT(*) AS filas_rechazadas,
    ROUND(
        COUNT(*) * 100.0 /
        SUM(COUNT(*)) OVER (
            PARTITION BY COALESCE(strftime('%Y-%m', scheduled_at), 'fecha_invalida')
        ),
        2
    ) AS porcentaje_del_mes
FROM appointments_rejects
GROUP BY
    COALESCE(strftime('%Y-%m', scheduled_at), 'fecha_invalida'),
    reject_reason
ORDER BY mes, filas_rechazadas DESC, reject_reason;
