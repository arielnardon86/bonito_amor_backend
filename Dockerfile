# Usa una imagen base oficial de Python
FROM python:3.9-slim-buster

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala dos2unix para manejar los saltos de línea
RUN apt-get update && apt-get install -y dos2unix && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requisitos e instala las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código fuente de tu aplicación al contenedor
COPY . .

# Asegura que start.sh tenga permisos de ejecución y convierte los saltos de línea
RUN chmod +x start.sh && dos2unix start.sh

# Verifica si bash está disponible (solo para depuración, puedes quitarlo después)
RUN ls -l /bin/bash || echo "Error: /bin/bash no encontrado. Instalando bash..." && apt-get update && apt-get install -y bash

# Expone el puerto en el que Gunicorn escuchará
EXPOSE $PORT

# Define el comando para iniciar la aplicación
CMD ["/app/start.sh"]
