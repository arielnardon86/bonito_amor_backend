#!/bin/bash

# Script para hacer dump de la base de datos de producción
# Uso: ./scripts/dump_production_db.sh

set -e  # Salir si hay algún error

# Buscar PostgreSQL en las rutas comunes
PG_DUMP_CMD=""
if command -v brew &> /dev/null; then
    # Buscar PostgreSQL@15 primero
    PG_PREFIX=$(brew --prefix postgresql@15 2>/dev/null)
    if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/pg_dump" ]; then
        PG_DUMP_CMD="$PG_PREFIX/bin/pg_dump"
        export PATH="$PG_PREFIX/bin:$PATH"
    else
        # Buscar PostgreSQL genérico
        PG_PREFIX=$(brew --prefix postgresql 2>/dev/null)
        if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/pg_dump" ]; then
            PG_DUMP_CMD="$PG_PREFIX/bin/pg_dump"
            export PATH="$PG_PREFIX/bin:$PATH"
        fi
    fi
fi

# Si no se encontró con brew, buscar en rutas estándar
if [ -z "$PG_DUMP_CMD" ]; then
    if command -v pg_dump &> /dev/null; then
        PG_DUMP_CMD="pg_dump"
    elif [ -f "/opt/homebrew/bin/pg_dump" ]; then
        PG_DUMP_CMD="/opt/homebrew/bin/pg_dump"
        export PATH="/opt/homebrew/bin:$PATH"
    elif [ -f "/usr/local/bin/pg_dump" ]; then
        PG_DUMP_CMD="/usr/local/bin/pg_dump"
        export PATH="/usr/local/bin:$PATH"
    fi
fi

if [ -z "$PG_DUMP_CMD" ]; then
    echo "ERROR: pg_dump no encontrado. Por favor, instala PostgreSQL o agrega al PATH."
    exit 1
fi

echo "========================================="
echo "Dump de Base de Datos de Producción"
echo "========================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que DATABASE_URL de producción esté configurada
if [ -z "$PRODUCTION_DATABASE_URL" ]; then
    echo -e "${RED}ERROR: La variable PRODUCTION_DATABASE_URL no está configurada${NC}"
    echo ""
    echo "Por favor, configura la variable de entorno con la URL de tu base de datos de producción:"
    echo "export PRODUCTION_DATABASE_URL='postgresql://user:password@host:port/dbname'"
    echo ""
    echo "O ejecuta este script con:"
    echo "PRODUCTION_DATABASE_URL='tu-url-aqui' ./scripts/dump_production_db.sh"
    exit 1
fi

# Nombre del archivo de dump
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="backups/production_dump_${TIMESTAMP}.sql"
DUMP_FILE_CUSTOM="backups/production_dump_${TIMESTAMP}.dump"

# Crear directorio de backups si no existe
mkdir -p backups

echo -e "${YELLOW}Haciendo dump de la base de datos de producción...${NC}"
echo ""

# Opción 1: Dump en formato SQL (texto plano, más portable)
echo "Creando dump SQL..."
echo "Conectando a la base de datos de producción..."
echo ""

# Intentar con timeout más largo y opciones adicionales para conexiones remotas
$PG_DUMP_CMD --verbose --no-password "$PRODUCTION_DATABASE_URL" > "$DUMP_FILE" 2>&1

DUMP_EXIT_CODE=$?

if [ $DUMP_EXIT_CODE -eq 0 ]; then
    # Comprimir el archivo
    echo "Comprimiendo dump..."
    gzip -f "$DUMP_FILE"
    echo -e "${GREEN}✓ Dump SQL creado exitosamente: ${DUMP_FILE}.gz${NC}"
else
    echo -e "${RED}✗ Error al crear el dump SQL${NC}"
    echo ""
    echo "Posibles causas:"
    echo "  1. Sin conexión a internet"
    echo "  2. El servidor de base de datos no es accesible desde tu red"
    echo "  3. Necesitas VPN o túnel SSH para acceder"
    echo "  4. El hostname o la URL de conexión es incorrecta"
    echo ""
    echo "Sugerencias:"
    echo "  - Verifica tu conexión a internet"
    echo "  - Intenta hacer ping al servidor:"
    echo "    ping bmbtf23hj0uxx6xl84kb-postgresql.services.clever-cloud.com"
    echo "  - Si usas Clever Cloud, verifica que el servidor esté accesible"
    echo "  - Considera hacer el dump desde el servidor mismo o usar un túnel SSH"
    exit 1
fi

# Opción 2: Dump en formato custom (binario, más eficiente)
echo ""
echo "Creando dump en formato custom..."
$PG_DUMP_CMD -Fc "$PRODUCTION_DATABASE_URL" > "$DUMP_FILE_CUSTOM"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dump custom creado exitosamente: ${DUMP_FILE_CUSTOM}${NC}"
else
    echo -e "${YELLOW}⚠ Error al crear el dump custom (puede requerir instalación adicional)${NC}"
fi

echo ""
echo "========================================="
echo -e "${GREEN}Proceso completado${NC}"
echo "========================================="
echo ""
echo "Archivos creados:"
echo "  - ${DUMP_FILE}.gz (formato SQL comprimido)"
if [ -f "$DUMP_FILE_CUSTOM" ]; then
    echo "  - ${DUMP_FILE_CUSTOM} (formato custom)"
fi
echo ""
echo "Para restaurar en staging, usa:"
echo "  ./scripts/restore_to_staging.sh ${DUMP_FILE}.gz"
echo ""

