# 🔧 Solución: Error "column recargo_monto already exists"

## ❌ Error

```
django.db.utils.ProgrammingError: column "recargo_monto" of relation "inventario_venta" already exists
```

## 🔍 Causa

La migración `0010` intenta agregar campos que **ya existen parcialmente** en la base de datos de producción. Esto puede ocurrir si:

1. Se intentó aplicar la migración antes y falló a mitad de camino
2. Se agregaron algunos campos manualmente
3. Hubo una aplicación parcial de la migración

## ✅ Solución Rápida (Recomendada)

### Opción 1: Usar el Script Automatizado

En el **Shell de Render**, ejecuta:

```bash
cd /opt/render/project/src/backend
bash scripts/solucionar_migracion_0010_render.sh
```

Este script:
- ✅ Verifica qué campos existen
- ✅ Solo agrega los campos faltantes
- ✅ Marca la migración 0010 como aplicada (fake)
- ✅ Aplica la migración 0011 que corrige los campos faltantes

### Opción 2: Manual (Paso a Paso)

1. **Verificar qué campos faltan:**

```bash
cd /opt/render/project/src/backend
python manage.py shell
```

```python
from django.db import connection

cursor = connection.cursor()

# Verificar campos de tienda
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda'
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion');
""")
print("Campos de tienda:", [row[0] for row in cursor.fetchall()])

# Verificar campos de venta
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_venta'
    AND column_name IN ('recargo_monto', 'recargo_porcentaje', 'facturada');
""")
print("Campos de venta:", [row[0] for row in cursor.fetchall()])
```

2. **Marcar la migración 0010 como aplicada (fake):**

```bash
python manage.py migrate inventario 0010 --fake
```

Esto le dice a Django que "ya se aplicó" sin intentar ejecutarla.

3. **Aplicar la migración 0011 (corrección):**

```bash
python manage.py migrate inventario 0011
```

La migración 0011 verifica qué campos existen y solo agrega los faltantes.

4. **Verificar:**

```bash
python manage.py showmigrations inventario | tail -5
```

Debes ver:
```
[X] 0010_tienda_api_key_arca_tienda_certificado_afip_and_more
[X] 0011_fix_missing_fields
```

### Opción 3: SQL Directo (Si todo falla)

Si las opciones anteriores no funcionan, ejecuta SQL directamente:

```bash
python manage.py dbshell
```

O usando psql:

```sql
-- Verificar qué campos existen
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'inventario_tienda'
AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip');

-- Agregar solo los faltantes (ejemplo)
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS cuit VARCHAR(13) NULL;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS punto_venta INTEGER NOT NULL DEFAULT 1;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS tipo_facturacion VARCHAR(10) NOT NULL DEFAULT 'NINGUNA';
-- ... etc (ver script SQL completo en scripts/migracion_0010.sql)

-- Luego marcar como aplicada
-- (salir de dbshell y ejecutar)
python manage.py migrate inventario 0010 --fake
```

## 📝 Archivos Creados

1. **`inventario/migrations/0011_fix_missing_fields.py`**
   - Nueva migración que verifica y agrega solo campos faltantes

2. **`scripts/solucionar_migracion_0010_render.sh`**
   - Script automatizado para aplicar la solución

## ⚠️ IMPORTANTE

Después de aplicar la solución:

1. **Reinicia el servicio** en Render Dashboard
2. **Verifica que la aplicación funcione** correctamente
3. **Confirma que no hay errores** en los logs

## 🔄 Comandos Rápidos para Render Shell

```bash
# Todo en uno:
cd /opt/render/project/src/backend && \
bash scripts/solucionar_migracion_0010_render.sh
```

O si el script no está disponible:

```bash
cd /opt/render/project/src/backend && \
python manage.py migrate inventario 0010 --fake && \
python manage.py migrate inventario && \
python manage.py showmigrations inventario | tail -3
```



