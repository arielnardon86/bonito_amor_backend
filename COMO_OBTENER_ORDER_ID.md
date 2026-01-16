# 📦 Cómo Obtener un ID de Orden Real de Mercado Libre

Hay varias formas de obtener un ID de orden real de Mercado Libre para probar el webhook:

## 🔧 Opción 1: Usando el Script Python (Recomendado)

El script más fácil es usar el script que creamos:

```bash
cd backend
python scripts/obtener_ordenes_ml.py
```

O si quieres especificar una tienda específica:

```bash
python scripts/obtener_ordenes_ml.py <TIENDA_ID>
```

O si quieres obtener más órdenes:

```bash
python scripts/obtener_ordenes_ml.py <TIENDA_ID> 20
```

Este script:
- ✅ Se conecta a la API de Mercado Libre
- ✅ Obtiene las últimas órdenes de tu cuenta
- ✅ Muestra información detallada de cada orden
- ✅ Te da el comando exacto para probar el webhook

## 🌐 Opción 2: Desde la Interfaz Web de Mercado Libre

### Paso 1: Acceder a Tus Ventas

1. Ve a [Mercado Libre](https://www.mercadolibre.com.ar)
2. Inicia sesión con tu cuenta
3. Ve a **"Vender"** → **"Ventas"** (o directamente a [Ventas](https://www.mercadolibre.com.ar/vender/ventas))

### Paso 2: Encontrar una Orden

1. Busca una orden reciente en la lista
2. Haz clic en la orden para ver los detalles
3. En la URL del navegador, verás algo como:
   ```
   https://www.mercadolibre.com.ar/ventas/1234567890/detalle
   ```
   El número `1234567890` es el **ID de la orden**

### Paso 3: Usar el ID

Una vez que tengas el ID, puedes probarlo:

```bash
curl -k -X POST "https://bonito-amor-backend.onrender.com/api/tiendas/e265d339-39ec-4ec5-a73c-d5a31904d29a/mercadolibre/webhook/" \
  -H "Content-Type: application/json" \
  -d '{"resource": "/orders/1234567890", "topic": "orders"}'
```

## 🔌 Opción 3: Desde la API de Mercado Libre Directamente

Si tienes acceso a la API de Mercado Libre, puedes obtener órdenes usando:

### Con curl:

```bash
# Primero necesitas tu ACCESS_TOKEN y USER_ID
ACCESS_TOKEN="tu_token_aqui"
USER_ID="tu_user_id_aqui"

curl -X GET \
  "https://api.mercadolibre.com/orders/search?seller=${USER_ID}&limit=10" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

### Con Python:

```python
import requests

ACCESS_TOKEN = "tu_token_aqui"
USER_ID = "tu_user_id_aqui"

url = f"https://api.mercadolibre.com/orders/search"
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}
params = {
    "seller": USER_ID,
    "limit": 10
}

response = requests.get(url, headers=headers, params=params)
orders = response.json()

for order in orders.get('results', []):
    print(f"Orden ID: {order['id']}")
    print(f"Estado: {order['status']}")
    print(f"Total: ${order['total_amount']}")
    print()
```

## 📱 Opción 4: Desde la App Móvil de Mercado Libre

1. Abre la app de Mercado Libre en tu celular
2. Ve a **"Vender"** → **"Ventas"**
3. Selecciona una orden
4. En los detalles de la orden, busca el **número de orden** o **ID de orden**

## ⚠️ Notas Importantes

### Estados de Orden Válidos

El webhook solo procesa órdenes en estos estados:
- ✅ `confirmed` - Orden confirmada
- ✅ `payment_required` - Pago requerido
- ✅ `payment_in_process` - Pago en proceso

Si la orden está en otro estado (como `cancelled`, `closed`, etc.), el webhook la omitirá.

### Verificar que el Producto Esté Sincronizado

Para que una orden se procese correctamente:
1. El producto en la orden debe tener un `ml_item_id` en tu sistema
2. El `ml_item_id` debe coincidir con el ID del item en Mercado Libre

### Ver los Logs

Después de probar, revisa los logs del servidor en Render para ver qué pasó:
1. Ve a tu dashboard de Render
2. Selecciona el servicio `bonito-amor-backend`
3. Ve a la pestaña **"Logs"**
4. Busca mensajes que empiecen con `INFO: Notificación recibida de ML`

## 🧪 Ejemplo Completo

```bash
# 1. Obtener órdenes
cd backend
python scripts/obtener_ordenes_ml.py

# 2. Copiar un ID de orden de la lista

# 3. Probar el webhook
curl -k -X POST \
  "https://bonito-amor-backend.onrender.com/api/tiendas/e265d339-39ec-4ec5-a73c-d5a31904d29a/mercadolibre/webhook/" \
  -H "Content-Type: application/json" \
  -d '{"resource": "/orders/<ORDER_ID_COPIADO>", "topic": "orders"}'

# 4. Verificar en los logs de Render que se procesó correctamente
```

## 🔗 Referencias

- [API de Órdenes de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/ordenes-y-envios)
- [Documentación de Búsqueda de Órdenes](https://developers.mercadolibre.com.ar/es_ar/ordenes-y-envios#buscar-ordenes)
