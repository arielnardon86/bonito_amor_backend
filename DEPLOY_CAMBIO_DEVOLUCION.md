# Deploy de Sistema de Cambios/Devoluciones a Producción

## Cambios Implementados

Este deploy incluye:
- Sistema completo de cambios/devoluciones con manejo de stock
- Generación automática de notas de crédito
- Ventas pendientes para diferencias a pagar
- Métricas mejoradas (excluye notas de crédito, cuenta solo diferencias)
- Interfaz integrada con Punto de Venta
- Visualización mejorada de productos en recibos y métricas

## Pasos para Deploy

### 1. Verificar que el código está en GitHub

Los cambios ya fueron commitados. Verifica que estén en GitHub:

**Backend:**
```bash
cd backend
git log --oneline -1
# Debe mostrar: feat: Implementar sistema de cambios/devoluciones...
git push origin main  # Si aún no se subió
```

**Frontend:**
```bash
cd frontend
git log --oneline -1
# Debe mostrar: feat: Integrar interfaz de cambios/devoluciones...
git push origin main  # Si aún no se subió
```

### 2. Aplicar Migración en Render

#### Opción A: Usando el Shell de Render (Recomendado)

1. Ve a tu servicio de backend en Render
2. Abre el **Shell** (pestaña "Shell" en el dashboard)
3. Ejecuta el siguiente comando:

```bash
python manage.py migrate inventario 0013_cambiodevolucion_detallecambiodevolucion
```

#### Opción B: Aplicar todas las migraciones pendientes

Si prefieres aplicar todas las migraciones pendientes:

```bash
python manage.py migrate inventario
```

#### Verificar que la migración se aplicó correctamente

```bash
python manage.py showmigrations inventario | grep 0013
```

Debe mostrar:
```
[X] 0013_cambiodevolucion_detallecambiodevolucion
```

Si muestra `[X]` significa que ya está aplicada correctamente. Si muestra `[ ]` significa que aún no se ha aplicado.

### 3. Verificar que el servicio se reinició correctamente

Después de que Render detecte los cambios en GitHub, el servicio se reiniciará automáticamente. Verifica en los logs:

1. Ve a **Logs** en el dashboard de Render
2. Busca mensajes de éxito de Django
3. Verifica que no haya errores de migración

### 4. Verificar que el Frontend se desplegó

El frontend debería desplegarse automáticamente si está configurado con auto-deploy. Verifica en el dashboard de Render que el build fue exitoso.

## Archivos Modificados

### Backend:
- `inventario/models.py` - Nuevos modelos CambioDevolucion y DetalleCambioDevolucion
- `inventario/serializers.py` - Serializers para cambios/devoluciones
- `inventario/views.py` - Lógica de cambios/devoluciones y métricas mejoradas
- `inventario/urls.py` - Rutas para cambios/devoluciones
- `inventario/migrations/0013_cambiodevolucion_detallecambiodevolucion.py` - Nueva migración
- `mi_tienda_backend/urls.py` - Registro de rutas

### Frontend:
- `src/components/CambioDevolucion.js` - Nuevo componente
- `src/components/VentasPage.jsx` - Mejoras en visualización
- `src/components/ReciboImpresion.js` - Mostrar saldo a favor
- `src/components/MetricasVentas.js` - Mejoras en visualización
- `src/App.js` - Ruta para CambioDevolucion

## Rollback (Si es necesario)

Si necesitas hacer rollback:

1. **Revertir migración:**
```bash
python manage.py migrate inventario 0012_tienda_condicion_iva_emisor
```

2. **Revertir código en GitHub:**
```bash
git revert HEAD
git push origin main
```

## Notas Importantes

- La migración es **no destructiva** - no elimina datos existentes
- Los cambios son **compatibles hacia atrás** - las ventas existentes siguen funcionando
- Las notas de crédito generadas antes de este deploy seguirán siendo válidas
- Las métricas se calcularán correctamente para datos históricos y nuevos

## Soporte

Si encuentras algún problema:
1. Revisa los logs en Render
2. Verifica que la migración se aplicó correctamente
3. Verifica que todos los servicios están corriendo

