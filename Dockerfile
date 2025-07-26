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
# Esta es la sintaxis de la FORMA "SHELL" de CMD.
# Docker ejecutará esto a través de /bin/sh -c.
# El orden de las migraciones es crucial:
# 1. contenttypes y auth (para asegurar que los tipos de contenido y el modelo de usuario base existan).
# 2. inventario 0001 (aplica específicamente la migración inicial de inventario para crear inventario_user).
# 3. admin (para que pueda usar inventario_user).
# 4. migrate general (para el resto de migraciones pendientes).
CMD python manage.py migrate contenttypes --noinput && \
    python manage.py migrate auth --noinput && \
    python manage.py migrate inventario 0001_initial --noinput && \
    python manage.py migrate admin --noinput && \
    python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput && \
    gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:$PORT
