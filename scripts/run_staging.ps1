# Script helper para ejecutar comandos Django en modo staging (PowerShell)
# Uso: .\scripts\run_staging.ps1 [comando] [argumentos...]
# Ejemplos:
#   .\scripts\run_staging.ps1 runserver
#   .\scripts\run_staging.ps1 migrate
#   .\scripts\run_staging.ps1 shell

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
} elseif (Test-Path "venv\Scripts\python3.exe") {
    $PythonCmd = "venv\Scripts\python3.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} else {
    Write-Host "ERROR: No se encontró Python. Por favor, instala Python 3." -ForegroundColor Red
    exit 1
}

# Cargar variables de entorno de staging si existe el archivo
if (Test-Path ".env.staging") {
    Get-Content ".env.staging" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") {
                $value = $matches[1]
            }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Asegurar que estamos en modo staging
$env:DJANGO_ENVIRONMENT = "staging"

# Construir el comando completo
$cmdArgs = @($Command) + $Arguments
Write-Host "Ejecutando: $PythonCmd manage.py $($cmdArgs -join ' ')" -ForegroundColor Cyan

# Ejecutar el comando de Django
& $PythonCmd manage.py $cmdArgs
