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
# Un solo worker (proceso) para no repetir el costo de memoria de cargar toda
# la app Django por duplicado -- eso es lo que hacía que la instancia de 512MB
# de Render se quedara sin memoria al bootear con 2 workers. Pero un solo
# worker 'sync' (el default de gunicorn) atiende UN request a la vez: con más
# de un cajero en simultáneo, o incluso un solo cajero cuyo navegador dispara
# varios requests en paralelo por pantalla, todo se encolaba atrás del primero
# -- de ahí la lentitud reportada. --worker-class gthread + --threads da
# concurrencia real DENTRO del mismo proceso (los threads comparten la memoria
# ya cargada, a diferencia de un segundo worker) -- tiene sentido para esta
# app porque la mayoría del tiempo de cada request es I/O esperando a Postgres,
# no CPU, así que un thread libera el GIL mientras espera y otro puede avanzar.
# --max-requests sigue como salvaguarda ante un crecimiento gradual de memoria.
gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT" --timeout 300 --workers 1 --worker-class gthread --threads 4 --max-requests 300 --max-requests-jitter 50 --log-file -