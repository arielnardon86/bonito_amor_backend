# Guía Rápida - Probar Integración con Mercado Libre

## Paso 1: Verificar que el servidor esté corriendo

El servidor debe estar corriendo en `http://localhost:8000` (o tu URL de staging)

## Paso 2: Obtener Token de Autenticación

Necesitas un token JWT para autenticarte en la API:

```bash
curl -X POST http://localhost:8000/api/token/ \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "TU_USUARIO_ADMIN",
    "password": "TU_PASSWORD"
  }'
```

Respuesta esperada:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

Guarda el `access` token para usarlo en los siguientes pasos.

## Paso 3: Verificar Estado de la Integración

Verifica que la tienda esté configurada correctamente:

```bash
# Reemplaza TIENDA_ID con el ID de tu tienda (ejemplo: 31551735-b173-4831-9c4a-3b8d5196dbd5)
# Reemplaza TU_TOKEN con el token obtenido en el paso anterior

curl http://localhost:8000/api/tiendas/TIENDA_ID/mercadolibre/status/ \
  -H 'Authorization: Bearer TU_TOKEN'
```

Deberías ver:
```json
{
  "plataforma_ecommerce": "MERCADO_LIBRE",
  "ml_sync_habilitado": true,
  "ml_app_id": "4287131814924103",
  "authenticated": false,
  "ml_modo_test": true
}
```

## Paso 4: Obtener URL de Autorización OAuth

```bash
curl 'http://localhost:8000/api/tiendas/TIENDA_ID/mercadolibre/auth-url/?redirect_uri=https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/' \
  -H 'Authorization: Bearer TU_TOKEN'
```

Respuesta esperada:
```json
{
  "auth_url": "https://auth.mercadolibre.com.ar/authorization?response_type=code&client_id=4287131814924103&redirect_uri=https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/",
  "redirect_uri": "https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/",
  "app_id": "4287131814924103"
}
```

## Paso 5: Autorizar la Aplicación

1. **Copia la `auth_url`** de la respuesta anterior

2. **Abre esa URL en tu navegador**

3. **Inicia sesión** con tu cuenta de Mercado Libre

4. **Autoriza la aplicación** haciendo clic en "Autorizar"

5. **Serás redirigido** a:
   ```
   https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/?code=TG-XXXXX&state=...
   ```

6. **Copia el código** de la URL (el valor después de `code=`, ejemplo: `TG-XXXXX`)

## Paso 6: Intercambiar Código por Tokens

```bash
curl -X POST http://localhost:8000/api/tiendas/TIENDA_ID/mercadolibre/callback/ \
  -H 'Authorization: Bearer TU_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "code": "TG-XXXXX",
    "redirect_uri": "https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/"
  }'
```

⚠️ **IMPORTANTE**: El `redirect_uri` debe ser **exactamente igual** al usado en el Paso 4 y al configurado en Mercado Libre Developers.

Respuesta esperada:
```json
{
  "message": "Autenticación exitosa con Mercado Libre",
  "user_id": "123456789",
  "access_token": "APP_USR-XXXXX..."
}
```

## Paso 7: Verificar que la Autenticación Funcionó

Verifica nuevamente el estado:

```bash
curl http://localhost:8000/api/tiendas/TIENDA_ID/mercadolibre/status/ \
  -H 'Authorization: Bearer TU_TOKEN'
```

Ahora deberías ver:
```json
{
  "plataforma_ecommerce": "MERCADO_LIBRE",
  "authenticated": true,
  "user_id": "123456789",
  "token_expires_at": "2026-01-10T22:00:00Z",
  "token_expired": false,
  ...
}
```

## Siguiente Paso: Probar Sincronización

Una vez autenticado, puedes probar sincronizar productos:

```bash
curl -X POST http://localhost:8000/api/tiendas/TIENDA_ID/mercadolibre/sync-products/ \
  -H 'Authorization: Bearer TU_TOKEN'
```

## Troubleshooting

### Error: "App ID no configurado"
- Ve al admin de Django y configura `ml_app_id` en la tienda

### Error: "Client Secret no configurado"
- Ve al admin y configura `ml_client_secret` en la tienda

### Error: "redirect_uri mismatch"
- Asegúrate de usar exactamente la misma URI en todos los pasos
- Verifica que la URI en Mercado Libre Developers coincida exactamente

### Error: "Token expired"
- Los tokens de Mercado Libre expiran después de 6 horas
- El sistema debería renovarlos automáticamente
- Si falla, puedes completar el flujo OAuth nuevamente
