#!/bin/bash

# Script para configurar el ambiente de staging local
# Este script crea la base de datos, usuario y configura todo lo necesario

set -e  # Salir si hay algún error

echo "========================================="
echo "Setup de Ambiente de Staging"
echo "========================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que PostgreSQL esté instalado y buscar en rutas comunes
PSQL_CMD=""
PG_ISREADY_CMD=""

# Intentar encontrar PostgreSQL usando brew
if command -v brew &> /dev/null; then
    # Buscar PostgreSQL@15 primero
    PG_PREFIX=$(brew --prefix postgresql@15 2>/dev/null)
    if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/psql" ]; then
        PSQL_CMD="$PG_PREFIX/bin/psql"
        PG_ISREADY_CMD="$PG_PREFIX/bin/pg_isready"
        export PATH="$PG_PREFIX/bin:$PATH"
    else
        # Buscar PostgreSQL genérico
        PG_PREFIX=$(brew --prefix postgresql 2>/dev/null)
        if [ -n "$PG_PREFIX" ] && [ -f "$PG_PREFIX/bin/psql" ]; then
            PSQL_CMD="$PG_PREFIX/bin/psql"
            PG_ISREADY_CMD="$PG_PREFIX/bin/pg_isready"
            export PATH="$PG_PREFIX/bin:$PATH"
        fi
    fi
fi

# Si no se encontró con brew, buscar en rutas estándar
if [ -z "$PSQL_CMD" ]; then
    if command -v psql &> /dev/null; then
        PSQL_CMD="psql"
        PG_ISREADY_CMD="pg_isready"
    elif [ -f "/opt/homebrew/bin/psql" ]; then
        PSQL_CMD="/opt/homebrew/bin/psql"
        PG_ISREADY_CMD="/opt/homebrew/bin/pg_isready"
        export PATH="/opt/homebrew/bin:$PATH"
    elif [ -f "/usr/local/bin/psql" ]; then
        PSQL_CMD="/usr/local/bin/psql"
        PG_ISREADY_CMD="/usr/local/bin/pg_isready"
        export PATH="/usr/local/bin:$PATH"
    else
        echo -e "${RED}ERROR: PostgreSQL no está instalado o no está en PATH${NC}"
        echo ""
        echo "Por favor, instala PostgreSQL:"
        echo "  macOS: brew install postgresql@15"
        echo ""
        echo "O agrega PostgreSQL al PATH manualmente."
        exit 1
    fi
fi

echo -e "${GREEN}✓ PostgreSQL detectado${NC}"
echo ""

# Verificar que PostgreSQL esté corriendo
if [ -n "$PG_ISREADY_CMD" ] && ! $PG_ISREADY_CMD -q 2>/dev/null; then
    echo -e "${YELLOW}⚠ PostgreSQL no está corriendo${NC}"
    echo ""
    echo "Iniciando PostgreSQL..."
    
    # Intentar iniciar PostgreSQL (diferentes comandos según el sistema)
    if command -v brew &> /dev/null; then
        # macOS con Homebrew
        brew services start postgresql@15 || brew services start postgresql
    elif command -v systemctl &> /dev/null; then
        # Linux con systemd
        sudo systemctl start postgresql
    else
        echo "Por favor, inicia PostgreSQL manualmente y vuelve a ejecutar este script"
        exit 1
    fi
    
    sleep 2
    
    sleep 2
    if [ -n "$PG_ISREADY_CMD" ] && ! $PG_ISREADY_CMD -q 2>/dev/null; then
        echo -e "${YELLOW}⚠ PostgreSQL puede no estar listo todavía${NC}"
        echo "Continuando de todas formas..."
    fi
elif [ -z "$PG_ISREADY_CMD" ]; then
    echo -e "${YELLOW}⚠ No se pudo verificar si PostgreSQL está corriendo (pg_isready no encontrado)${NC}"
    echo "Continuando de todas formas..."
fi

echo -e "${GREEN}✓ PostgreSQL está disponible${NC}"
echo ""

# Valores por defecto (se pueden sobrescribir con variables de entorno)
DB_NAME="${STAGING_DB_NAME:-bonito_amor_staging}"
DB_USER="${STAGING_DB_USER:-postgres}"
DB_PASSWORD="${STAGING_DB_PASSWORD:-postgres}"
DB_HOST="${STAGING_DB_HOST:-localhost}"
DB_PORT="${STAGING_DB_PORT:-5432}"

echo "Configuración de la base de datos:"
echo "  Nombre: $DB_NAME"
echo "  Usuario: $DB_USER"
echo "  Host: $DB_HOST"
echo "  Puerto: $DB_PORT"
echo ""

# Crear archivo .env.staging si no existe
if [ ! -f ".env.staging" ]; then
    echo "Creando archivo .env.staging desde la plantilla..."
    
    if [ -f "env.staging.template" ]; then
        cp env.staging.template .env.staging
        
        # Actualizar los valores en el archivo
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/STAGING_DB_NAME=.*/STAGING_DB_NAME=$DB_NAME/" .env.staging
            sed -i '' "s/STAGING_DB_USER=.*/STAGING_DB_USER=$DB_USER/" .env.staging
            sed -i '' "s/STAGING_DB_PASSWORD=.*/STAGING_DB_PASSWORD=$DB_PASSWORD/" .env.staging
            sed -i '' "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME|" .env.staging
        else
            # Linux
            sed -i "s/STAGING_DB_NAME=.*/STAGING_DB_NAME=$DB_NAME/" .env.staging
            sed -i "s/STAGING_DB_USER=.*/STAGING_DB_USER=$DB_USER/" .env.staging
            sed -i "s/STAGING_DB_PASSWORD=.*/STAGING_DB_PASSWORD=$DB_PASSWORD/" .env.staging
            sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME|" .env.staging
        fi
        
        echo -e "${GREEN}✓ Archivo .env.staging creado${NC}"
    else
        echo -e "${YELLOW}⚠ Plantilla .env.staging.example no encontrada, creando archivo básico...${NC}"
        cat > .env.staging << EOF
DJANGO_ENVIRONMENT=staging
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=staging-secret-key-$(openssl rand -hex 32)

DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME
EOF
        echo -e "${GREEN}✓ Archivo .env.staging creado${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}⚠ Archivo .env.staging ya existe, no se modificará${NC}"
    echo ""
fi

# Crear la base de datos si no existe
echo "Creando base de datos '$DB_NAME' si no existe..."
$PSQL_CMD -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
$PSQL_CMD -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Base de datos '$DB_NAME' lista${NC}"
else
    echo -e "${RED}ERROR: No se pudo crear la base de datos${NC}"
    echo "Verifica que el usuario '$DB_USER' tenga permisos para crear bases de datos"
    exit 1
fi

echo ""
echo "========================================="
echo -e "${GREEN}Setup completado exitosamente${NC}"
echo "========================================="
echo ""
echo "Siguientes pasos:"
echo ""
echo "1. Si tienes un dump de producción, restáuralo:"
echo "   ./scripts/restore_to_staging.sh backups/production_dump_YYYYMMDD_HHMMSS.sql.gz"
echo ""
echo "2. O aplica las migraciones para crear las tablas desde cero:"
echo "   DJANGO_ENVIRONMENT=staging python manage.py migrate"
echo ""
echo "3. Crea un superusuario (si es necesario):"
echo "   DJANGO_ENVIRONMENT=staging python manage.py createsuperuser"
echo ""
echo "4. Ejecuta el servidor en modo staging:"
echo "   DJANGO_ENVIRONMENT=staging python manage.py runserver"
echo ""
echo "5. Para hacer dump de producción:"
echo "   PRODUCTION_DATABASE_URL='tu-url-produccion' ./scripts/dump_production_db.sh"
echo ""

