#!/bin/bash

# Script para verificar que todo esté listo antes de desplegar a producción

echo "🔍 Verificando estado del proyecto para deployment..."

# Colores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# 1. Verificar que estamos en el directorio correcto
if [ ! -f "manage.py" ]; then
    echo -e "${RED}❌ Error: No se encontró manage.py. Ejecuta este script desde el directorio backend/${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Directorio correcto${NC}"

# 2. Verificar que requirements.txt tenga todas las dependencias
echo ""
echo "📦 Verificando dependencias en requirements.txt..."
REQUIRED_DEPS=("pyafipws" "reportlab" "setuptools" "requests" "cryptography")
MISSING_DEPS=()

for dep in "${REQUIRED_DEPS[@]}"; do
    if ! grep -q "$dep" requirements.txt; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${RED}❌ Faltan dependencias en requirements.txt: ${MISSING_DEPS[*]}${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ Todas las dependencias están en requirements.txt${NC}"
fi

# 3. Verificar que existan las migraciones
echo ""
echo "📋 Verificando migraciones..."
if [ ! -f "inventario/migrations/0010_tienda_api_key_arca_tienda_certificado_afip_and_more.py" ]; then
    echo -e "${RED}❌ Error: No se encontró la migración 0010${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ Migración 0010 encontrada${NC}"
fi

# 4. Verificar que existan los archivos nuevos
echo ""
echo "📁 Verificando archivos nuevos..."
NEW_FILES=(
    "inventario/services/facturacion_service.py"
    "inventario/services/__init__.py"
    "inventario/management/commands/convertir_certificados_afip.py"
    "FACTURACION_ELECTRONICA.md"
    "CONFIGURAR_FACTURACION.md"
    "DEPLOY_PRODUCCION.md"
)

MISSING_FILES=()
for file in "${NEW_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Archivos faltantes: ${MISSING_FILES[*]}${NC}"
    echo -e "${YELLOW}   (Algunos pueden ser opcionales)${NC}"
else
    echo -e "${GREEN}✅ Todos los archivos nuevos existen${NC}"
fi

# 5. Verificar estado de git
echo ""
echo "🔀 Verificando estado de Git..."
if command -v git &> /dev/null; then
    cd ..
    if [ -d ".git" ]; then
        UNCOMMITTED=$(git status --porcelain)
        if [ -n "$UNCOMMITTED" ]; then
            echo -e "${YELLOW}⚠️  Hay cambios sin commitear:${NC}"
            echo "$UNCOMMITTED" | head -10
            echo ""
            echo -e "${YELLOW}   Considera hacer commit antes de desplegar${NC}"
        else
            echo -e "${GREEN}✅ No hay cambios sin commitear${NC}"
        fi
        
        UNTRACKED=$(git ls-files --others --exclude-standard)
        if [ -n "$UNTRACKED" ]; then
            echo -e "${YELLOW}⚠️  Hay archivos sin trackear:${NC}"
            echo "$UNTRACKED" | head -10
        fi
    else
        echo -e "${YELLOW}⚠️  No es un repositorio Git${NC}"
    fi
    cd backend
else
    echo -e "${YELLOW}⚠️  Git no está instalado${NC}"
fi

# 6. Resumen
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ Verificación completada. Todo parece estar listo para deployment.${NC}"
    echo ""
    echo "📝 Próximos pasos:"
    echo "   1. Revisa DEPLOY_PRODUCCION.md para instrucciones detalladas"
    echo "   2. Haz commit de todos los cambios: git add . && git commit -m 'mensaje'"
    echo "   3. Sube a Git: git push origin main"
    echo "   4. Despliega en producción siguiendo DEPLOY_PRODUCCION.md"
    exit 0
else
    echo -e "${RED}❌ Se encontraron $ERRORS error(es). Corrígelos antes de desplegar.${NC}"
    exit 1
fi

