#!/bin/bash
set -e

# Script para levantar el backend en desarrollo local
# Uso:
#   cd backend
#   chmod +x run_local.sh    # solo la primera vez
#   ./run_local.sh

echo "📂 Cambiando al directorio del backend..."
cd "$(dirname "$0")"

echo "🐍 Verificando entorno virtual..."

# Siempre usar ./venv como entorno virtual
if [ ! -d "venv" ]; then
  echo "⚙️  Creando virtualenv en ./venv..."
  python3 -m venv venv
fi

# Si existe la carpeta pero no tiene scripts de activación, recrearla
if [ ! -f "venv/bin/activate" ] && [ ! -f "venv/Scripts/activate" ]; then
  echo "⚠️  Carpeta venv encontrada pero sin scripts de activación. Recreando..."
  rm -rf venv
  python3 -m venv venv
fi

echo "✅ Activando virtualenv..."
if [ -f "venv/bin/activate" ]; then
  # macOS / Linux
  # shellcheck disable=SC1091
  source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
  # Windows (por si lo ejecutas allí)
  # shellcheck disable=SC1091
  source venv/Scripts/activate
else
  echo "❌ No se encontró el script de activación del virtualenv después de recrearlo."
  echo "   Revisa que python3 esté instalado y vuelve a intentar:"
  echo "   python3 -m venv venv"
  exit 1
fi

echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🔧 Configurando variables de entorno para DESARROLLO..."
export DJANGO_ENVIRONMENT=development
export DJANGO_DEBUG=True
# Asegurar que en local use SQLite (no la DB de producción)
unset DATABASE_URL || true

echo "🗃  Aplicando migraciones..."
python manage.py migrate

echo "🚀 Levantando servidor Django en http://127.0.0.1:8000 ..."
python manage.py runserver 0.0.0.0:8000

