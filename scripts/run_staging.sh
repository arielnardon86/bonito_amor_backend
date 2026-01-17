#!/bin/bash

# Script helper para ejecutar comandos Django en modo staging
# Uso: ./scripts/run_staging.sh [comando] [argumentos...]
# Ejemplos:
#   ./scripts/run_staging.sh runserver
#   ./scripts/run_staging.sh migrate
#   ./scripts/run_staging.sh shell

set -e

# Determinar qué comando Python usar
PYTHON_CMD=""
if [ -d "venv" ] && [ -f "venv/bin/python" ]; then
    # Usar el Python del entorno virtual
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

# Cargar variables de entorno de staging si existe el archivo
if [ -f ".env.staging" ]; then
    export $(grep -v '^#' .env.staging | xargs)
fi

# Asegurar que estamos en modo staging
export DJANGO_ENVIRONMENT=staging

# Ejecutar el comando de Django
$PYTHON_CMD manage.py "$@"

