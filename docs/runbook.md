# Runbook operativo — SaludNorte

## Instalación

Desde PowerShell, en la raíz del proyecto:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PySpark 4.2 requiere una instalación de Java compatible y `JAVA_HOME` configurado. Valídalo con `java -version` antes del benchmark.

## Ejecución completa

```powershell
.\run_all.ps1
```

El comando regenera las fuentes, verifica dos veces la huella SHA256, ejecuta el ETL y muestra sus conteos. Un código de salida distinto de cero indica fallo.

## Diagnóstico de fallos

```powershell
Get-Content .\data\etl.log -Tail 100
$LASTEXITCODE
```

Busca el `run_id`, la etapa reportada y el mensaje `ERROR`. La tabla `etl_runs` conserva `FAILED`; el watermark efectivo solo considera corridas `SUCCESS`.

## Quality gate

Si el porcentaje rechazado supera `max_reject_pct`, no se cargan filas ni avanza el watermark.

1. Revisa los motivos con `python .\scripts\verify_etl.py`.
2. Corrige la fuente o la regla del catálogo; no aumentes el umbral sin aprobación del responsable de datos.
3. Ejecuta de nuevo `python .\src\etl.py`.
4. Confirma una corrida `SUCCESS` y los conteos esperados.

Para demostrar el fallo de 5% conservando la configuración:

```powershell
Copy-Item .\config.json .\config.backup.json
$config = Get-Content .\config.json -Raw | ConvertFrom-Json
$config.max_reject_pct = 0.05
$config | ConvertTo-Json -Depth 10 | Set-Content .\config.json -Encoding utf8
python .\scripts\generate_data.py --rows 60000
python .\src\etl.py
Move-Item -Force .\config.backup.json .\config.json
```

La ejecución del ETL debe devolver un código distinto de cero, dejar la corrida en `FAILED` y no crear ni modificar filas curadas/rechazadas.

## Reprocesar un día

El reproceso usa `created_at` y UPSERT, por lo que no duplica citas ni retrocede la marca de agua:

```powershell
python .\src\etl.py --reprocess-date 2025-11-20
python .\scripts\verify_etl.py
```

## Lote incremental

```powershell
python .\scripts\append_new_batch.py
python .\src\etl.py
python .\scripts\verify_etl.py
```

El script agrega 2,500 citas limpias (2,550 tras D4) y no actualiza filas fuente existentes. La siguiente corrida extrae solo registros con `created_at` posterior al último watermark exitoso.

## Escalamiento

- Incidente de fuente SQLite o catálogo: responsable de Ingeniería de Datos.
- Tarifa ausente o monto anómalo: dueño del archivo de Finanzas.
- Definición clínica o regla de negocio: Operaciones de SaludNorte.
- Incidente no resuelto o riesgo de reporte incorrecto: profesor/propietario del producto antes de publicar resultados.

## Programación

Task Scheduler puede ejecutar diariamente el programa `powershell.exe` con los argumentos:

```text
-NoProfile -ExecutionPolicy Bypass -File "<ruta-del-proyecto>\run_all.ps1"
```

En Linux, el equivalente conceptual en `cron` sería:

```text
0 2 * * * cd /ruta/al/proyecto && ./.venv/bin/python src/etl.py
```

No se usa Airflow ni otro orquestador: la programación queda fuera del pipeline evaluado.
