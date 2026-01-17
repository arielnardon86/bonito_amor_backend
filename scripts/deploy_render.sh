#!/bin/bash

# ============================================================================
# SCRIPT PARA DESPLEGAR EN RENDER.COM
# ============================================================================
# Este script ejecuta todos los pasos necesarios para desplegar
# los cambios de facturación electrónica en Render
# ============================================================================

set -e  # Salir si hay algún error

echo "🚀 Iniciando deployment en Render..."
echo ""

# Colores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# 1. VERIFICAR VARIABLES DE ENTORNO
# ============================================================================

echo -e "${BLUE}📋 Verificando variables de entorno...${NC}"

if [ -z "$DJANGO_ENVIRONMENT" ]; then
    export DJANGO_ENVIRONMENT="production"
    echo -e "${YELLOW}⚠️  DJANGO_ENVIRONMENT no estaba definido, usando 'production'${NC}"
fi

if [ "$DJANGO_ENVIRONMENT" != "production" ]; then
    echo -e "${RED}❌ Error: DJANGO_ENVIRONMENT debe ser 'production'${NC}"
    exit 1
fi

echo -e "${GREEN}✅ DJANGO_ENVIRONMENT=$DJANGO_ENVIRONMENT${NC}"

# ============================================================================
# 2. INSTALAR DEPENDENCIAS
# ============================================================================

echo ""
echo -e "${BLUE}📦 Instalando dependencias...${NC}"

if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Dependencias instaladas${NC}"
else
    echo -e "${RED}❌ Error: No se encontró requirements.txt${NC}"
    exit 1
fi

# ============================================================================
# 3. APLICAR MIGRACIONES
# ============================================================================

echo ""
echo -e "${BLUE}🗄️  Aplicando migraciones...${NC}"

# Verificar estado de migraciones
echo "Estado actual de migraciones:"
python manage.py showmigrations inventario | tail -5

# Aplicar migraciones
python manage.py migrate inventario

# Verificar que se aplicaron correctamente
echo ""
echo "Estado después de migraciones:"
python manage.py showmigrations inventario | tail -5

echo -e "${GREEN}✅ Migraciones aplicadas${NC}"

# ============================================================================
# 4. RECOLECTAR ARCHIVOS ESTÁTICOS
# ============================================================================

echo ""
echo -e "${BLUE}📁 Recolectando archivos estáticos...${NC}"

python manage.py collectstatic --noinput

echo -e "${GREEN}✅ Archivos estáticos recolectados${NC}"

# ============================================================================
# 5. VERIFICAR TABLAS Y CAMPOS
# ============================================================================

echo ""
echo -e "${BLUE}🔍 Verificando estructura de base de datos...${NC}"

python manage.py shell << 'EOF'
from django.db import connection
cursor = connection.cursor()

# Verificar tabla inventario_factura
cursor.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'inventario_factura'
    );
""")
exists = cursor.fetchone()[0]
if exists:
    print("✅ Tabla inventario_factura existe")
else:
    print("❌ ERROR: Tabla inventario_factura NO existe")

# Verificar campos en inventario_tienda
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda' 
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip');
""")
tienda_fields = [row[0] for row in cursor.fetchall()]
required_tienda = ['cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip']
if all(field in tienda_fields for field in required_tienda):
    print("✅ Campos de facturación en inventario_tienda existen")
else:
    missing = set(required_tienda) - set(tienda_fields)
    print(f"❌ ERROR: Faltan campos en inventario_tienda: {missing}")

# Verificar campos en inventario_venta
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_venta' 
    AND column_name IN ('facturada', 'cliente_nombre', 'cliente_cuit');
""")
venta_fields = [row[0] for row in cursor.fetchall()]
required_venta = ['facturada', 'cliente_nombre', 'cliente_cuit']
if all(field in venta_fields for field in required_venta):
    print("✅ Campos de facturación en inventario_venta existen")
else:
    missing = set(required_venta) - set(venta_fields)
    print(f"❌ ERROR: Faltan campos en inventario_venta: {missing}")
EOF

# ============================================================================
# 6. RESUMEN FINAL
# ============================================================================

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Deployment completado exitosamente${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Verificar que el servidor se haya reiniciado automáticamente"
echo "   2. Probar la aplicación en producción"
echo "   3. Configurar certificados AFIP de producción en Django Admin"
echo "   4. Desactivar 'Modo test AFIP' en producción"
echo ""
echo "📚 Documentación:"
echo "   - DEPLOY_PRODUCCION.md"
echo "   - CONFIGURAR_FACTURACION.md"
echo ""



