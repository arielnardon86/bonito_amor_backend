    #!/bin/bash

    # Aplicar las migraciones de la base de datos
    echo "Aplicando migraciones de la base de datos..."
    python manage.py migrate

    # Iniciar el servidor Gunicorn
    echo "Iniciando servidor Gunicorn..."
    gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:"$PORT"
    