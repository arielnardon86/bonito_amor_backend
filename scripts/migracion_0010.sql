-- ============================================================================
-- SCRIPT SQL PARA MIGRACIÓN 0010 - SISTEMA DE FACTURACIÓN ELECTRÓNICA
-- ============================================================================
-- Este script agrega:
-- 1. Nueva tabla: inventario_factura
-- 2. Nuevos campos en inventario_tienda
-- 3. Nuevos campos en inventario_venta
-- ============================================================================
-- IMPORTANTE: Ejecuta este script SOLO si no puedes usar "python manage.py migrate"
-- Si puedes usar Django migrations, es preferible usar: python manage.py migrate inventario 0010
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. AGREGAR CAMPOS A inventario_tienda
-- ============================================================================

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS cuit VARCHAR(13) NULL;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS punto_venta INTEGER NOT NULL DEFAULT 1;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS tipo_facturacion VARCHAR(10) NOT NULL DEFAULT 'NINGUNA' 
CHECK (tipo_facturacion IN ('AFIP', 'ARCA', 'NINGUNA'));

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS modo_test_afip BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS certificado_afip TEXT NULL;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS clave_privada_afip TEXT NULL;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS api_key_arca VARCHAR(255) NULL;

ALTER TABLE inventario_tienda 
ADD COLUMN IF NOT EXISTS url_arca VARCHAR(200) NULL;

-- ============================================================================
-- 2. AGREGAR CAMPOS A inventario_venta
-- ============================================================================

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS facturada BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS cliente_nombre VARCHAR(255) NULL;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS cliente_cuit VARCHAR(13) NULL;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS cliente_domicilio VARCHAR(255) NULL;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS cliente_tipo_documento VARCHAR(20) NULL;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS recargo_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0.00;

ALTER TABLE inventario_venta 
ADD COLUMN IF NOT EXISTS recargo_monto NUMERIC(10,2) NOT NULL DEFAULT 0.00;

-- ============================================================================
-- 3. CREAR TABLA inventario_factura
-- ============================================================================

CREATE TABLE IF NOT EXISTS inventario_factura (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venta_id UUID NOT NULL UNIQUE,
    tienda_id UUID NOT NULL,
    numero_comprobante INTEGER NULL,
    punto_venta INTEGER NOT NULL,
    tipo_comprobante VARCHAR(1) NOT NULL DEFAULT 'B' 
        CHECK (tipo_comprobante IN ('A', 'B', 'C')),
    cliente_nombre VARCHAR(255) NOT NULL,
    cliente_cuit VARCHAR(13) NULL,
    cliente_domicilio VARCHAR(255) NULL,
    cliente_tipo_documento VARCHAR(20) NULL,
    cliente_condicion_iva VARCHAR(2) NOT NULL DEFAULT 'CF'
        CHECK (cliente_condicion_iva IN ('RI', 'CF', 'EX', 'MT', 'NR')),
    subtotal NUMERIC(10,2) NOT NULL,
    impuesto_iva NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    total NUMERIC(10,2) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE', 'EMITIDA', 'ANULADA', 'ERROR')),
    sistema_facturacion VARCHAR(10) NOT NULL
        CHECK (sistema_facturacion IN ('AFIP', 'ARCA', 'NINGUNA')),
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

-- ============================================================================
-- 4. CREAR ÍNDICES PARA OPTIMIZACIÓN
-- ============================================================================

CREATE INDEX IF NOT EXISTS inventario__tienda__160d7b_idx 
ON inventario_factura(tienda_id, numero_comprobante, punto_venta);

CREATE INDEX IF NOT EXISTS inventario__cae_7a2e2a_idx 
ON inventario_factura(cae);

-- ============================================================================
-- 5. AGREGAR COMENTARIOS A LAS COLUMNAS (opcional, pero útil)
-- ============================================================================

COMMENT ON COLUMN inventario_tienda.cuit IS 'CUIT de la tienda (formato: XX-XXXXXXXX-X)';
COMMENT ON COLUMN inventario_tienda.punto_venta IS 'Punto de venta AFIP/ARCA';
COMMENT ON COLUMN inventario_tienda.tipo_facturacion IS 'Sistema de facturación a utilizar';
COMMENT ON COLUMN inventario_tienda.modo_test_afip IS 'Usar modo testing/homologación de AFIP';
COMMENT ON COLUMN inventario_tienda.certificado_afip IS 'Certificado digital AFIP (.crt) codificado en base64';
COMMENT ON COLUMN inventario_tienda.clave_privada_afip IS 'Clave privada AFIP (.key) codificado en base64';

COMMENT ON COLUMN inventario_venta.facturada IS 'Indica si esta venta ha sido facturada';
COMMENT ON COLUMN inventario_venta.cliente_nombre IS 'Nombre o razón social del cliente';
COMMENT ON COLUMN inventario_venta.cliente_cuit IS 'CUIT del cliente';
COMMENT ON COLUMN inventario_venta.recargo_porcentaje IS 'Porcentaje de recargo aplicado a la venta total.';
COMMENT ON COLUMN inventario_venta.recargo_monto IS 'Monto de recargo aplicado a la venta total.';

COMMENT ON COLUMN inventario_factura.cae IS 'CAE (Código de Autorización Electrónica) de AFIP';
COMMENT ON COLUMN inventario_factura.fecha_vencimiento_cae IS 'Fecha de vencimiento del CAE';
COMMENT ON COLUMN inventario_factura.numero_comprobante_afip IS 'Número de comprobante retornado por AFIP';
COMMENT ON COLUMN inventario_factura.respuesta_bruta IS 'Respuesta completa del servicio de facturación (JSON)';
COMMENT ON COLUMN inventario_factura.error_mensaje IS 'Mensaje de error si la facturación falló';

COMMIT;

-- ============================================================================
-- VERIFICACIÓN POST-MIGRACIÓN
-- ============================================================================

-- Verificar que la tabla existe
SELECT 'Tabla inventario_factura creada correctamente' AS status
WHERE EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'inventario_factura'
);

-- Verificar campos en inventario_tienda
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'inventario_tienda' 
AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip');

-- Verificar campos en inventario_venta
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'inventario_venta' 
AND column_name IN ('facturada', 'cliente_nombre', 'cliente_cuit', 'recargo_porcentaje', 'recargo_monto');



