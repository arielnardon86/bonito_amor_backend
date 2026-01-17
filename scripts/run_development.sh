#!/bin/bash

# Script para ejecutar comandos Django en modo development (SQLite)
# Uso: ./scripts/run_development.sh [comando]
# Ejemplo: ./scripts/run_development.sh runserver
# Ejemplo: ./scripts/run_development.sh createsuperuser

cd "$(dirname "$0")/.."

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Configurar ambiente
export DJANGO_ENVIRONMENT=development

# Ejecutar comando Django
python3 manage.py "$@"



