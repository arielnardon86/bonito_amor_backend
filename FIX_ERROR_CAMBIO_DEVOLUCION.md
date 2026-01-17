# Fix: Error de Importación de CambioDevolucion en Producción

## Problema
Error al iniciar el servicio en producción:
```
ImportError: cannot import name 'CambioDevolucion' from 'inventario.models'
```

## Causa
La migración `0013_cambiodevolucion_detallecambiodevolucion` no se ha aplicado en producción. Las tablas no existen en la base de datos.

## Solución

### Opción 1: Aplicar la migración manualmente (RECOMENDADO)

1. **Accede al Shell de Render**:
   - Ve al dashboard de Render
   - Selecciona el servicio backend
   - Ve a la pestaña "Shell"

2. **Aplica la migración**:
   ```bash
   python manage.py migrate inventario 0013_cambiodevolucion_detallecambiodevolucion
   ```

3. **Verifica que se aplicó correctamente**:
   ```bash
   python manage.py showmigrations inventario | grep 0013
   ```
   
   Debe mostrar:
   ```
   [X] 0013_cambiodevolucion_detallecambiodevolucion
   ```

4. **Reinicia el servicio**:
   - El servicio debería reiniciarse automáticamente
   - O ve a la pestaña "Manual Deploy" y haz clic en "Deploy latest commit"

### Opción 2: Aplicar todas las migraciones pendientes

Si prefieres aplicar todas las migraciones pendientes:

```bash
python manage.py migrate inventario
```

### Opción 3: Si el servicio no puede iniciar

Si el servicio no puede iniciar debido a este error, necesitas:

1. **Comentar temporalmente las importaciones en `views.py`**:
   - Esto NO es necesario si puedes acceder al Shell sin que el servicio esté corriendo
   - Pero si es necesario, puedes comentar temporalmente la línea 41 en `views.py`:
   ```python
   # from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda, Factura, CambioDevolucion, DetalleCambioDevolucion
   ```
   - Y luego aplicar la migración
   - Finalmente, descomentar la línea y hacer un nuevo deploy

2. **O mejor: Aplica la migración antes del deploy**:
   - Si tienes acceso a la base de datos directamente, puedes aplicar la migración SQL manualmente
   - Pero la forma más segura es aplicar la migración desde el Shell

## Verificación Final

Después de aplicar la migración, verifica:

1. **Que el servicio se inició correctamente**:
   - Ve a los logs del servicio
   - No debe haber errores de importación

2. **Que las tablas existen**:
   ```bash
   python manage.py dbshell
   ```
   
   Luego en PostgreSQL:
   ```sql
   \dt inventario_cambiodevolucion
   \dt inventario_detaldecambiodevolucion
   ```
   
   Deben mostrar las tablas.

3. **Que el endpoint funciona**:
   - Prueba acceder a `/api/cambios-devoluciones/`
   - Debe responder correctamente (401 si no estás autenticado, pero no 500)

## Notas

- **Importante**: Asegúrate de que la migración `0013_cambiodevolucion_detallecambiodevolucion.py` esté en el repositorio antes de aplicar
- Si necesitas verificar qué migraciones están aplicadas:
  ```bash
  python manage.py showmigrations inventario
  ```
- Si la migración ya está aplicada pero el error persiste, puede ser un problema de cache. Reinicia el servicio.

