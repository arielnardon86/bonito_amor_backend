# 🚀 Instrucciones para Desplegar en Render.com

## 📋 Opción 1: Usando el Script Automático (Recomendado)

### En el Shell de Render:

1. **Conéctate al Shell de Render:**
   - Ve a tu servicio de Render (Web Service o Background Worker)
   - Haz clic en "Shell" en el panel izquierdo
   - Se abrirá una terminal en tu servidor

2. **Navega al directorio del proyecto:**
   ```bash
   cd /opt/render/project/src/backend
   # O la ruta donde esté tu proyecto backend
   ```

3. **Ejecuta el script de deployment:**
   ```bash
   bash scripts/deploy_render.sh
   ```

El script hará automáticamente:
- ✅ Verificar variables de entorno
- ✅ Instalar dependencias
- ✅ Aplicar migraciones
- ✅ Recolectar archivos estáticos
- ✅ Verificar que las tablas se crearon correctamente

---

## 📋 Opción 2: Comandos Manuales

Si prefieres ejecutar los comandos uno por uno:

### Paso 1: Instalar Dependencias

```bash
cd /opt/render/project/src/backend
pip install --upgrade pip
pip install -r requirements.txt
```

### Paso 2: Aplicar Migraciones

```bash
python manage.py migrate inventario
```

### Paso 3: Verificar Migraciones

```bash
python manage.py showmigrations inventario
```

Debes ver todas las migraciones con `[X]` (aplicadas), incluyendo la `0010`.

### Paso 4: Recolectar Archivos Estáticos

```bash
python manage.py collectstatic --noinput
```

### Paso 5: Verificar Base de Datos

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
print("Tabla existe:", cursor.fetchone()[0])

# Verificar campos
cursor.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'inventario_tienda' 
    AND column_name IN ('cuit', 'punto_venta', 'tipo_facturacion');
""")
print("Campos en tienda:", [row[0] for row in cursor.fetchall()])

exit()
```

---

## 📋 Opción 3: Usando SQL Directo (Si las migraciones fallan)

**⚠️ SOLO usar si las migraciones de Django fallan. Django migrations es preferible.**

### Paso 1: Descargar el archivo SQL

1. Desde tu máquina local, sube el archivo `scripts/migracion_0010.sql` a Render
2. O copia y pega el contenido en el Shell de Render

### Paso 2: Conectarte a PostgreSQL

En el Shell de Render:

```bash
# Obtener la cadena de conexión de Render
echo $DATABASE_URL

# Conectarte a PostgreSQL (si tienes psql instalado)
psql $DATABASE_URL
```

### Paso 3: Ejecutar el SQL

Dentro de psql:

```sql
\i /ruta/al/archivo/migracion_0010.sql
```

O si copiaste y pegaste:

```sql
-- Pega todo el contenido del archivo migracion_0010.sql aquí
```

### Paso 4: Marcar la migración como aplicada

Después de ejecutar el SQL, necesitas decirle a Django que la migración ya está aplicada:

```bash
python manage.py migrate inventario 0010 --fake
```

---

## 🔧 Configuración en Render Dashboard

### Variables de Entorno Necesarias

Asegúrate de tener estas variables configuradas en Render:

1. Ve a tu servicio en Render Dashboard
2. Ve a "Environment"
3. Verifica que tengas:

```
DJANGO_ENVIRONMENT=production
DJANGO_SECRET_KEY=tu-secret-key-único
DATABASE_URL=postgresql://... (debe estar configurada automáticamente)
```

### Build Command (si lo configuraste)

Si tienes un Build Command configurado en Render, debe incluir:

```bash
cd backend && pip install -r requirements.txt
```

### Start Command

Tu Start Command debe ser algo como:

```bash
cd backend && python manage.py migrate && gunicorn mi_tienda_backend.wsgi:application
```

---

## ⚠️ IMPORTANTE: Después del Deployment

### 1. Verificar que Funcione

- Accede a tu aplicación en producción
- Ve al Django Admin
- Verifica que puedas ver la tabla "Facturas"

### 2. Configurar Certificados AFIP

**⚠️ EN PRODUCCIÓN DEBES:**
- Usar certificados de **PRODUCCIÓN** (no de testing)
- Desactivar "Modo test AFIP" en Django Admin
- Ver `CONFIGURAR_FACTURACION.md` para más detalles

### 3. Probar Facturación

Haz una venta de prueba y verifica que:
- Se puede emitir una factura
- El PDF se genera correctamente
- Los datos se guardan en la base de datos

---

## 🆘 Troubleshooting

### Error: "No module named 'pyafipws'"

**Solución:**
```bash
pip install git+https://github.com/reingart/pyafipws.git
```

### Error: "Table already exists"

**Solución:** La migración ya se aplicó. Solo marca como aplicada:
```bash
python manage.py migrate inventario 0010 --fake
```

### Error: "Permission denied" al ejecutar script

**Solución:**
```bash
chmod +x scripts/deploy_render.sh
bash scripts/deploy_render.sh
```

### No puedo conectarme a PostgreSQL

**Solución:** Verifica que `DATABASE_URL` esté configurada en Render Dashboard.

---

## 📝 Checklist Post-Deployment

- [ ] Migraciones aplicadas sin errores
- [ ] Tabla `inventario_factura` existe
- [ ] Campos agregados a `inventario_tienda` y `inventario_venta`
- [ ] Servidor funcionando
- [ ] Frontend accesible
- [ ] Django Admin muestra "Facturas"
- [ ] Certificados AFIP de producción configurados
- [ ] Modo test desactivado
- [ ] Prueba de facturación exitosa

---

## 📞 Soporte

Si algo falla:
1. Revisa los logs en Render Dashboard → Logs
2. Verifica que todas las variables de entorno estén correctas
3. Revisa `DEPLOY_PRODUCCION.md` para más detalles
4. Si es necesario, revierte las migraciones: `python manage.py migrate inventario 0009`



