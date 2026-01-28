-- Script SQL para corregir los valores por defecto de los campos de ML en la base de datos
-- Ejecutar este script en DBeaver conectado a la base de datos de producción/staging

-- Paso 1: Actualizar todos los registros existentes que tengan NULL
UPDATE inventario_tienda 
SET plataforma_ecommerce = 'NINGUNA' 
WHERE plataforma_ecommerce IS NULL;

UPDATE inventario_tienda 
SET ml_modo_test = TRUE 
WHERE ml_modo_test IS NULL;

UPDATE inventario_tienda 
SET ml_sync_habilitado = FALSE 
WHERE ml_sync_habilitado IS NULL;

UPDATE inventario_tienda 
SET ml_sincronizar_stock = TRUE 
WHERE ml_sincronizar_stock IS NULL;

UPDATE inventario_tienda 
SET ml_sincronizar_precios = TRUE 
WHERE ml_sincronizar_precios IS NULL;

UPDATE inventario_tienda 
SET ml_sincronizar_productos = TRUE 
WHERE ml_sincronizar_productos IS NULL;

-- Paso 2: Establecer los valores por defecto en las columnas para futuros registros
ALTER TABLE inventario_tienda 
ALTER COLUMN plataforma_ecommerce SET DEFAULT 'NINGUNA';

ALTER TABLE inventario_tienda 
ALTER COLUMN ml_modo_test SET DEFAULT TRUE;

ALTER TABLE inventario_tienda 
ALTER COLUMN ml_sync_habilitado SET DEFAULT FALSE;

ALTER TABLE inventario_tienda 
ALTER COLUMN ml_sincronizar_stock SET DEFAULT TRUE;

ALTER TABLE inventario_tienda 
ALTER COLUMN ml_sincronizar_precios SET DEFAULT TRUE;

ALTER TABLE inventario_tienda 
ALTER COLUMN ml_sincronizar_productos SET DEFAULT TRUE;

-- Verificar que las columnas ahora tienen los valores por defecto
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'inventario_tienda' 
AND column_name IN ('plataforma_ecommerce', 'ml_modo_test', 'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios', 'ml_sincronizar_productos')
ORDER BY column_name;
