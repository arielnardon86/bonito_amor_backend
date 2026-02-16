# 🧪 Guía para Probar el Webhook de Mercado Libre

Esta guía te ayudará a probar el webhook de Mercado Libre y ver qué información devuelve.

## 📋 Información del Webhook

- **URL del Webhook**: `https://bonito-amor-backend.onrender.com/api/tiendas/e265d339-39ec-4ec5-a73c-d5a31904d29a/mercadolibre/webhook/`
- **Métodos soportados**: `GET` (validación) y `POST` (notificaciones)

## 🚀 Formas de Probar

### Opción 1: Script Bash (Recomendado)

El script más fácil de usar, solo necesitas tener `curl` instalado:

```bash
cd backend/scripts
./probar_webhook_ml.sh
```

Para probar con una orden real de Mercado Libre:

```bash
./probar_webhook_ml.sh <ORDER_ID_REAL>
```

### Opción 2: Script Python

Si tienes Python y `requests` instalado:

```bash
cd backend
python scripts/probar_webhook_ml.py
```

O con un ID de orden específico:

```bash
python scripts/probar_webhook_ml.py <ORDER_ID>
```

### Opción 3: Usando curl Manualmente

#### Probar GET (Validación)

```bash
curl -X GET "https://bonito-amor-backend.onrender.com/api/tiendas/e265d339-39ec-4ec5-a73c-d5a31904d29a/mercadolibre/webhook/"
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "message": "Webhook configurado correctamente",
  "tienda_id": "e265d339-39ec-4ec5-a73c-d5a31904d29a"
}
```

#### Probar POST (Notificación)

```bash
curl -X POST "https://bonito-amor-backend.onrender.com/api/tiendas/e265d339-39ec-4ec5-a73c-d5a31904d29a/mercadolibre/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }'
```

**Respuesta esperada:**
```json
{
  "status": "success",
  "message": "Orden procesada correctamente",
  "order_id": "123456789"
}
```

O si la orden no existe o no está en estado válido:
```json
{
  "status": "skipped",
  "message": "La orden no está en un estado procesable",
  "order_id": "123456789"
}
```

## 📊 Qué Esperar

### GET Request

El endpoint GET es usado por Mercado Libre para validar que el webhook existe y está configurado correctamente. Debe responder con:

- **Status Code**: `200 OK`
- **Body**: JSON con `status: "ok"` y `message: "Webhook configurado correctamente"`

### POST Request

El endpoint POST recibe notificaciones reales de Mercado Libre cuando ocurre un evento relacionado con órdenes. La estructura típica es:

```json
{
  "resource": "/orders/123456789",
  "topic": "orders"
}
```

El webhook procesará la notificación y:

1. **Extraerá el ID de la orden** del campo `resource`
2. **Obtendrá la información de la orden** desde la API de Mercado Libre
3. **Verificará el estado de la orden** (solo procesa órdenes en estados: `confirmed`, `payment_required`, `payment_in_process`, `paid`)
4. **Creará una venta** en el sistema con el método de pago "Mercado Libre"
5. **Calculará el arancel** según la categoría del producto
6. **Actualizará el stock** de los productos vendidos

## 🔍 Verificar los Resultados

### 1. Ver los Logs del Servidor

En Render:
1. Ve a tu dashboard de Render
2. Selecciona tu servicio `bonito-amor-backend`
3. Ve a la pestaña **"Logs"**
4. Busca mensajes que empiecen con `INFO: Notificación recibida de ML`

### 2. Verificar que se Creó la Venta

Puedes verificar en el Django Admin o en la API:

```bash
# Obtener las últimas ventas
curl -X GET "https://bonito-amor-backend.onrender.com/api/ventas/" \
  -H "Authorization: Bearer <TU_TOKEN>"
```

### 3. Verificar que se Actualizó el Stock

Los productos vendidos deberían tener su stock actualizado automáticamente.

## 🐛 Troubleshooting

### Error: "404 Not Found"

**Problema**: La URL del webhook es incorrecta o el ID de tienda no existe.

**Solución**:
- Verifica que la URL sea exactamente: `/api/tiendas/{TIENDA_ID}/mercadolibre/webhook/`
- Verifica que el ID de tienda sea correcto

### Error: "Tienda no encontrada"

**Problema**: El ID de tienda en la URL no existe en la base de datos.

**Solución**:
- Verifica que el ID de tienda sea correcto
- Verifica que la tienda exista en la base de datos

### Error: "Los campos de Mercado Libre no están disponibles"

**Problema**: Las migraciones no se han aplicado en producción.

**Solución**:
- Ejecuta las migraciones en producción: `python manage.py migrate`

### Error: "La tienda no está configurada para Mercado Libre"

**Problema**: La tienda no tiene configurado `plataforma_ecommerce = 'MERCADO_LIBRE'`.

**Solución**:
- Configura la tienda en el Django Admin o a través de la API

### La orden no se procesa

**Posibles causas**:
1. **La orden no existe en Mercado Libre**: El ID de orden que estás probando no existe
2. **La orden no está en un estado válido**: Solo se procesan órdenes en estados `confirmed`, `payment_required`, `payment_in_process`, `paid`
3. **El producto no está sincronizado**: El producto en la orden no tiene `ml_item_id` configurado en el sistema
4. **Token de acceso inválido**: El token de Mercado Libre puede haber expirado

**Solución**:
- Usa un ID de orden real de tu cuenta de Mercado Libre
- Verifica que la orden esté en un estado válido
- Verifica que los productos estén sincronizados con Mercado Libre
- Renueva el token de acceso si es necesario

## 📝 Notas Importantes

1. **Solo se procesan órdenes válidas**: El webhook solo procesa órdenes que estén en estados específicos (`confirmed`, `payment_required`, `payment_in_process`, `paid`)

2. **El webhook siempre responde 200 OK**: Incluso si hay errores, el webhook responde con `200 OK` para evitar que Mercado Libre reenvíe la notificación. Los errores se registran en los logs.

3. **Los productos deben estar sincronizados**: Para que una orden se procese correctamente, los productos en la orden deben tener `ml_item_id` configurado en el sistema.

4. **El arancel se calcula automáticamente**: Si tienes configurado un `ArancelMercadoLibre` para la categoría del producto, se calculará y descontará automáticamente de las métricas.

## 🔗 Referencias

- [Documentación de Webhooks de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/notificaciones-y-webhooks)
- [API de Órdenes de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/ordenes-y-envios)
