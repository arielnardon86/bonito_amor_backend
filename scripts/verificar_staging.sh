#!/bin/bash

# Script para verificar y corregir la configuración de staging

set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Agregar PostgreSQL al PATH
export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"

echo "========================================="
echo "Verificación de Ambiente Staging"
echo "========================================="
echo ""

# Verificar que PostgreSQL esté corriendo
echo "1. Verificando PostgreSQL..."
if pg_isready -q 2>/dev/null; then
    echo -e "${GREEN}✓ PostgreSQL está corriendo${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL no está corriendo, intentando iniciar...${NC}"
    brew services start postgresql@15 2>/dev/null || brew services start postgresql
    sleep 2
    if pg_isready -q 2>/dev/null; then
        echo -e "${GREEN}✓ PostgreSQL iniciado${NC}"
    else
        echo -e "${RED}✗ No se pudo iniciar PostgreSQL${NC}"
        exit 1
    fi
fi
echo ""

# Determinar el usuario de PostgreSQL
echo "2. Verificando usuario de PostgreSQL..."
DB_USER=$(whoami)
echo "Usuario del sistema: $DB_USER"
echo "Intentando conectar como usuario: $DB_USER"
echo ""

# Verificar si puede crear bases de datos
echo "3. Verificando permisos..."
if psql -U "$DB_USER" -d postgres -tc "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Puede conectar a PostgreSQL como $DB_USER${NC}"
    CAN_CONNECT=true
else
    echo -e "${YELLOW}⚠ No puede conectar como $DB_USER, intentando crear usuario...${NC}"
    CAN_CONNECT=false
    
    # Intentar crear el usuario si no existe
    if psql -U "$DB_USER" -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        echo "Usuario $DB_USER ya existe"
    else
        echo "Creando usuario $DB_USER..."
        createuser -s "$DB_USER" 2>/dev/null || echo "No se pudo crear usuario automáticamente"
    fi
fi
echo ""

# Verificar o crear la base de datos
echo "4. Verificando base de datos 'bonito_amor_staging'..."
DB_NAME="bonito_amor_staging"

if psql -U "$DB_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 2>/dev/null; then
    echo -e "${GREEN}✓ Base de datos '$DB_NAME' existe${NC}"
else
    echo "Creando base de datos '$DB_NAME'..."
    if psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null; then
        echo -e "${GREEN}✓ Base de datos '$DB_NAME' creada${NC}"
    else
        echo -e "${RED}✗ No se pudo crear la base de datos${NC}"
        exit 1
    fi
fi
echo ""

# Verificar y actualizar .env.staging
echo "5. Verificando archivo .env.staging..."
if [ -f ".env.staging" ]; then
    echo -e "${GREEN}✓ Archivo .env.staging existe${NC}"
    
    # Actualizar DATABASE_URL con el usuario correcto
    DB_URL="postgresql://$DB_USER@localhost:5432/$DB_NAME"
    
    # Actualizar el archivo
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|DATABASE_URL=.*|DATABASE_URL=$DB_URL|" .env.staging
        sed -i '' "s|STAGING_DB_USER=.*|STAGING_DB_USER=$DB_USER|" .env.staging
    else
        # Linux
        sed -i "s|DATABASE_URL=.*|DATABASE_URL=$DB_URL|" .env.staging
        sed -i "s|STAGING_DB_USER=.*|STAGING_DB_USER=$DB_USER|" .env.staging
    fi
    
    echo "DATABASE_URL actualizado a: $DB_URL"
else
    echo -e "${YELLOW}⚠ Archivo .env.staging no existe${NC}"
    echo "Ejecuta: ./scripts/setup_staging.sh primero"
fi
echo ""

echo "========================================="
echo -e "${GREEN}Verificación completada${NC}"
echo "========================================="
echo ""
echo "Próximos pasos:"
echo "  1. Ejecutar migraciones:"
echo "     DJANGO_ENVIRONMENT=staging python manage.py migrate"
echo ""
echo "  2. Iniciar servidor:"
echo "     ./scripts/run_staging.sh runserver"
echo ""





