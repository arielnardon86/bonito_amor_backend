#!/bin/bash

# Script para ejecutar migraciones en Render
# Este script verifica y ejecuta migraciones pendientes

set -e  # Salir si hay algún error

echo "=========================================="
echo "Ejecutando migraciones en Render"
echo "=========================================="

# Verificar que estamos en el entorno correcto
if [ -z "$DJANGO_ENVIRONMENT" ]; then
    echo "Advertencia: DJANGO_ENVIRONMENT no está configurado"
fi

# Ir al directorio del backend
cd /app || cd /opt/render/project/src/backend || pwd

# Mostrar migraciones pendientes
echo ""
echo "Migraciones pendientes:"
python manage.py showmigrations inventario | grep "\[ \]"

echo ""
echo "Ejecutando migraciones..."
python manage.py migrate inventario

echo ""
echo "Migraciones aplicadas. Verificando estado final:"
python manage.py showmigrations inventario | tail -5

echo ""
echo "=========================================="
echo "Migraciones completadas exitosamente"
echo "=========================================="

