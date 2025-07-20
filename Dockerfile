# Usa una imagen base de Python 3.12.x de Debian (Render usa Ubuntu/Debian)
FROM python:3.12-slim-bookworm 

# Instala las dependencias del sistema operativo que psycopg-binary podría necesitar
# build-essential: herramientas básicas de compilación (gcc, g++, make)
# libpq-dev: librerías de desarrollo de PostgreSQL (para psycopg-binary)
# python3-dev: archivos de encabezado y bibliotecas para construir extensiones de Python
# postgresql-client: ¡Añadido para el comando 'psql'!
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    python3-dev \
    postgresql-client \
    && \
    rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo en el contenedor
WORKDIR /usr/src/app

# Copia los archivos de requerimientos
COPY requirements.txt ./

# Instala las dependencias, asegurando que pip esté actualizado
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia todo el código de tu aplicación
COPY . .

# Expone el puerto que usa Gunicorn (típicamente 8000)
EXPOSE 8000

# Comando para iniciar la aplicación con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "mi_tienda_backend.wsgi:application"]