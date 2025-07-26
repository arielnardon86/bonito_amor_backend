# Usa una imagen base de Python oficial. Python 3.12 es la que se muestra en tus logs.
# Puedes ajustar la versión de Python si usas otra.
FROM python:3.12-slim-bookworm

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala las dependencias del sistema necesarias (ej. para psycopg2 si usas PostgreSQL)
# Asegúrate de que apt-get update se ejecute antes de instalar paquetes
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    # Si usas Pillow (para imágenes), necesitarás estas librerías
    libjpeg-dev zlib1g-dev \
    # Limpia el cache de apt para reducir el tamaño de la imagen
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requisitos e instálalos
# Esto se hace antes de copiar el resto del código para aprovechar el cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de tu aplicación
COPY . .

# Establece las variables de entorno de Django (opcional, Render las inyecta)
# ENV DJANGO_SETTINGS_MODULE=mi_tienda_backend.settings

# Expone el puerto que tu aplicación Gunicorn escuchará
EXPOSE 8000

# Comando para ejecutar la aplicación.
# Este es el CRÍTICO. Ejecuta las migraciones en un orden específico, recolecta estáticos y luego inicia Gunicorn.
# Usamos 'sh -c' para que la cadena de comandos se interprete correctamente.
CMD ["/bin/sh", "-c", "python manage.py migrate auth && python manage.py migrate contenttypes && python manage.py migrate sessions && python manage.py migrate admin && python manage.py migrate inventario --fake-initial && python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn mi_tienda_backend.wsgi:application --bind 0.0.0.0:$PORT"]

# NOTA: $PORT es una variable de entorno que Render inyecta automáticamente.
# Asegúrate de que tu Gunicorn se vincule a 0.0.0.0 y use $PORT.
