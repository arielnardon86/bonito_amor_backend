# Usa una imagen base oficial de Python más reciente (Python 3.12 en Debian Bookworm)
FROM python:3.12-slim-bookworm

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala dos2unix y otras dependencias del sistema necesarias
# Incluyo las dependencias para psycopg2 y Pillow que tenías antes
RUN apt-get update && apt-get install -y \
    dos2unix \
    postgresql-client \
    build-essential \
    libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requisitos e instala las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código fuente de tu aplicación al contenedor
COPY . .

# Asegura que start.sh tenga permisos de ejecución y convierte los saltos de línea
RUN chmod +x start.sh && dos2unix start.sh

# Verifica si bash está disponible (solo para depuración, puedes quitarlo después)
# La imagen slim-bookworm ya debería tener bash, pero es una buena verificación.
RUN ls -l /bin/bash || (echo "Error: /bin/bash no encontrado. Instalando bash..." && apt-get update && apt-get install -y bash)

# Expone el puerto en el que Gunicorn escuchará
EXPOSE 8000 

# Define el comando para iniciar la aplicación
CMD ["/app/start.sh"]
