# ✅ Verificar Webhook en Producción

Tu webhook está configurado en:
```
https://bonito-amor-backend.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

## 🔍 Verificación

### 1. Verificar que el Endpoint Responde

**GET (Validación de Mercado Libre):**
```bash
curl https://bonito-amor-backend.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

**Deberías ver:**
```json
{
  "status": "ok",
  "message": "Webhook configurado correctamente",
  "tienda_id": "31551735-b173-4831-9c4a-3b8d5196dbd5"
}
```

**POST (Notificación de prueba):**
```bash
curl -X POST https://bonito-amor-backend.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }'
```

## ✅ Estado Actual

- ✅ Webhook configurado en Mercado Libre
- ✅ URL de producción configurada
- ✅ Endpoint accesible públicamente
- ✅ Soporta GET (validación) y POST (notificaciones)

## 🧪 Cómo Probar que Funciona

### Opción 1: Hacer una Venta Real en Mercado Libre

1. Publica un producto en Mercado Libre (si no lo has hecho)
2. Haz una venta de prueba (puedes comprarlo tú mismo)
3. Revisa los logs de tu servidor en Render para ver si recibiste la notificación
4. Verifica que el stock se actualizó en tu sistema

### Opción 2: Verificar en los Logs de Render

1. Ve a tu panel de Render
2. Selecciona tu servicio de backend
3. Ve a la sección "Logs"
4. Busca mensajes como:
   ```
   INFO: Notificación recibida de ML: topic=orders, resource=/orders/123456789
   INFO: Orden 123456789 obtenida exitosamente
   INFO: Stock actualizado para Producto X: -1 unidades (nuevo stock: 5)
   ```

### Opción 3: Verificar en la Base de Datos

```python
# En Django shell (en producción o localmente conectado a producción)
from inventario.models import Producto

# Ver productos sincronizados con ML
productos_ml = Producto.objects.filter(ml_item_id__isnull=False).exclude(ml_item_id='')
for p in productos_ml:
    print(f"{p.nombre}: Stock={p.stock}, ML Item ID={p.ml_item_id}")
```

## 📋 Checklist de Funcionamiento

Cuando Mercado Libre envíe una notificación:

- [ ] El webhook recibe la notificación (ver logs)
- [ ] Se obtiene la orden desde la API de ML
- [ ] Se identifica el producto por `ml_item_id`
- [ ] Se actualiza el stock restando las unidades vendidas
- [ ] Se registra en los logs

## 🔄 Flujo Completo

1. **Cliente compra en Mercado Libre** → ML crea una orden
2. **Mercado Libre envía notificación** → POST a tu webhook
3. **Tu servidor procesa la notificación** → Obtiene detalles de la orden
4. **Identifica productos vendidos** → Por `ml_item_id`
5. **Actualiza stock** → Resta cantidad vendida
6. **Registra en logs** → Para auditoría

## ⚠️ Consideraciones

### Si el Stock No Se Actualiza

1. **Verifica que el producto tenga `ml_item_id`:**
   - Solo productos sincronizados con ML tienen este campo
   - Si no está sincronizado, el webhook no puede actualizar su stock

2. **Verifica que la orden esté en estado válido:**
   - Solo se procesan órdenes en: `confirmed`, `payment_required`, `payment_in_process`
   - Órdenes canceladas o pendientes no actualizan stock

3. **Revisa los logs:**
   - Busca errores al obtener la orden
   - Busca errores al actualizar el stock

### Si No Recibes Notificaciones

1. **Verifica la configuración en Mercado Libre:**
   - La URL debe ser exactamente correcta
   - El topic debe ser `orders`
   - El webhook debe estar activo

2. **Verifica que el servidor esté corriendo:**
   - Render puede poner el servidor en "sleep" si no hay tráfico
   - La primera petición puede tardar unos segundos en "despertar" el servidor

3. **Revisa los logs de Render:**
   - Busca errores 500 o 404
   - Verifica que el endpoint esté accesible

## 🎉 ¡Listo!

Tu webhook está configurado y funcionando. Ahora:

1. **Cuando haya una venta en Mercado Libre**, el stock se actualizará automáticamente
2. **Revisa los logs periódicamente** para asegurarte de que todo funciona
3. **Verifica el stock** después de cada venta para confirmar que se actualizó

## 📝 Próximos Pasos

- [ ] Hacer una venta de prueba en Mercado Libre
- [ ] Verificar que el stock se actualizó
- [ ] Revisar los logs para confirmar que funcionó
- [ ] (Opcional) Configurar alertas o notificaciones cuando se actualice el stock
