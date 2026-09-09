#================= CONFIGURACIÓN =================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    $python = "python"
}


#================= GENERACIÓN =================

Write-Host "Generando los datos..."
& $python "scripts\generate_data.py" "--rows" "60000"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}


#================= REPRODUCIBILIDAD =================

Write-Host "Comprobando el SHA256..."
& $python "scripts\generate_data.py" "--rows" "60000"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}


#================= ETL =================

Write-Host "Ejecutando el ETL..."
& $python "src\etl.py"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}


#================= VERIFICACIÓN =================

Write-Host "Verificando los resultados..."
& $python "scripts\verify_etl.py"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Proceso completo terminado correctamente."
