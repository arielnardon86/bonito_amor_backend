# 🔧 Solución: Error "column inventario_tienda.cuit does not exist"

## ❌ Error

```
django.db.utils.ProgrammingError: column inventario_tienda.cuit does not exist
```

## 🔍 Causa

Las migraciones no se aplicaron en producción. El código intenta acceder a campos (`cuit`, `punto_venta`, `tipo_facturacion`, etc.) que no existen en la base de datos.

## ✅ Soluciones

### Solución 1: Aplicar Migraciones (RECOMENDADO)

En el **Shell de Render**, ejecuta:

```bash
cd /opt/render/project/src/backend
python manage.py migrate inventario
```

O usa el script automatizado:

```bash
bash scripts/aplicar_migraciones_render.sh
```

### Solución 2: Usar SQL Directo (Si las migraciones fallan)

Si por alguna razón las migraciones fallan, puedes ejecutar el SQL directamente:

1. **En el Shell de Render**, conectarte a PostgreSQL:

```bash
# Obtener la URL de conexión
echo $DATABASE_URL

# Conectarte (si tienes psql instalado)
psql $DATABASE_URL
```

2. **Dentro de psql**, ejecutar:

```sql
-- Copiar y pegar el contenido completo de scripts/migracion_0010.sql
-- O ejecutar las siguientes líneas críticas:

ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS cuit VARCHAR(13) NULL;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS punto_venta INTEGER NOT NULL DEFAULT 1;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS tipo_facturacion VARCHAR(10) NOT NULL DEFAULT 'NINGUNA';
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS modo_test_afip BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS certificado_afip TEXT NULL;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS clave_privada_afip TEXT NULL;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS api_key_arca VARCHAR(255) NULL;
ALTER TABLE inventario_tienda ADD COLUMN IF NOT EXISTS url_arca VARCHAR(200) NULL;

ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS facturada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS cliente_nombre VARCHAR(255) NULL;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS cliente_cuit VARCHAR(13) NULL;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS cliente_domicilio VARCHAR(255) NULL;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS cliente_tipo_documento VARCHAR(20) NULL;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS recargo_porcentaje NUMERIC(5,2) NOT NULL DEFAULT 0.00;
ALTER TABLE inventario_venta ADD COLUMN IF NOT EXISTS recargo_monto NUMERIC(10,2) NOT NULL DEFAULT 0.00;

-- Luego crear la tabla inventario_factura (ver scripts/migracion_0010.sql para el SQL completo)
```

3. **Después de ejecutar el SQL**, marca la migración como aplicada:

```bash
python manage.py migrate inventario 0010 --fake
```

### Solución 3: Parche Temporal del Serializer (Ya aplicado)

Se modificó `TiendaSerializer` para manejar campos que pueden no existir. Esto permite que la aplicación funcione mientras se aplican las migraciones, pero **NO es una solución permanente**.

## 🔄 Verificación

Después de aplicar las migraciones, verifica:

```bash
python manage.py shell
```

```python
from inventario.models import Tienda, Factura

# Verificar campos
tienda = Tienda.objects.first()
if tienda:
    print("✅ Campos disponibles:")
    print(f"  - cuit: {hasattr(tienda, 'cuit')}")
    print(f"  - punto_venta: {hasattr(tienda, 'punto_venta')}")
    print(f"  - tipo_facturacion: {hasattr(tienda, 'tipo_facturacion')}")

# Verificar tabla
try:
    facturas = Factura.objects.count()
    print(f"✅ Tabla Factura existe. Total: {facturas}")
except:
    print("❌ Tabla Factura NO existe")
```

## ⚠️ IMPORTANTE

1. **Aplica las migraciones PRIMERO** antes de usar la aplicación
2. El parche del serializer es temporal - las migraciones son necesarias
3. Reinicia el servicio en Render después de aplicar migraciones

## 📝 Comandos Rápidos para Render Shell

```bash
# Todo en uno:
cd /opt/render/project/src/backend && \
python manage.py migrate inventario && \
python manage.py showmigrations inventario | tail -5
```



