#!/bin/bash

# Script para solucionar el problema de migración 0010 en Render
# Este script verifica qué campos existen y solo agrega los faltantes

set -e

echo "🔍 Verificando estado actual de la base de datos..."

cd /opt/render/project/src/backend || cd /app

python manage.py shell << 'EOF'
from django.db import connection

cursor = connection.cursor()

# Verificar campos de tienda
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda'
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip', 
                       'clave_privada_afip', 'modo_test_afip', 'api_key_arca', 'url_arca')
    ORDER BY column_name;
""")
campos_tienda = {row[0] for row in cursor.fetchall()}
print(f"✅ Campos de tienda existentes: {sorted(campos_tienda)}")

campos_tienda_necesarios = {'cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip',
                            'clave_privada_afip', 'modo_test_afip', 'api_key_arca', 'url_arca'}
faltantes_tienda = campos_tienda_necesarios - campos_tienda

if faltantes_tienda:
    print(f"⚠️ Campos de tienda faltantes: {sorted(faltantes_tienda)}")
else:
    print("✅ Todos los campos de tienda están presentes")

# Verificar campos de venta
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_venta'
    AND column_name IN ('cliente_cuit', 'cliente_domicilio', 'cliente_nombre', 
                       'cliente_tipo_documento', 'facturada', 'recargo_monto', 'recargo_porcentaje')
    ORDER BY column_name;
""")
campos_venta = {row[0] for row in cursor.fetchall()}
print(f"✅ Campos de venta existentes: {sorted(campos_venta)}")

campos_venta_necesarios = {'cliente_cuit', 'cliente_domicilio', 'cliente_nombre',
                          'cliente_tipo_documento', 'facturada', 'recargo_monto', 'recargo_porcentaje'}
faltantes_venta = campos_venta_necesarios - campos_venta

if faltantes_venta:
    print(f"⚠️ Campos de venta faltantes: {sorted(faltantes_venta)}")
else:
    print("✅ Todos los campos de venta están presentes")

# Verificar tabla factura
cursor.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'inventario_factura'
    );
""")
existe_factura = cursor.fetchone()[0]
print(f"✅ Tabla inventario_factura: {'EXISTE' if existe_factura else 'NO EXISTE'}")

# Crear tabla inventario_factura si no existe
if not existe_factura:
    print("\n🔧 Creando tabla inventario_factura...")
    cursor.execute("""
        CREATE TABLE inventario_factura (
            id UUID NOT NULL PRIMARY KEY,
            venta_id UUID NOT NULL UNIQUE,
            tienda_id UUID NOT NULL,
            numero_comprobante INTEGER NULL,
            punto_venta INTEGER NOT NULL,
            tipo_comprobante VARCHAR(1) NOT NULL DEFAULT 'B',
            cliente_nombre VARCHAR(255) NOT NULL,
            cliente_cuit VARCHAR(13) NULL,
            cliente_domicilio VARCHAR(255) NULL,
            cliente_tipo_documento VARCHAR(20) NULL,
            cliente_condicion_iva VARCHAR(2) NOT NULL DEFAULT 'CF',
            subtotal NUMERIC(10,2) NOT NULL,
            impuesto_iva NUMERIC(10,2) NOT NULL DEFAULT 0.00,
            total NUMERIC(10,2) NOT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
            sistema_facturacion VARCHAR(10) NOT NULL,
            cae VARCHAR(14) NULL,
            fecha_vencimiento_cae DATE NULL,
            numero_comprobante_afip BIGINT NULL,
            respuesta_bruta TEXT NULL,
            error_mensaje TEXT NULL,
            pdf_factura VARCHAR(100) NULL,
            fecha_emision TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_factura_venta FOREIGN KEY (venta_id) 
                REFERENCES inventario_venta(id) ON DELETE CASCADE,
            CONSTRAINT fk_factura_tienda FOREIGN KEY (tienda_id) 
                REFERENCES inventario_tienda(id) ON DELETE CASCADE
        );
    """)
    
    # Crear índices
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS inventario__tienda__160d7b_idx 
        ON inventario_factura(tienda_id, numero_comprobante, punto_venta);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS inventario__cae_7a2e2a_idx 
        ON inventario_factura(cae);
    """)
    print("  ✅ Tabla inventario_factura creada")

# Agregar campos faltantes de tienda
if faltantes_tienda:
    print("\n🔧 Agregando campos faltantes en inventario_tienda...")
    if 'cuit' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN cuit VARCHAR(13) NULL;")
        print("  ✅ Agregado: cuit")
    if 'punto_venta' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN punto_venta INTEGER NOT NULL DEFAULT 1;")
        print("  ✅ Agregado: punto_venta")
    if 'tipo_facturacion' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN tipo_facturacion VARCHAR(10) NOT NULL DEFAULT 'NINGUNA';")
        print("  ✅ Agregado: tipo_facturacion")
    if 'certificado_afip' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN certificado_afip TEXT NULL;")
        print("  ✅ Agregado: certificado_afip")
    if 'clave_privada_afip' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN clave_privada_afip TEXT NULL;")
        print("  ✅ Agregado: clave_privada_afip")
    if 'modo_test_afip' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN modo_test_afip BOOLEAN NOT NULL DEFAULT TRUE;")
        print("  ✅ Agregado: modo_test_afip")
    if 'api_key_arca' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN api_key_arca VARCHAR(255) NULL;")
        print("  ✅ Agregado: api_key_arca")
    if 'url_arca' in faltantes_tienda:
        cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN url_arca VARCHAR(200) NULL;")
        print("  ✅ Agregado: url_arca")

# Agregar campos faltantes de venta
if faltantes_venta:
    print("\n🔧 Agregando campos faltantes en inventario_venta...")
    if 'cliente_cuit' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_cuit VARCHAR(13) NULL;")
        print("  ✅ Agregado: cliente_cuit")
    if 'cliente_domicilio' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_domicilio VARCHAR(255) NULL;")
        print("  ✅ Agregado: cliente_domicilio")
    if 'cliente_nombre' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_nombre VARCHAR(255) NULL;")
        print("  ✅ Agregado: cliente_nombre")
    if 'cliente_tipo_documento' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_tipo_documento VARCHAR(20) NULL;")
        print("  ✅ Agregado: cliente_tipo_documento")
    if 'facturada' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN facturada BOOLEAN NOT NULL DEFAULT FALSE;")
        print("  ✅ Agregado: facturada")
    if 'recargo_monto' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN recargo_monto NUMERIC(10,2) NOT NULL DEFAULT 0.00;")
        print("  ✅ Agregado: recargo_monto")
    if 'recargo_porcentaje' in faltantes_venta:
        cursor.execute("ALTER TABLE inventario_venta ADD COLUMN recargo_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0.00;")
        print("  ✅ Agregado: recargo_porcentaje")

print("\n✅ Verificación completada")
EOF

echo ""
echo "🔄 Intentando aplicar migraciones ahora..."
python manage.py migrate inventario 0010 --fake

echo ""
echo "🔄 Aplicando migración 0011 (fix de campos faltantes)..."
python manage.py migrate inventario

echo ""
echo "✅ Verificando estado final..."
python manage.py showmigrations inventario | tail -5

echo ""
echo "🎉 Proceso completado!"

