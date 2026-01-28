# 🧪 Probar Webhook de Mercado Libre Localmente

Esta guía te ayudará a probar y verificar que el webhook funciona correctamente desde tu entorno local.

## 📋 Pasos para Probar el Webhook Localmente

### Paso 1: Iniciar tu Servidor Django

```bash
cd backend
python manage.py runserver
```

Tu servidor estará disponible en `http://localhost:8000`

### Paso 2: Exponer tu Servidor Local a Internet

Mercado Libre necesita poder acceder a tu servidor local desde internet. Para esto, usa **ngrok**:

#### Instalar ngrok

```bash
# macOS (con Homebrew)
brew install ngrok

# O descargar desde https://ngrok.com/download
```

#### Exponer el puerto 8000

En una **nueva terminal** (deja el servidor Django corriendo):

```bash
ngrok http 8000
```

Esto te dará una salida como:

```
Forwarding  https://abc123def456.ngrok.io -> http://localhost:8000
```

**Copia la URL HTTPS** (la que empieza con `https://`)

### Paso 3: Construir la URL del Webhook

Tu URL del webhook será:

```
https://abc123def456.ngrok.io/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/
```

**Para obtener el ID de tu tienda:**

```bash
# Opción 1: Desde la API
curl http://localhost:8000/api/tiendas/ | python -m json.tool

# Opción 2: Desde Django shell
python manage.py shell
```

En el shell:
```python
from inventario.models import Tienda
tienda = Tienda.objects.first()
print(f"ID de tienda: {tienda.id}")
exit()
```

### Paso 4: Probar el Webhook Manualmente

Puedes simular una notificación de Mercado Libre haciendo una petición POST:

```bash
curl -X POST http://localhost:8000/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }'
```

**O usando la URL de ngrok:**

```bash
curl -X POST https://abc123def456.ngrok.io/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/ \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }'
```

### Paso 5: Verificar los Logs

El sistema registrará información en los logs. Deberías ver algo como:

```
INFO: Notificación recibida de ML: topic=orders, resource=/orders/123456789
INFO: Intentando obtener orden 123456789 desde ML...
```

**Para ver los logs en tiempo real:**

```bash
# En otra terminal, mientras el servidor Django está corriendo
# Los logs aparecerán en la consola donde está corriendo runserver
```

## 🔍 Verificar que Funciona Correctamente

### 1. Verificar la Respuesta del Endpoint

El endpoint debería responder con `200 OK` y un JSON:

```json
{
  "status": "success",
  "message": "Orden procesada correctamente",
  "order_id": "123456789"
}
```

### 2. Verificar que se Obtiene la Orden desde ML

El sistema intentará obtener la orden desde Mercado Libre. Si la orden existe y está en un estado válido, verás en los logs:

```
INFO: Orden 123456789 obtenida exitosamente
INFO: Procesando orden con estado: confirmed
```

### 3. Verificar que se Actualiza el Stock

Si tienes un producto sincronizado con ML y la orden contiene ese producto, el stock debería actualizarse.

**Para verificar:**

```bash
python manage.py shell
```

```python
from inventario.models import Producto

# Ver productos sincronizados con ML
productos_ml = Producto.objects.filter(ml_item_id__isnull=False).exclude(ml_item_id='')
for p in productos_ml:
    print(f"{p.nombre}: Stock={p.stock}, ML Item ID={p.ml_item_id}")

# Ver el stock de un producto específico antes y después
producto = Producto.objects.get(ml_item_id='TU_ML_ITEM_ID')
print(f"Stock actual: {producto.stock}")
```

### 4. Probar con una Orden Real de Mercado Libre

Para probar con una orden real:

1. **Configura el webhook en Mercado Libre** con la URL de ngrok:
   ```
   https://abc123def456.ngrok.io/api/tiendas/[ID-TIENDA]/mercadolibre/webhook/
   ```

2. **Haz una venta de prueba** en Mercado Libre de un producto que esté sincronizado

3. **Observa los logs** en tiempo real para ver la notificación

## 🐛 Troubleshooting

### Error: "Connection refused" o "Cannot connect"

**Problema**: ngrok no está corriendo o el servidor Django no está activo.

**Solución**:
1. Verifica que `python manage.py runserver` esté corriendo
2. Verifica que ngrok esté corriendo en otra terminal
3. Asegúrate de usar la URL HTTPS de ngrok (no HTTP)

### Error: "404 Not Found"

**Problema**: La URL del webhook es incorrecta o el ID de tienda no existe.

**Solución**:
1. Verifica que el ID de tienda sea correcto
2. Verifica que la ruta sea exactamente: `/api/tiendas/[ID]/mercadolibre/webhook/`
3. Prueba acceder a la URL sin el webhook primero: `http://localhost:8000/api/tiendas/`

### Error: "No hay token de acceso configurado"

**Problema**: La tienda no tiene configurado el token de Mercado Libre.

**Solución**:
1. Completa el flujo OAuth de Mercado Libre primero
2. Verifica que `ml_access_token` esté configurado en la tienda

### Error: "Orden no encontrada" o "No se pudo obtener información"

**Problema**: El ID de orden que estás probando no existe en Mercado Libre, o no tienes permisos para verla.

**Solución**:
1. Usa un ID de orden real de tu cuenta de Mercado Libre
2. Verifica que el token de acceso tenga permisos para leer órdenes
3. Prueba obtener la orden manualmente desde la API de ML

### El stock no se actualiza

**Problema**: El producto no está sincronizado o la orden no contiene ese producto.

**Solución**:
1. Verifica que el producto tenga `ml_item_id` configurado
2. Verifica que el `ml_item_id` en la orden coincida con el de tu producto
3. Revisa los logs para ver si hay errores al actualizar el stock

## 📝 Script de Prueba Completo

Crea un archivo `test_webhook.sh`:

```bash
#!/bin/bash

# Configura estas variables
TIENDA_ID="tu-id-de-tienda"
NGROK_URL="https://abc123def456.ngrok.io"  # O usa localhost:8000 para pruebas locales

echo "🧪 Probando webhook de Mercado Libre"
echo "======================================"
echo ""

# Probar con una orden de ejemplo
echo "📤 Enviando notificación de prueba..."
curl -X POST "${NGROK_URL}/api/tiendas/${TIENDA_ID}/mercadolibre/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }' \
  -w "\n\nStatus: %{http_code}\n"

echo ""
echo "✅ Si ves Status: 200, el endpoint está funcionando"
echo "📋 Revisa los logs del servidor Django para ver más detalles"
```

Hazlo ejecutable y úsalo:

```bash
chmod +x test_webhook.sh
./test_webhook.sh
```

## 🔄 Flujo Completo de Prueba

1. ✅ Inicia el servidor Django: `python manage.py runserver`
2. ✅ Inicia ngrok: `ngrok http 8000`
3. ✅ Obtén el ID de tu tienda
4. ✅ Construye la URL del webhook con ngrok
5. ✅ Configura el webhook en Mercado Libre (opcional, para pruebas reales)
6. ✅ Prueba manualmente con curl
7. ✅ Verifica los logs
8. ✅ Verifica que el stock se actualiza (si tienes una orden real)

## 💡 Tips

- **Mantén ngrok corriendo**: Si cierras ngrok, la URL cambiará y tendrás que actualizar la configuración en Mercado Libre
- **Usa una cuenta gratuita de ngrok**: Te permite tener una URL fija (útil para desarrollo)
- **Revisa los logs constantemente**: Te darán información valiosa sobre qué está pasando
- **Prueba primero con curl**: Antes de configurar en ML, prueba manualmente para asegurarte de que funciona

## ✅ Checklist de Verificación

- [ ] Servidor Django corriendo en `localhost:8000`
- [ ] ngrok corriendo y exponiendo el puerto 8000
- [ ] ID de tienda obtenido
- [ ] URL del webhook construida correctamente
- [ ] Petición POST de prueba responde con 200 OK
- [ ] Logs muestran que se recibió la notificación
- [ ] (Opcional) Orden real procesada y stock actualizado
