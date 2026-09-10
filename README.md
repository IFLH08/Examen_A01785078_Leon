# SaludNorte — pipeline de Data Engineering

Proyecto individual de examen para la matrícula **A01785078**. La semilla reproducible es **785078**.

## Caso y objetivo

**Red de clínicas "SaludNorte".** Operan 5 sucursales y 8 especialidades. El área de operación necesita una tabla curada de citas médicas para medir ingreso real por especialidad y sucursal, y la tasa de inasistencia (*no-show*). Hoy no puede: la información de pacientes y citas vive en una base operativa, las tarifas llegan en un CSV que mantiene Finanzas a mano, y el catálogo de sucursales viene en un JSON con nombres escritos de varias formas.

El pipeline produce `appointments_curated`, `appointments_rejects` y `etl_runs` mediante las etapas:

```text
DEFINE → EXTRACT → STAGE → VALIDATE → TRANSFORM → INTEGRATE → QUALITY GATE → LOAD → AUDIT
```

La tabla curada permite decidir en qué especialidad y sucursal ajustar capacidad, recordatorios y políticas de cobro, usando ingreso, brecha contra tarifa y no-show confiables.

## Estructura

```text
.
├── config.json                     # semilla, rutas, tablas y umbrales
├── run_all.ps1                     # reconstrucción y verificaciones principales
├── src/
│   ├── contracts.py                # contrato estructural ejecutable
│   ├── etl.py                      # pipeline incremental e idempotente
│   └── spark_agg.py                # agregación PySpark local[*]
├── scripts/
│   ├── generate_data.py            # tres fuentes + D1–D7 + SHA256
│   ├── append_new_batch.py         # lote incremental
│   ├── verify_etl.py               # auditoría independiente
│   ├── run_queries.py              # ejecutor de las cinco consultas
│   ├── execute_notebook.py         # ejecución reproducible del notebook
│   └── benchmark.py                # pandas vs Spark, tres repeticiones
├── notebooks/01_exploracion.ipynb # siete preguntas y contraste D1–D7
├── sql/consultas.sql               # cinco consultas SQLite
├── tests/test_etl.py                # siete pruebas aisladas
├── docs/                            # diccionario, contrato y runbook
└── data/                            # generado; no versionado
```

## Instalación y ejecución en PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_all.ps1
```

`run_all.ps1` borra únicamente artefactos generados conocidos, genera dos veces, compara SHA256, compila los `.py`, ejecuta las siete pruebas, corre dos veces el ETL, verifica las tablas y ejecuta el notebook. No usa rutas absolutas ni un orquestador.

Comandos individuales:

```powershell
python .\scripts\generate_data.py --rows 60000
python .\src\etl.py
python .\scripts\verify_etl.py
python .\scripts\run_queries.py
python -m pytest -q
python .\scripts\benchmark.py
```

## Resultados reproducidos en esta máquina

Generación con las versiones fijadas en `requirements.txt`:

| Métrica | Resultado |
|---|---:|
| Pacientes | 8,000 |
| Citas limpias | 60,000 |
| Citas después de D4 | 61,200 |
| D1 / D2 / D3 / D4 | 1,200 / 600 / 1,800 / 1,200 |
| D5 / D6 / D7 | 3,000 / 2,400 / 300 |
| Concentración del top 30% | 73.67% |
| SHA256 en dos generaciones | `604c717a2252ab8d61b3a44e51777c9b5ccdfd7c7ab2c2a1f442f1acc314168d` en ambas |

ETL inicial:

| Leídas | Curadas | Rechazadas | Rechazo |
|---:|---:|---:|---:|
| 61,200 | 56,100 | 5,100 | 8.33% |

La segunda ejecución leyó 0 filas y mantuvo los conteos. Los ocho motivos observados fueron `ORPHAN_PATIENT`, `NULL_SPECIALTY`, `NULL_AMOUNT`, `INVALID_AMOUNT`, `DUPLICATE_ID`, `DUPLICATE_EXACT`, `ZERO_DURATION_WITH_CHARGE` y `APPOINTMENT_BEFORE_REGISTRATION`.

El notebook midió que un `INNER JOIN` ingenuo reduce 61,200 filas a 54,900: pierde 6,300 (10.29%). Homologar primero y usar `LEFT JOIN` evita que esas pérdidas queden ocultas.

## Demostraciones evaluables

### Reproducibilidad

```powershell
python .\scripts\generate_data.py --rows 60000
python .\scripts\generate_data.py --rows 60000
Get-Content .\data\sha256_60000.txt
```

La segunda corrida debe imprimir `coincide con la ejecución anterior`.

### Idempotencia

```powershell
python .\src\etl.py
python .\scripts\verify_etl.py
python .\src\etl.py
python .\scripts\verify_etl.py
```

La segunda corrida lee 0 y no duplica filas; las cargas usan UPSERT por `appointment_id`.

### Incrementalidad

```powershell
python .\scripts\append_new_batch.py
python .\src\etl.py
python .\scripts\verify_etl.py
```

Resultado medido: **2,550 leídas, 2,338 cargadas y 212 rechazadas**. El total quedó en 58,438 curadas y 5,312 rechazadas. Una ejecución posterior leyó 0.

### Quality gate y atomicidad

Con `max_reject_pct=0.05`, el ETL terminó con exit code 1 porque 8.33% supera 5%. La auditoría registrada fue `FAILED`, 61,200 leídas, 0 cargadas, 5,100 rechazadas y watermark `1900-01-01 00:00:00` antes/después. No existían las tablas curada ni de rechazos, demostrando que no hubo carga parcial. El valor final de `config.json` está restaurado a 0.10.

## Consultas e interpretación

Las cinco consultas de `sql/consultas.sql` se ejecutaron con `scripts/run_queries.py`.

1. **Ingreso por especialidad.** Medicina General encabezó con **$8,774,334.70 MXN** y ticket promedio de **$1,255.81**; Traumatología quedó al final con **$5,370,074.60**. Esto orienta capacidad hacia las líneas de mayor ingreso y revisión de tarifa/mezcla en las de menor ticket.
2. **No-show por sucursal.** El promedio general fue **13.00%**. CL01 (**13.36%**) fue la única sucursal que lo superó; ahí conviene priorizar confirmaciones y recordatorios.
3. **Variación mensual.** La consulta produjo 115 filas y usa `LAG`. Por ejemplo, CL01 cayó **$139,371.23** de enero a febrero de 2025; esa caída amerita revisar agenda y demanda del mes.
4. **Pacientes frecuentes.** P004661 tuvo **244 citas** y `revenue_gap` acumulado de **−$43,406.56**; es un caso prioritario para revisar política de cobro y retención.
5. **Rechazos por mes.** `ORPHAN_PATIENT` fue el principal motivo global (**1,200 filas**). La distribución mensual permite localizar cuándo aumenta cada defecto y dirigir la corrección al sistema fuente correspondiente.

## Spark y benchmark

`src/spark_agg.py` implementa únicamente ingreso y tasa de no-show por `clinic_code × specialty × mes` en `local[*]`. `scripts/benchmark.py` mide tres repeticiones, mediana, overhead de inicio, plan `.explain()`, tabla, gráfica y métricas de skew.

Mediciones reales disponibles de pandas:

| Filas | Mediana pandas (s) | Top 30% pacientes | Máx./mediana de grupos |
|---:|---:|---:|---:|
| 60,000 | 0.196 | 73.67% | 3.343 |
| 250,000 | 0.828 | 71.95% | 3.046 |
| 1,000,000 | 3.319 | 71.58% | 3.058 |
| 4,000,000 | 14.487 | 71.48% | 3.015 |

Spark no pudo medirse en esta máquina: PySpark 4.2 requiere Java 17 y se detectó Java 8 (error real `UnsupportedClassVersionError`, class file 61 vs 52). Por tanto, el overhead, los tiempos Spark, el punto de inflexión y la inspección real del `Exchange` quedan pendientes; el script los genera al instalar Java 17 y guarda `docs/spark_explain.txt`. El skew de pacientes no es clave del `groupBy`, así que no debería trasladarse directamente a ese shuffle; sí existe desbalance esperado por sucursal (30% frente a 10%), resumido por la razón máx./mediana. Con pandas terminando 4M en 14.487 s y sin medición Spark válida, **no se recomienda migrar hoy**; se debe reevaluar solo después de obtener el crossover en el mismo hardware.

## Documentación adicional

- `docs/data_dictionary.md`: columnas de las tres fuentes y D1–D7.
- `docs/data_contract.md`: contrato completo de `appointments_curated`.
- `docs/runbook.md`: fallos, logs, reproceso, incremental, escalamiento y programación.
