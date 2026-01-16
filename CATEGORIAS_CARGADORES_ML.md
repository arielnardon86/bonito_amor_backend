# 🔍 Cómo Encontrar la Categoría de Cargadores en Mercado Libre

## Búsquedas Recomendadas

Cuando busques la categoría para "Cargadores accesorios", prueba estas búsquedas en el selector de categorías:

### Búsquedas que deberían funcionar:

1. **"cargador"** - Busca todas las categorías que contengan "cargador"
2. **"cargadores"** - Plural
3. **"power bank"** - Si es un power bank
4. **"batería"** - Si es una batería externa
5. **"accesorio"** - Busca accesorios en general
6. **"celular"** - Accesorios para celular
7. **"smartphone"** - Accesorios para smartphone

### Categorías Comunes en Mercado Libre:

- **MLA430687** - Cargadores
- **MLA430688** - Cargadores para Celulares
- **MLA430689** - Power Banks
- **MLA430690** - Baterías Externas
- **MLA1430** - Ropa y Accesorios (categoría padre)

## 💡 Consejos para Buscar Categorías

1. **Usa términos simples**: En lugar de "Cargadores accesorios", busca solo "cargador"
2. **Prueba sinónimos**: "power bank", "batería externa", "cargador portátil"
3. **Busca en inglés**: Muchas categorías tienen nombres en inglés
4. **Busca la categoría padre**: Si no encuentras la específica, busca categorías más generales como "Accesorios para Celulares"

## 🔧 Si No Encuentras la Categoría

Si después de probar estas búsquedas no encuentras la categoría:

1. **Verifica que las categorías estén cargadas**: Asegúrate de que se hayan ejecutado las migraciones y que las categorías estén en la base de datos
2. **Usa una categoría genérica**: Puedes usar "MLA1574" (Hogar, Muebles y Decoración) o "MLA1430" (Ropa y Accesorios) como fallback
3. **Consulta directamente en Mercado Libre**: Ve a [Mercado Libre](https://www.mercadolibre.com.ar) y busca "cargador" para ver qué categoría usa ML

## 📝 Nota sobre el Error "is not modifiable"

Si recibes el error:
```
Error de validación: description.plain_text is not modifiable., available_quantity is not modifiable., ...
```

Esto significa que el producto ya está publicado en Mercado Libre y está en un estado que no permite modificaciones (por ejemplo, está vendido, cerrado, o en proceso de venta).

**Solución**: El sistema ahora detecta este error automáticamente y:
1. Limpia el `ml_item_id` del producto
2. Crea una nueva publicación en Mercado Libre

Solo necesitas intentar sincronizar el producto nuevamente.
