# 🔔 Configurar Webhook de Mercado Libre

Esta guía te ayudará a configurar el webhook para recibir notificaciones cuando se vendan productos en Mercado Libre.

## 📍 URL del Webhook

La URL del webhook tiene el siguiente formato:

```
https://[TU-DOMINIO]/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/
```

### Paso 1: Identificar tu Dominio de Producción

Según tu configuración, tu servidor está desplegado en Render. Las posibles URLs son:

- `https://bonito-amor-backend.onrender.com`
- `https://bonitoamorstock.onrender.com`
- `https://totalstock.onrender.com`

**Para verificar cuál es tu dominio:**
1. Ve a tu panel de Render
2. Selecciona tu servicio de backend
3. En la sección "Settings" o "Info", verás la URL pública

### Paso 2: Obtener el ID de tu Tienda

Tienes varias opciones para obtener el ID de tu tienda:

#### Opción A: Desde el Frontend (Más Fácil)
1. Abre tu aplicación en el navegador
2. Abre las herramientas de desarrollador (F12)
3. Ve a la consola y ejecuta:
```javascript
// Si tienes acceso al token de autenticación
fetch('/api/tiendas/', {
  headers: {
    'Authorization': 'Bearer TU_TOKEN'
  }
})
.then(r => r.json())
.then(data => console.log('ID de tienda:', data[0].id))
```

#### Opción B: Desde el Admin de Django
1. Ve a `https://[TU-DOMINIO]/admin/inventario/tienda/`
2. Haz clic en tu tienda
3. El ID aparecerá en la URL: `/admin/inventario/tienda/[ID-TIENDA]/change/`

#### Opción C: Desde la API (Sin Autenticación)
```bash
curl https://[TU-DOMINIO]/api/tiendas/
```

Esto te devolverá un JSON con todas las tiendas, incluyendo sus IDs.

### Paso 3: Construir la URL Completa

Una vez que tengas:
- **Dominio**: `https://totalstock.onrender.com` (ejemplo)
- **ID de Tienda**: `31551735-b173-4831-9c4a-3b8d5196dbd5` (ejemplo)

Tu URL del webhook sería:

```
https://totalstock.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

## 🔧 Configurar el Webhook en Mercado Libre

### Paso 1: Acceder a la Configuración de Webhooks

1. Ve a [Mercado Libre Developers](https://developers.mercadolibre.com.ar/)
2. Inicia sesión con tu cuenta
3. Ve a **"Mis Aplicaciones"**
4. Selecciona tu aplicación (la misma que usas para OAuth)
5. Busca la sección **"Webhooks"** o **"Notificaciones"**

### Paso 2: Agregar el Webhook

1. Haz clic en **"Agregar Webhook"** o **"Crear Notificación"**
2. Ingresa la URL completa del webhook (la que construiste arriba)
3. Selecciona los **Topics** (temas) que quieres recibir:
   - ✅ **`orders`** - Para recibir notificaciones cuando se crean órdenes/pedidos
   - ✅ **`items`** - (Opcional) Para recibir notificaciones sobre cambios en items
   - ✅ **`payments`** - (Opcional) Para recibir notificaciones sobre pagos

### Paso 3: Verificar el Webhook

Mercado Libre enviará una solicitud de verificación a tu endpoint. El sistema debería responder automáticamente con `200 OK`.

**Para verificar que funciona:**
1. Haz una venta de prueba en Mercado Libre
2. Revisa los logs de tu servidor para ver si recibiste la notificación
3. Verifica que el stock se actualizó en tu sistema

## 🧪 Probar el Webhook Localmente

Si estás desarrollando localmente, necesitas exponer tu servidor local a internet. Puedes usar **ngrok**:

### Instalar ngrok
```bash
# macOS
brew install ngrok

# O descargar desde https://ngrok.com/
```

### Exponer tu servidor local
```bash
# En una terminal, inicia tu servidor Django
cd backend
python manage.py runserver

# En otra terminal, expón el puerto 8000
ngrok http 8000
```

Esto te dará una URL temporal como: `https://abc123.ngrok.io`

Tu URL del webhook para desarrollo sería:
```
https://abc123.ngrok.io/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/
```

⚠️ **Nota**: La URL de ngrok cambia cada vez que lo reinicias (a menos que tengas cuenta de pago). Para desarrollo, considera usar una cuenta gratuita de ngrok que te da una URL fija.

## 📝 Ejemplo de Notificación

Cuando Mercado Libre envía una notificación, el payload se ve así:

```json
{
  "resource": "/orders/123456789",
  "topic": "orders",
  "user_id": 123456789,
  "application_id": 1234567890123456,
  "attempts": 1,
  "sent": "2024-01-15T10:30:00.000Z",
  "received": "2024-01-15T10:30:00.100Z"
}
```

El sistema automáticamente:
1. Extrae el ID de la orden (`123456789`)
2. Obtiene los detalles de la orden desde la API de ML
3. Identifica los productos vendidos por su `ml_item_id`
4. Actualiza el stock restando las unidades vendidas

## 🔍 Verificar que Funciona

### Ver logs del servidor
```bash
# En Render, ve a la sección "Logs" de tu servicio
# O si estás en local:
tail -f logs/django.log
```

Deberías ver mensajes como:
```
INFO: Notificación recibida de ML: topic=orders, resource=/orders/123456789
INFO: Orden 123456789 obtenida exitosamente
INFO: Stock actualizado para Producto X: -1 unidades (nuevo stock: 5)
```

### Verificar en la base de datos
```python
# En Django shell
from inventario.models import Producto
producto = Producto.objects.get(ml_item_id='MLA123456789')
print(f"Stock actual: {producto.stock}")
```

## ⚠️ Consideraciones Importantes

1. **HTTPS Requerido**: Mercado Libre solo envía webhooks a URLs HTTPS. Asegúrate de que tu servidor esté configurado con SSL.

2. **Autenticación**: El endpoint del webhook NO requiere autenticación (Mercado Libre no puede autenticarse con tu sistema). El sistema verifica que la notificación venga de ML validando el `resource` y `topic`.

3. **Idempotencia**: El sistema está diseñado para manejar notificaciones duplicadas. Si recibes la misma notificación dos veces, solo procesará la orden una vez.

4. **Rate Limiting**: Mercado Libre puede enviar múltiples notificaciones rápidamente. El sistema procesa cada una de forma asíncrona para evitar bloqueos.

## 🐛 Troubleshooting

### El webhook no recibe notificaciones

1. **Verifica la URL**: Asegúrate de que la URL sea exactamente correcta (sin espacios, con HTTPS)
2. **Verifica SSL**: Mercado Libre requiere HTTPS
3. **Revisa los logs**: Busca errores en los logs del servidor
4. **Prueba manualmente**: Puedes hacer una petición POST de prueba:
```bash
curl -X POST https://[TU-DOMINIO]/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }'
```

### El stock no se actualiza

1. **Verifica que el producto tenga `ml_item_id`**: Solo los productos sincronizados con ML tienen este campo
2. **Verifica los logs**: Busca errores al obtener la orden o actualizar el stock
3. **Verifica que la orden esté en estado válido**: Solo se procesan órdenes en estado `confirmed`, `payment_required`, `payment_in_process` o `paid` (venta cobrada)

### Venta en Mercado Libre no se refleja en Total Stock

**Checklist de verificación:**

1. ☐ **Webhook registrado en ML**: [Mis Aplicaciones](https://applications.mercadolibre.com.ar) → tu app → Webhooks → URL correcta
2. ☐ **Topic `orders` seleccionado** en la configuración del webhook
3. ☐ **URL exacta**: `https://[TU-DOMINIO]/api/tiendas/[UUID-TIENDA]/mercadolibre/webhook/`
4. ☐ **Productos con `ml_item_id`**: Los items de la orden deben estar sincronizados (importados desde ML)
5. ☐ **Logs en Render**: Busca `INFO: Notificación recibida de ML` o `Orden X con estado 'paid'` para ver si llegaron notificaciones
6. ☐ **Token vigente**: Renová la conexión ML en Configuración si hay errores 401

### Error 404 al recibir notificación

1. **Verifica la URL**: Asegúrate de que el ID de la tienda sea correcto
2. **Verifica que el endpoint esté registrado**: Revisa `mi_tienda_backend/urls.py` para confirmar que las rutas están configuradas

## 📚 Referencias

- [Documentación de Webhooks de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/notificaciones)
- [Documentación de Órdenes de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/ordenes-y-envios)
