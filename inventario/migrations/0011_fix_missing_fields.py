# Generated manually to fix partial migration 0010
# This migration checks if fields exist before adding them

from django.db import migrations, models
import django.db.models.deletion
import uuid
from decimal import Decimal


def check_and_add_fields(apps, schema_editor):
    """
    Verifica qué campos existen y solo agrega los faltantes.
    """
    db_alias = schema_editor.connection.alias
    
    # Verificar campos en inventario_tienda
    with schema_editor.connection.cursor() as cursor:
        # Verificar campos de tienda
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'inventario_tienda'
            AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip', 
                               'clave_privada_afip', 'modo_test_afip', 'api_key_arca', 'url_arca');
        """)
        campos_tienda_existentes = {row[0] for row in cursor.fetchall()}
        
        # Verificar campos de venta
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'inventario_venta'
            AND column_name IN ('cliente_cuit', 'cliente_domicilio', 'cliente_nombre', 
                               'cliente_tipo_documento', 'facturada', 'recargo_monto', 'recargo_porcentaje');
        """)
        campos_venta_existentes = {row[0] for row in cursor.fetchall()}
        
        # Verificar si existe la tabla inventario_factura
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'inventario_factura'
            );
        """)
        tabla_factura_existe = cursor.fetchone()[0]
        
        print(f"📋 Campos de tienda existentes: {campos_tienda_existentes}")
        print(f"📋 Campos de venta existentes: {campos_venta_existentes}")
        print(f"📋 Tabla factura existe: {tabla_factura_existe}")
        
        # Crear tabla inventario_factura si no existe
        if not tabla_factura_existe:
            print("⚠️ Creando tabla inventario_factura...")
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
            print("✅ Tabla inventario_factura creada")
        else:
            print("✅ Tabla inventario_factura ya existe")
        
        # Agregar campos de tienda faltantes
        campos_tienda_faltantes = {
            'cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip',
            'clave_privada_afip', 'modo_test_afip', 'api_key_arca', 'url_arca'
        } - campos_tienda_existentes
        
        if campos_tienda_faltantes:
            print(f"⚠️ Agregando campos faltantes en tienda: {campos_tienda_faltantes}")
            if 'cuit' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN cuit VARCHAR(13) NULL;")
            if 'punto_venta' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN punto_venta INTEGER NOT NULL DEFAULT 1;")
            if 'tipo_facturacion' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN tipo_facturacion VARCHAR(10) NOT NULL DEFAULT 'NINGUNA';")
            if 'certificado_afip' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN certificado_afip TEXT NULL;")
            if 'clave_privada_afip' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN clave_privada_afip TEXT NULL;")
            if 'modo_test_afip' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN modo_test_afip BOOLEAN NOT NULL DEFAULT TRUE;")
            if 'api_key_arca' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN api_key_arca VARCHAR(255) NULL;")
            if 'url_arca' in campos_tienda_faltantes:
                cursor.execute("ALTER TABLE inventario_tienda ADD COLUMN url_arca VARCHAR(200) NULL;")
        
        # Agregar campos de venta faltantes
        campos_venta_faltantes = {
            'cliente_cuit', 'cliente_domicilio', 'cliente_nombre',
            'cliente_tipo_documento', 'facturada', 'recargo_monto', 'recargo_porcentaje'
        } - campos_venta_existentes
        
        if campos_venta_faltantes:
            print(f"⚠️ Agregando campos faltantes en venta: {campos_venta_faltantes}")
            if 'cliente_cuit' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_cuit VARCHAR(13) NULL;")
            if 'cliente_domicilio' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_domicilio VARCHAR(255) NULL;")
            if 'cliente_nombre' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_nombre VARCHAR(255) NULL;")
            if 'cliente_tipo_documento' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN cliente_tipo_documento VARCHAR(20) NULL;")
            if 'facturada' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN facturada BOOLEAN NOT NULL DEFAULT FALSE;")
            if 'recargo_monto' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN recargo_monto NUMERIC(10,2) NOT NULL DEFAULT 0.00;")
            if 'recargo_porcentaje' in campos_venta_faltantes:
                cursor.execute("ALTER TABLE inventario_venta ADD COLUMN recargo_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0.00;")


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0010_tienda_api_key_arca_tienda_certificado_afip_and_more'),
    ]

    operations = [
        migrations.RunPython(check_and_add_fields, migrations.RunPython.noop),
    ]

