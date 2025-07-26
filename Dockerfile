# Usa una imagen base de Python oficial. Python 3.12 es la que se muestra en tus logs.
FROM python:3.12-slim-bookworm

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala las dependencias del sistema necesarias (ej. para psycopg2 si usas PostgreSQL)
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requisitos e instálalos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación
COPY . .

# Expone el puerto que tu aplicación Gunicorn escuchará
EXPOSE 8000

# Comando para ejecutar la aplicación.
# Esta secuencia de comandos es crítica para asegurar que inventario_user exista.
# NOTA: Asumimos que la base de datos de Render está LIMPIA (recién creada).
CMD ["/bin/sh", "-c", \
    "python manage.py migrate inventario --noinput && " \
    "python manage.py migrate --noinput && " \
    "python manage.py collectstatic --noinput && " \
    "gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:$PORT" \
]
