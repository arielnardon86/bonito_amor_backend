# 🚀 Comandos para Ejecutar en el Shell de Render

## ⚠️ IMPORTANTE

**En tu máquina local**, siempre activa el entorno virtual primero:
```bash
cd /Users/arinardon/Proyectos/Bonito_Amor/backend
source venv/bin/activate
```

**En Render**, el entorno virtual generalmente se activa automáticamente, pero si necesitas activarlo manualmente:
```bash
source venv/bin/activate
# O si el venv está en otra ubicación:
# source /opt/render/project/src/backend/venv/bin/activate
```

## 📋 Comandos para Ejecutar en el Shell de Render

### Paso 1: Navegar al Directorio del Backend

```bash
cd /opt/render/project/src/backend
# O la ruta donde esté tu proyecto
pwd  # Para verificar dónde estás
```

### Paso 2: Instalar Dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Paso 3: Aplicar Migraciones (CRÍTICO)

**⚠️ IMPORTANTE: Si ves el error "column inventario_tienda.cuit does not exist", ejecuta esto PRIMERO:**

```bash
python manage.py migrate inventario --verbosity=2
```

Si hay algún problema con las migraciones, puedes forzar la aplicación:

```bash
python manage.py migrate inventario 0010 --fake-initial
python manage.py migrate inventario
```

### Paso 4: Verificar Migraciones

```bash
python manage.py showmigrations inventario
```

Debes ver todas con `[X]`, incluyendo la `0010_tienda_api_key_arca_tienda_certificado_afip_and_more`.

Si la migración `0010` muestra `[ ]` (sin X), significa que NO se aplicó. Ejecuta:
```bash
python manage.py migrate inventario 0010
```

### Paso 5: Recolectar Archivos Estáticos (si aplica)

```bash
python manage.py collectstatic --noinput
```

### Paso 6: Verificar que las Tablas Existen

```bash
python manage.py shell
```

Dentro del shell de Python:

```python
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
print("✅ Tabla inventario_factura existe:", existe)

# Verificar campos en inventario_tienda
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda' 
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip');
""")
campos = [row[0] for row in cursor.fetchall()]
print("✅ Campos en inventario_tienda:", campos)

exit()
```

## 🔄 Todo en un Solo Comando (Copiar y Pegar)

```bash
cd /opt/render/project/src/backend && \
pip install --upgrade pip && \
pip install -r requirements.txt && \
python manage.py migrate inventario && \
python manage.py showmigrations inventario && \
echo "✅ Deployment completado"
```

## 📝 Verificación Rápida

```bash
python manage.py shell -c "
from inventario.models import Factura, Tienda
print('✅ Tabla Factura:', Factura.objects.model._meta.db_table)
tienda = Tienda.objects.first()
if tienda:
    print('✅ Campos disponibles:', hasattr(tienda, 'cuit'), hasattr(tienda, 'tipo_facturacion'))
"
```

## ⚠️ Si Algo Sale Mal

### Error: "No module named 'django'"

```bash
# Asegúrate de estar en el directorio correcto
cd /opt/render/project/src/backend

# Verifica que requirements.txt existe
ls -la requirements.txt

# Instala dependencias
pip install -r requirements.txt
```

### Error: "Table already exists"

Las migraciones ya están aplicadas. Solo verifica:
```bash
python manage.py showmigrations inventario
```

### Error: "Migration 0010 is not applied"

```bash
python manage.py migrate inventario 0010
```

## 📚 Archivos de Referencia

- **SQL Directo**: `scripts/migracion_0010.sql` (solo si las migraciones fallan)
- **Script Automático**: `scripts/deploy_render.sh`
- **Instrucciones Detalladas**: `INSTRUCCIONES_RENDER.md`

