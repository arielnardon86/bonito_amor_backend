# Verificar Categorías de Mercado Libre Cargadas

## 🔍 Verificar Cuántas Categorías se Cargaron

### Opción 1: Script Rápido (Recomendado)

En el Shell de Render, ejecuta:

```bash
python manage.py shell < scripts/verificar_categorias_ml.py
```

O si prefieres ejecutarlo directamente:

```bash
python scripts/verificar_categorias_ml.py
```

### Opción 2: Consulta Directa en Django Shell

En el Shell de Render:

```bash
python manage.py shell
```

Luego ejecuta:

```python
from inventario.models import CategoriaMercadoLibre

# Total de categorías
total = CategoriaMercadoLibre.objects.count()
print(f"Total: {total}")

# Categorías hoja (las que se pueden usar)
hoja = CategoriaMercadoLibre.objects.filter(is_leaf=True).count()
print(f"Categorías hoja: {hoja}")

# Ver algunas categorías
for cat in CategoriaMercadoLibre.objects.filter(is_leaf=True)[:10]:
    print(f"- {cat.nombre} ({cat.id})")
```

## 📊 Cantidades Esperadas

Para **MLA (Argentina)**, deberías tener aproximadamente:
- **Total de categorías**: 5,000 - 8,000
- **Categorías hoja** (las que puedes usar): 1,500 - 2,500

Si tienes menos de **1,000 categorías hoja**, probablemente el comando se interrumpió.

## 🔄 Re-ejecutar el Comando

Si verificaste que faltan categorías, re-ejecuta el comando:

```bash
python manage.py actualizar_categorias_ml --site_id MLA --force
```

El flag `--force` actualizará todas las categorías existentes.

### ⏱️ Tiempo Esperado

El comando puede tardar:
- **5-10 minutos** para descargar todas las categorías
- **10-15 minutos** si la conexión es lenta
- **Más de 15 minutos** si hay problemas de red

### 💡 Consejos

1. **Deja el Shell abierto**: No cierres la ventana mientras se ejecuta
2. **No interrumpas**: Deja que termine completamente
3. **Verifica después**: Usa el script de verificación para confirmar

## ❓ ¿El Comando se Interrumpió?

Si el comando se interrumpió (por timeout, cierre de sesión, etc.):

1. **Verifica cuántas categorías hay** (usando el script arriba)
2. **Re-ejecuta el comando** con `--force`:
   ```bash
   python manage.py actualizar_categorias_ml --site_id MLA --force
   ```
3. **Espera a que termine completamente**
4. **Verifica nuevamente** que se cargaron todas

## ✅ Verificar que Funcionó en el Frontend

Después de cargar las categorías:

1. Ve al frontend donde seleccionas productos para sincronizar
2. Deberías ver **muchas categorías** en el dropdown
3. Puedes **buscar** categorías escribiendo en el campo de búsqueda
4. Si solo ves 10 categorías de fallback, significa que no se cargaron correctamente
