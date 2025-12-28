#!/bin/bash

# Script rápido para crear la tabla inventario_factura si no existe

set -e

echo "🔍 Verificando si existe la tabla inventario_factura..."

cd /opt/render/project/src/backend || cd /app

python manage.py shell << 'EOF'
from django.db import connection

cursor = connection.cursor()

# Verificar si existe
cursor.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'inventario_factura'
    );
""")
existe = cursor.fetchone()[0]

if existe:
    print("✅ La tabla inventario_factura YA EXISTE")
else:
    print("⚠️ La tabla NO EXISTE. Creándola...")
    
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
    
    print("✅ Tabla inventario_factura creada exitosamente")
    
    # Verificar
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'inventario_factura'
        );
    """)
    verificacion = cursor.fetchone()[0]
    
    if verificacion:
        print("✅ Verificación: Tabla creada correctamente")
    else:
        print("❌ Error: La tabla no se creó correctamente")
EOF

echo ""
echo "✅ Proceso completado"

