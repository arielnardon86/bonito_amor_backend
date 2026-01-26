# Script para crear una tienda en development (SQLite)
# Uso: .\scripts\crear_tienda_development.ps1 [nombre_tienda] [direccion] [telefono] [email]

param(
    [Parameter(Position=0)]
    [string]$NombreTienda = "Tienda Development",
    
    [Parameter(Position=1)]
    [string]$Direccion = "Dirección de prueba",
    
    [Parameter(Position=2)]
    [string]$Telefono = "123456789",
    
    [Parameter(Position=3)]
    [string]$Email = "tienda@development.com"
)

# Cambiar al directorio del backend
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
    Write-Host "ERROR: No se encontró Python." -ForegroundColor Red
    exit 1
}

# Asegurar que estamos en modo development
$env:DJANGO_ENVIRONMENT = "development"

Write-Host "=== Creando tienda en DEVELOPMENT (SQLite) ===" -ForegroundColor Cyan
Write-Host "Nombre: $NombreTienda" -ForegroundColor Yellow
Write-Host "Dirección: $Direccion" -ForegroundColor Yellow
Write-Host "Teléfono: $Telefono" -ForegroundColor Yellow
Write-Host "Email: $Email" -ForegroundColor Yellow
Write-Host ""

# Crear script Python temporal
$pythonScript = @"
from inventario.models import Tienda
import sys

nombre_tienda = "$NombreTienda"
direccion = "$Direccion"
telefono = "$Telefono"
email = "$Email"

try:
    # Crear o obtener tienda
    tienda, created = Tienda.objects.get_or_create(
        nombre=nombre_tienda,
        defaults={
            'direccion': direccion,
            'telefono': telefono,
            'email': email,
            'tipo_facturacion': 'NINGUNA',
            'punto_venta': 1,
        }
    )
    
    if created:
        print(f"✅ Tienda '{nombre_tienda}' creada exitosamente")
        print(f"   ID: {tienda.id}")
        print(f"   Nombre: {tienda.nombre}")
        print(f"   Dirección: {tienda.direccion}")
        print(f"   Teléfono: {tienda.telefono}")
        print(f"   Email: {tienda.email}")
    else:
        print(f"⚠️  Tienda '{nombre_tienda}' ya existe")
        print(f"   ID: {tienda.id}")
        print(f"   Nombre: {tienda.nombre}")
        print(f"   Dirección: {tienda.direccion}")
        print(f"   Teléfono: {tienda.telefono}")
        print(f"   Email: {tienda.email}")
        
    print("")
    print("=== INFORMACIÓN DE LA TIENDA ===")
    print(f"Nombre (slug): {tienda.nombre}")
    print(f"ID: {tienda.id}")
    print("")
    print("✅ ¡Tienda lista para usar!")
    
except Exception as e:
    print(f"❌ Error al crear tienda: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"@

# Guardar script temporal
$tempScript = [System.IO.Path]::GetTempFileName() + ".py"
$pythonScript | Out-File -FilePath $tempScript -Encoding UTF8

try {
    # Ejecutar el script
    & $PythonCmd manage.py shell < $tempScript
} finally {
    # Eliminar script temporal
    if (Test-Path $tempScript) {
        Remove-Item $tempScript -Force
    }
}
