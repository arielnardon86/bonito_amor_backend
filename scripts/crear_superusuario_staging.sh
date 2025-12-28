#!/bin/bash

# Script para crear un superusuario en staging y asociarlo con una tienda
# Uso: ./scripts/crear_superusuario_staging.sh [username] [email] [password] [tienda_nombre]

set -e

cd "$(dirname "$0")/.."

# Cargar variables de entorno de staging si existe el archivo
if [ -f ".env.staging" ]; then
    export $(grep -v '^#' .env.staging | xargs)
fi

# Asegurar que estamos en modo staging
export DJANGO_ENVIRONMENT=staging

# Determinar qué comando Python usar
PYTHON_CMD=""
if [ -d "venv" ] && [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif [ -d "venv" ] && [ -f "venv/bin/python3" ]; then
    PYTHON_CMD="venv/bin/python3"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: No se encontró Python. Por favor, instala Python 3."
    exit 1
fi

# Valores por defecto
USERNAME=${1:-admin}
EMAIL=${2:-admin@bonitoamor.com}
PASSWORD=${3:-admin123}
TIENDA_NOMBRE=${4:-Test}

echo "=== Creando superusuario en STAGING ==="
echo "Usuario: $USERNAME"
echo "Email: $EMAIL"
echo "Tienda: $TIENDA_NOMBRE"
echo ""

# Ejecutar script de Python para crear usuario y asociarlo con tienda
$PYTHON_CMD manage.py shell << EOF
from inventario.models import User, Tienda
from django.contrib.auth import get_user_model

username = "$USERNAME"
email = "$EMAIL"
password = "$PASSWORD"
tienda_nombre = "$TIENDA_NOMBRE"

# Crear o obtener tienda
tienda, created = Tienda.objects.get_or_create(
    nombre=tienda_nombre,
    defaults={
        'direccion': 'Dirección de prueba',
        'telefono': '123456789',
        'email': email,
    }
)

if created:
    print(f"✅ Tienda '{tienda_nombre}' creada")
else:
    print(f"✅ Tienda '{tienda_nombre}' ya existe")

# Crear o actualizar usuario
User = get_user_model()
if User.objects.filter(username=username).exists():
    user = User.objects.get(username=username)
    user.set_password(password)
    user.email = email
    user.is_superuser = True
    user.is_staff = True
    user.tienda = tienda
    user.save()
    print(f"✅ Usuario '{username}' actualizado (es superusuario y está asociado a la tienda '{tienda_nombre}')")
else:
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        tienda=tienda
    )
    print(f"✅ Usuario '{username}' creado como superusuario y asociado a la tienda '{tienda_nombre}'")

print("")
print("=== CREDENCIALES DE ACCESO ===")
print(f"URL Admin: http://localhost:8000/admin/")
print(f"Usuario: {username}")
print(f"Password: {password}")
print(f"Tienda asociada: {tienda_nombre}")
print("")
print("✅ ¡Listo! Puedes iniciar sesión ahora.")
EOF

