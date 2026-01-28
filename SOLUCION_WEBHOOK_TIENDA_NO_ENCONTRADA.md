# 🔧 Solución: Error "No Tienda matches the given query" en Webhook

## Problema

Al verificar el webhook, recibes:
```json
{
    "status": "error",
    "message": "Error: No Tienda matches the given query."
}
```

## Causa

El ID de tienda `31551735-b173-4831-9c4a-3b8d5196dbd5` **no existe en la base de datos de producción**.

## Solución Implementada

He mejorado el manejo de errores para que:
1. ✅ Siempre retorne `200 OK` (para que ML no reenvíe notificaciones)
2. ✅ Proporcione mensajes de error más claros
3. ✅ Obtenga la tienda directamente por ID

## Verificar el ID Correcto de tu Tienda

### Opción 1: Desde la API

```bash
curl https://bonito-amor-backend.onrender.com/api/tiendas/
```

Esto te mostrará todas las tiendas con sus IDs.

### Opción 2: Desde el Admin de Django

1. Ve a `https://bonito-amor-backend.onrender.com/admin/inventario/tienda/`
2. Haz clic en tu tienda
3. El ID aparece en la URL: `/admin/inventario/tienda/[ID]/change/`

### Opción 3: Desde el Frontend

Abre la consola del navegador y ejecuta:
```javascript
fetch('/api/tiendas/', {
  headers: {
    'Authorization': 'Bearer TU_TOKEN'
  }
})
.then(r => r.json())
.then(data => console.log('Tiendas:', data))
```

## Actualizar la URL del Webhook

Una vez que tengas el ID correcto, actualiza la URL del webhook en Mercado Libre:

```
https://bonito-amor-backend.onrender.com/api/tiendas/[ID-CORRECTO]/mercadolibre/webhook/
```

## Verificar que Funciona

Después de actualizar con el ID correcto, deberías ver:

```json
{
    "status": "ok",
    "message": "Webhook configurado correctamente",
    "tienda_id": "[ID-CORRECTO]"
}
```

## Nota Importante

El webhook ahora siempre retorna `200 OK` incluso si hay errores, para evitar que Mercado Libre reenvíe notificaciones. Los errores se registran en los logs del servidor.
