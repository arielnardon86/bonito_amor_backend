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
# GUNICORN_WORKERS controla cuántos procesos levanta -- default 1 porque en el
# plan actual de Render (512MB) un 2do worker duplica el costo de memoria de
# cargar toda la app Django y eso fue justo lo que hizo que la instancia se
# quedara sin memoria al bootear. Queda como variable de entorno (no
# hardcodeado) para poder subir a 2 con un solo cambio en el dashboard de
# Render el día que se suba de plan (2GB+), sin tocar código ni volver a
# deployar -- con 1 solo worker, si se recicla por --max-requests no queda
# NADA escuchando mientras levanta el reemplazo, y un request que llega justo
# en ese hueco se cae con Network Error (pasó el 21/10 con un cambio/devolución
# real). Con 2+ workers ese hueco lo cubre el otro proceso.
#
# Con 1 worker, --worker-class gthread + --threads da concurrencia real DENTRO
# del mismo proceso (los threads comparten la memoria ya cargada, a diferencia
# de un segundo worker) -- tiene sentido para esta app porque la mayoría del
# tiempo de cada request es I/O esperando a Postgres, no CPU, así que un
# thread libera el GIL mientras espera y otro puede avanzar.
# --max-requests sigue como salvaguarda ante un crecimiento gradual de memoria.
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT" --timeout 300 --workers "$GUNICORN_WORKERS" --worker-class gthread --threads 4 --max-requests 300 --max-requests-jitter 50 --log-file -