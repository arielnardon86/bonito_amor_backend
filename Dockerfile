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

# Comando RUN para ejecutar las migraciones y collectstatic
# Esto se ejecuta durante la fase de construcción de la imagen Docker.
RUN python manage.py migrate contenttypes --noinput && \
    python manage.py migrate auth --noinput && \
    python manage.py migrate inventario 0001_initial --noinput && \
    python manage.py migrate admin --noinput && \
    python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput

# Comando CMD para iniciar la aplicación usando start.sh
# Esto asegura que start.sh se use tanto en Render como localmente.
CMD ["/app/start.sh"]
