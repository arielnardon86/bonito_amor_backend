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
# Un solo worker: con 2 arrancando a la vez, la instancia de 512MB de Render
# se queda sin memoria justo al bootear (cada worker carga por separado toda
# la app Django -- Django/DRF/psycopg2/cryptography/reportlab). --max-requests
# recicla el worker cada tanto, como salvaguarda extra ante un crecimiento
# gradual de memoria con el uso (ej. picos puntuales al generar un PDF grande).
gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT" --timeout 300 --workers 1 --max-requests 300 --max-requests-jitter 50 --log-file -