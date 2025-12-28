#!/bin/bash

# Script para aplicar migraciones en Render desde el Shell
# Copia y pega estos comandos en el Shell de Render

set -e

echo "🚀 Aplicando migraciones en producción..."

cd /opt/render/project/src/backend

# Verificar estado actual
echo "📋 Estado de migraciones ANTES:"
python manage.py showmigrations inventario | tail -5

# Aplicar todas las migraciones pendientes
echo ""
echo "🔄 Aplicando migraciones..."
python manage.py migrate inventario

# Verificar estado después
echo ""
echo "📋 Estado de migraciones DESPUÉS:"
python manage.py showmigrations inventario | tail -5

# Verificar que las tablas existen
echo ""
echo "🔍 Verificando estructura de base de datos..."
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
existe = cursor.fetchone()[0]
print(f"✅ Tabla inventario_factura: {'EXISTE' if existe else 'NO EXISTE'}")

# Verificar campos en inventario_tienda
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda' 
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip')
    ORDER BY column_name;
""")
campos = [row[0] for row in cursor.fetchall()]
print(f"✅ Campos en inventario_tienda: {campos}")

if len(campos) == 4:
    print("✅ Todos los campos fiscales están presentes")
else:
    faltantes = set(['cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip']) - set(campos)
    print(f"❌ Faltan campos: {faltantes}")

# Verificar campos en inventario_venta
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_venta' 
    AND column_name IN ('facturada', 'cliente_nombre', 'cliente_cuit')
    ORDER BY column_name;
""")
campos_venta = [row[0] for row in cursor.fetchall()]
print(f"✅ Campos en inventario_venta: {campos_venta}")

if len(campos_venta) == 3:
    print("✅ Todos los campos de facturación en venta están presentes")
else:
    faltantes_venta = set(['facturada', 'cliente_nombre', 'cliente_cuit']) - set(campos_venta)
    print(f"❌ Faltan campos: {faltantes_venta}")
EOF

echo ""
echo "✅ Verificación completada"
echo ""
echo "🔄 Si faltaban migraciones, reinicia el servicio en Render Dashboard"
echo "   (Render generalmente reinicia automáticamente después de migraciones)"

