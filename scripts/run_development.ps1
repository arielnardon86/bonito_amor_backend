# Script para ejecutar comandos Django en modo development (PowerShell)
# Uso: .\scripts\run_development.ps1 [comando] [argumentos...]
# Ejemplo: .\scripts\run_development.ps1 runserver
# Ejemplo: .\scripts\run_development.ps1 createsuperuser

param(
    [Parameter(Position=0)]
    [string]$Command = "runserver",
    
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

# Cambiar al directorio del script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Split-Path -Parent $ScriptDir
Set-Location $BackendDir

# Determinar qué comando Python usar
$PythonCmd = $null

if (Test-Path "venv\Scripts\python.exe") {
    $PythonCmd = "venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $PythonCmd = ".venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} else {
    Write-Host "ERROR: No se encontró Python. Por favor, instala Python 3." -ForegroundColor Red
    exit 1
}

# Configurar ambiente: development siempre usa SQLite
$env:DJANGO_ENVIRONMENT = "development"
# Quitar DATABASE_URL para forzar SQLite (evitar PostgreSQL sin servicio)
if (Test-Path Env:DATABASE_URL) { Remove-Item Env:DATABASE_URL }

# Para runserver, enlazar explícitamente a 127.0.0.1:8000
$cmdArgs = @($Command) + $Arguments
if ($Command -eq "runserver" -and $Arguments.Count -eq 0) {
    $cmdArgs = @("runserver", "127.0.0.1:8000")
    Write-Host "Usando SQLite. Backend en http://127.0.0.1:8000" -ForegroundColor Green
}
Write-Host "Ejecutando: $PythonCmd manage.py $($cmdArgs -join ' ')" -ForegroundColor Cyan

# Ejecutar comando Django
& $PythonCmd manage.py $cmdArgs
