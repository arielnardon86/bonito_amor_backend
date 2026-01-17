#!/bin/bash

# Script para restaurar un dump de producción en la base de datos de staging local
# Uso: ./scripts/restore_to_staging.sh [archivo_dump]

set -e  # Salir si hay algún error

# Buscar PostgreSQL en las rutas comunes
PSQL_CMD=""
PG_RESTORE_CMD=""

if command -v brew &> /dev/null; then
    # Buscar PostgreSQL@15 primero
    PG_PREFIX=$(brew --prefix postgresql@15 2>/dev/null)
    if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/psql" ]; then
        PSQL_CMD="$PG_PREFIX/bin/psql"
        PG_RESTORE_CMD="$PG_PREFIX/bin/pg_restore"
        export PATH="$PG_PREFIX/bin:$PATH"
    else
        # Buscar PostgreSQL genérico
        PG_PREFIX=$(brew --prefix postgresql 2>/dev/null)
        if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/psql" ]; then
            PSQL_CMD="$PG_PREFIX/bin/psql"
            PG_RESTORE_CMD="$PG_PREFIX/bin/pg_restore"
            export PATH="$PG_PREFIX/bin:$PATH"
        fi
    fi
fi

# Si no se encontró con brew, buscar en rutas estándar
if [ -z "$PSQL_CMD" ]; then
    if command -v psql &> /dev/null; then
        PSQL_CMD="psql"
        PG_RESTORE_CMD="pg_restore"
    elif [ -f "/opt/homebrew/bin/psql" ]; then
        PSQL_CMD="/opt/homebrew/bin/psql"
        PG_RESTORE_CMD="/opt/homebrew/bin/pg_restore"
        export PATH="/opt/homebrew/bin:$PATH"
    elif [ -f "/usr/local/bin/psql" ]; then
        PSQL_CMD="/usr/local/bin/psql"
        PG_RESTORE_CMD="/usr/local/bin/pg_restore"
        export PATH="/usr/local/bin:$PATH"
    fi
fi

if [ -z "$PSQL_CMD" ]; then
    echo "ERROR: psql no encontrado. Por favor, instala PostgreSQL o agrega al PATH."
    exit 1
fi

echo "========================================="
echo "Restaurar Dump a Staging Local"
echo "========================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que se proporcionó un archivo de dump
if [ -z "$1" ]; then
    echo -e "${RED}ERROR: No se proporcionó archivo de dump${NC}"
    echo ""
    echo "Uso: ./scripts/restore_to_staging.sh <archivo_dump>"
    echo ""
    echo "Ejemplos:"
    echo "  ./scripts/restore_to_staging.sh backups/production_dump_20240101_120000.sql.gz"
    echo "  ./scripts/restore_to_staging.sh backups/production_dump_20240101_120000.dump"
    exit 1
fi

DUMP_FILE="$1"

# Verificar que el archivo existe
if [ ! -f "$DUMP_FILE" ]; then
    echo -e "${RED}ERROR: El archivo ${DUMP_FILE} no existe${NC}"
    exit 1
fi

# Cargar variables de entorno de staging
if [ -f ".env.staging" ]; then
    source .env.staging
    echo -e "${GREEN}✓ Variables de entorno cargadas desde .env.staging${NC}"
else
    echo -e "${YELLOW}⚠ Archivo .env.staging no encontrado${NC}"
    echo "Asegúrate de tener configuradas las variables de entorno para staging"
fi

# Determinar la URL de la base de datos de staging
if [ -n "$DATABASE_URL" ]; then
    STAGING_DB_URL="$DATABASE_URL"
elif [ -n "$STAGING_DB_NAME" ] && [ -n "$STAGING_DB_USER" ]; then
    STAGING_DB_HOST="${STAGING_DB_HOST:-localhost}"
    STAGING_DB_PORT="${STAGING_DB_PORT:-5432}"
    STAGING_DB_PASSWORD="${STAGING_DB_PASSWORD:-postgres}"
    STAGING_DB_URL="postgresql://${STAGING_DB_USER}:${STAGING_DB_PASSWORD}@${STAGING_DB_HOST}:${STAGING_DB_PORT}/${STAGING_DB_NAME}"
else
    # Valores por defecto
    STAGING_DB_URL="postgresql://postgres:postgres@localhost:5432/bonito_amor_staging"
    echo -e "${YELLOW}⚠ Usando valores por defecto para la base de datos de staging${NC}"
fi

echo ""
echo -e "${YELLOW}⚠ ADVERTENCIA: Este proceso eliminará todos los datos actuales en la base de datos de staging${NC}"
echo ""
read -p "¿Estás seguro de que quieres continuar? (sí/no): " -r
echo ""

if [[ ! $REPLY =~ ^[Ss][IiÍí]$ ]] && [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]] && [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operación cancelada"
    exit 0
fi

# Extraer el nombre de la base de datos de la URL
DB_NAME=$(echo "$STAGING_DB_URL" | sed -n 's/.*\/\([^?]*\).*/\1/p')

echo ""
echo "Información de la base de datos de staging:"
echo "  URL: ${STAGING_DB_URL//:[^:]*@/:****@}"  # Ocultar password
echo "  Nombre: $DB_NAME"
echo ""

# Verificar conexión a PostgreSQL
echo "Verificando conexión a PostgreSQL..."
if ! $PSQL_CMD "$STAGING_DB_URL" -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: No se pudo conectar a la base de datos de staging${NC}"
    echo "Verifica que:"
    echo "  1. PostgreSQL esté instalado y corriendo"
    echo "  2. La base de datos '$DB_NAME' exista"
    echo "  3. Las credenciales sean correctas"
    exit 1
fi

echo -e "${GREEN}✓ Conexión exitosa${NC}"
echo ""

# Determinar el tipo de archivo y restaurar apropiadamente
if [[ "$DUMP_FILE" == *.dump ]] || [[ "$DUMP_FILE" == *.custom ]]; then
    # Formato custom (binario)
    echo "Restaurando dump en formato custom..."
    $PG_RESTORE_CMD -d "$STAGING_DB_URL" --clean --if-exists --no-owner --no-acl "$DUMP_FILE"
    
elif [[ "$DUMP_FILE" == *.gz ]]; then
    # Formato SQL comprimido
    echo "Descomprimiendo y restaurando dump SQL..."
    gunzip -c "$DUMP_FILE" | $PSQL_CMD "$STAGING_DB_URL"
    
elif [[ "$DUMP_FILE" == *.sql ]]; then
    # Formato SQL sin comprimir
    echo "Restaurando dump SQL..."
    $PSQL_CMD "$STAGING_DB_URL" < "$DUMP_FILE"
    
else
    echo -e "${RED}ERROR: Formato de archivo no reconocido${NC}"
    echo "Formatos soportados: .sql, .sql.gz, .dump, .custom"
    exit 1
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Dump restaurado exitosamente${NC}"
    echo ""
    echo "Siguientes pasos:"
    echo "  1. Ejecutar migraciones de Django (por si acaso):"
    echo "     DJANGO_ENVIRONMENT=staging python manage.py migrate"
    echo ""
    echo "  2. Ejecutar el servidor en modo staging:"
    echo "     DJANGO_ENVIRONMENT=staging python manage.py runserver"
    echo ""
else
    echo ""
    echo -e "${RED}✗ Error al restaurar el dump${NC}"
    exit 1
fi

