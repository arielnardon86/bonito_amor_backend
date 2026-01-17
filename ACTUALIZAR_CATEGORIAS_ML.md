# Actualizar Categorías de Mercado Libre en Producción

Este documento explica cómo actualizar las categorías de Mercado Libre en la base de datos de producción.

## Problema

Si ves el mensaje:
```
⚠️ No hay categorías disponibles. Por favor, ejecuta: python manage.py actualizar_categorias_ml
```

Significa que la tabla `CategoriaMercadoLibre` está vacía y necesitas ejecutar el comando de actualización.

## Solución: Ejecutar en Render

### Opción 1: Usando el Shell de Render (Recomendado)

1. **Accede al Dashboard de Render**:
   - Ve a [https://dashboard.render.com](https://dashboard.render.com)
   - Selecciona tu servicio de backend (`bonito-amor-backend`)

2. **Abre el Shell**:
   - En la barra lateral izquierda, haz clic en **"Shell"**
   - O ve a la pestaña **"Shell"** en la parte superior

3. **Ejecuta el comando**:
   ```bash
   python manage.py actualizar_categorias_ml --site_id MLA
   ```

   Para otros países:
   - Argentina: `--site_id MLA` (por defecto)
   - Brasil: `--site_id MLB`
   - México: `--site_id MLM`
   - Chile: `--site_id MLC`
   - Colombia: `--site_id MCO`

4. **Espera a que termine**:
   - El comando descargará todas las categorías desde la API pública de Mercado Libre
   - Puede tardar varios minutos (hay miles de categorías)
   - Verás un resumen al final con el total de categorías guardadas

### Opción 2: Usando SSH (si está habilitado)

Si tienes acceso SSH a tu servidor de Render:

```bash
ssh <usuario>@<servidor>
cd /app
python manage.py actualizar_categorias_ml --site_id MLA
```

## Verificar que Funcionó

Después de ejecutar el comando, deberías ver:

```
✅ Actualización completada
   📊 Total de categorías: XXXX
   ➕ Nuevas categorías: XXXX
   🔄 Categorías actualizadas: 0
   🍃 Categorías hoja: XXXX
```

Y una lista de ejemplos de categorías hoja disponibles.

## Actualizar Categorías en el Frontend

Una vez ejecutado el comando:

1. **Recarga la página** del frontend donde seleccionas productos para sincronizar
2. **Deberías ver** todas las categorías disponibles en el dropdown
3. **Puedes buscar** categorías escribiendo en el campo de búsqueda

## Re-ejecutar el Comando

Si necesitas actualizar las categorías (por ejemplo, si Mercado Libre agregó nuevas):

```bash
python manage.py actualizar_categorias_ml --site_id MLA --force
```

El flag `--force` actualizará todas las categorías existentes.

## Notas Importantes

- ⚠️ **No requiere autenticación**: El comando usa el endpoint público de Mercado Libre (`/sites/{site_id}/categories/all`), por lo que no necesitas tokens de acceso.
- ⏱️ **Puede tardar**: La descarga y procesamiento de todas las categorías puede tomar varios minutos.
- 💾 **Base de datos**: Asegúrate de que la migración `0017_create_categoria_mercadolibre.py` esté aplicada antes de ejecutar el comando.
- 🔄 **Frecuencia**: No es necesario ejecutar esto frecuentemente. Las categorías de Mercado Libre cambian muy poco.

## Troubleshooting

### Error: "No module named 'inventario.models.CategoriaMercadoLibre'"

**Solución**: Asegúrate de que la migración esté aplicada:
```bash
python manage.py migrate inventario
```

### Error: "Connection timeout" o "Network error"

**Solución**: El comando necesita acceso a internet. Verifica que Render tenga conectividad saliente.

### Error: "Table 'inventario_categoriamercadolibre' doesn't exist"

**Solución**: La migración no se aplicó. Ejecuta:
```bash
python manage.py migrate inventario 0017
```

### El comando se ejecuta pero no guarda categorías

**Solución**: Verifica los logs del comando. Puede haber un error en el formato de datos. Ejecuta con más verbosidad:
```bash
python manage.py actualizar_categorias_ml --site_id MLA --verbosity 2
```
