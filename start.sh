#!/bin/bash

# Aplicar las migraciones de la base de datos (sin preguntar)
echo "Aplicando migraciones de la base de datos..."
python manage.py migrate --no-input

# Recolectar archivos estáticos (sin preguntar)
echo "Recolectando archivos estáticos..."
python manage.py collectstatic --no-input

# Iniciar el servidor Gunicorn
echo "Iniciando servidor Gunicorn..."
gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT"