#!/bin/bash

# Aplicar las migraciones de la base de datos (sin preguntar)
echo "🔄 Aplicando migraciones de la base de datos..."
python manage.py migrate --no-input --verbosity=1

# Verificar que las migraciones se aplicaron correctamente
echo "✅ Verificando migraciones aplicadas..."
python manage.py showmigrations inventario | grep -E "\[X\]|\[ \]" | tail -3 || true

# Recolectar archivos estáticos (sin preguntar)
echo "📦 Recolectando archivos estáticos..."
python manage.py collectstatic --no-input --verbosity=0

# Iniciar el servidor Gunicorn
echo "🚀 Iniciando servidor Gunicorn..."
gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT"