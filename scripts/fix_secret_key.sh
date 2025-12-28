#!/bin/bash

# Script para generar y actualizar SECRET_KEY en .env.staging

set -e

echo "Generando SECRET_KEY para staging..."

# Activar venv si existe
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Generar SECRET_KEY usando Django
SECRET_KEY=$(python3 manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" 2>/dev/null)

if [ -z "$SECRET_KEY" ]; then
    # Fallback: generar usando openssl
    SECRET_KEY=$(openssl rand -base64 50 | tr -d '\n' | cut -c1-50)
fi

if [ -z "$SECRET_KEY" ]; then
    echo "ERROR: No se pudo generar SECRET_KEY"
    exit 1
fi

echo "SECRET_KEY generado: ${SECRET_KEY:0:20}..."

# Actualizar .env.staging
if [ -f ".env.staging" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET_KEY|" .env.staging
    else
        # Linux
        sed -i "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET_KEY|" .env.staging
    fi
    echo "✓ SECRET_KEY actualizado en .env.staging"
else
    echo "ERROR: Archivo .env.staging no encontrado"
    echo "Ejecuta primero: ./scripts/setup_staging.sh"
    exit 1
fi



