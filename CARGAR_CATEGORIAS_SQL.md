# Cargar Categorías de Mercado Libre con SQL

Si el comando de Django se queda tildado en Render, puedes generar un script SQL y ejecutarlo directamente en DBeaver.

## 📋 Pasos

### 1. Generar el Script SQL (Localmente)

En tu máquina local, ejecuta:

```bash
cd backend
python scripts/generar_sql_categorias_ml.py --site_id MLA --output categorias_ml.sql
```

Este script:
- Descarga todas las categorías desde la API de Mercado Libre
- Genera un archivo SQL con todos los INSERT statements
- Usa `ON CONFLICT` para evitar duplicados

### 2. Abrir el Archivo en DBeaver

1. Abre **DBeaver**
2. Conéctate a tu base de datos de **producción** (la de Render)
3. Abre el archivo `categorias_ml.sql` que se generó

### 3. Ejecutar el Script

1. **Revisa el script** (debería tener miles de líneas de INSERT)
2. **Ejecuta todo el script** (Ctrl+Enter o el botón de ejecutar)
3. **Espera** a que termine (puede tardar 1-2 minutos)

### 4. Verificar que Funcionó

En DBeaver, ejecuta esta consulta:

```sql
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE is_leaf = true) as categorias_hoja
FROM inventario_categoriamercadolibre
WHERE site_id = 'MLA';
```

Deberías ver:
- **Total**: ~5,000 - 8,000 categorías
- **Categorías hoja**: ~1,500 - 2,500

## 🔄 Si Necesitas Actualizar

Si ya tienes categorías y quieres actualizarlas:

1. **Opción 1**: El script SQL usa `ON CONFLICT DO UPDATE`, así que puedes ejecutarlo de nuevo y actualizará las existentes.

2. **Opción 2**: Limpia primero y luego inserta:
   ```sql
   DELETE FROM inventario_categoriamercadolibre WHERE site_id = 'MLA';
   ```
   Luego ejecuta el script SQL completo.

## ⚠️ Notas Importantes

- **Asegúrate de estar conectado a la base de datos correcta** (producción, no staging)
- **El script es seguro**: usa transacciones (BEGIN/COMMIT) y `ON CONFLICT` para evitar duplicados
- **Puede tardar**: Insertar miles de registros puede tomar 1-2 minutos
- **Verifica después**: Usa la consulta de verificación para confirmar

## 🐛 Troubleshooting

### Error: "relation 'inventario_categoriamercadolibre' does not exist"

**Solución**: La migración no está aplicada. Ejecuta en Render:
```bash
python manage.py migrate inventario 0017
```

### Error: "duplicate key value violates unique constraint"

**Solución**: El script usa `ON CONFLICT`, así que esto no debería pasar. Si ocurre, primero limpia:
```sql
DELETE FROM inventario_categoriamercadolibre WHERE site_id = 'MLA';
```
Y luego ejecuta el script de nuevo.

### El script SQL es muy grande

**Es normal**: Puede tener 10,000+ líneas. DBeaver puede manejarlo sin problemas.

## ✅ Verificar en el Frontend

Después de ejecutar el SQL:

1. Recarga la página del frontend donde seleccionas productos
2. Deberías ver **todas las categorías** disponibles
3. Puedes buscar categorías escribiendo en el campo de búsqueda
