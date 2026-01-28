#!/bin/bash

# Script para reiniciar el servidor Django en modo staging
# Uso: ./scripts/reiniciar_servidor.sh

set -e

cd "$(dirname "$0")/.." || exit 1

echo "🔄 Reiniciando servidor Django en modo staging..."

# Buscar procesos de Django que estén corriendo
if pgrep -f "manage.py runserver" > /dev/null; then
    echo "⏹️  Deteniendo servidor Django existente..."
    pkill -f "manage.py runserver" || true
    sleep 2
fi

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
    echo "❌ ERROR: No se encontró Python. Por favor, instala Python 3."
    exit 1
fi

echo "🚀 Iniciando servidor Django..."
echo "   Comando: $PYTHON_CMD manage.py runserver"
echo "   Ambiente: staging"
echo ""

# Ejecutar el servidor
$PYTHON_CMD manage.py runserver
