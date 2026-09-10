$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$config = Get-Content -Raw -LiteralPath "config.json" | ConvertFrom-Json

function Invoke-PythonStep {
    param(
        [string]$Label,
        [string[]]$Arguments
    )

    Write-Host $Label
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

# Reconstrucción controlada: solo elimina artefactos generados conocidos.
$generatedFiles = @(
    $config.paths.database,
    $config.paths.rates_csv,
    $config.paths.clinics_json,
    $config.paths.data_profile,
    $config.paths.etl_log,
    ("data/sha256_{0}.txt" -f $config.n_appointments)
)

foreach ($file in $generatedFiles) {
    if (Test-Path -LiteralPath $file) {
        Remove-Item -LiteralPath $file -Force
    }
}

Invoke-PythonStep "Generando los datos..." @("scripts\generate_data.py", "--rows", [string]$config.n_appointments)
Invoke-PythonStep "Comprobando reproducibilidad SHA256..." @("scripts\generate_data.py", "--rows", [string]$config.n_appointments)

$pythonFiles = Get-ChildItem -Path "src", "scripts", "tests" -Filter "*.py" -Recurse | ForEach-Object FullName
Invoke-PythonStep "Comprobando sintaxis..." (@("-m", "py_compile") + $pythonFiles)
Invoke-PythonStep "Ejecutando pruebas..." @("-m", "pytest", "-q")

Invoke-PythonStep "Ejecutando el ETL inicial..." @("src\etl.py")
Invoke-PythonStep "Comprobando idempotencia con una segunda ejecución..." @("src\etl.py")
Invoke-PythonStep "Verificando los resultados..." @("scripts\verify_etl.py")
Invoke-PythonStep "Ejecutando el notebook de exploración..." @("scripts\execute_notebook.py")

Write-Host "Proceso completo terminado correctamente."
