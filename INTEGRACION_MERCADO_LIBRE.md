# Integración con Mercado Libre - Guía de Implementación

Esta guía explica cómo configurar y usar la integración con Mercado Libre en el sistema Total Stock.

## 📋 Resumen Rápido - Crear Aplicación en Mercado Libre

### Valores para el Formulario de Creación

| Campo | Valor Recomendado |
|-------|-------------------|
| **Nombre** | `Total Stock - Integración ML` o `Bonito Amor - ML` |
| **Descripción** | `Sistema de gestión de inventario con integración a Mercado Libre para sincronización de productos y stock` |
| **Redirect URIs** | **Para STAGING:**<br>`http://localhost:8000/api/tiendas/mercadolibre/callback/`<br>(o usa ngrok si necesitas HTTPS)<br><br>**Para PRODUCCIÓN:**<br>`https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/` |
| **Permisos** | ✅ `offline_access` (IMPORTANTE - para refresh token)<br>✅ `read`<br>✅ `write` |

### Después de Crear la Aplicación

Guardar estos valores:
- **App ID** (Client ID): Número numérico, ejemplo: `1234567890123456`
- **Client Secret**: Cadena alfanumérica larga (solo se muestra una vez)

⚠️ **IMPORTANTE**: El Client Secret solo se muestra una vez. Guárdalo en un lugar seguro.

### Configurar en Django Admin

1. Ve a `/admin/inventario/tienda/{id}/change/`
2. Configura:
   - `Plataforma E-commerce`: **Mercado Libre**
   - `ml_app_id`: Tu App ID
   - `ml_client_secret`: Tu Client Secret
   - `ml_modo_test`: ✅ **Marcado** (True) para staging

---

## Estado de la Implementación

✅ **Modelo Tienda extendido** - Campos para configuración de Mercado Libre
✅ **Servicio de integración** - `MercadoLibreService` para interactuar con la API
✅ **Migración creada** - `0014_add_mercadolibre_fields.py`
✅ **Endpoints API** - Gestión de autenticación OAuth y sincronización
⏳ **Interfaz Frontend** - Pendiente de implementación
⏳ **Sincronización automática** - Pendiente de implementación completa

## Requisitos Previos

1. **Credenciales de Mercado Libre**:
   - Necesitas crear una aplicación en [Mercado Libre Developers](https://developers.mercadolibre.com.ar/)
   - Obtener `App ID` (Client ID) y `Client Secret`
   - Configurar `Redirect URI` en la aplicación

2. **Ambiente de Staging**:
   - PostgreSQL configurado y corriendo
   - Base de datos de staging creada
   - Variables de entorno configuradas

## Crear Aplicación en Mercado Libre Developers

### Paso 1: Registrarse en Mercado Libre Developers

1. Ve a [https://developers.mercadolibre.com.ar/](https://developers.mercadolibre.com.ar/)
2. Haz clic en **"Ingresar"** e inicia sesión con tu cuenta de Mercado Libre
3. Si no tienes cuenta, crea una en Mercado Libre primero

### Paso 2: Crear Nueva Aplicación

1. Una vez dentro, haz clic en **"Crear nueva aplicación"** o **"Crear aplicación"**
2. Completa el formulario con los siguientes datos:

#### Campos del Formulario:

**Nombre de la aplicación:**
```
Total Stock - Integración ML
```
o
```
Bonito Amor - Integración Mercado Libre
```

**Descripción:**
```
Sistema de gestión de inventario y punto de venta con integración a Mercado Libre para sincronización de productos y stock.
```

**Redirect URIs:**

⚠️ **IMPORTANTE: Mercado Libre requiere HTTPS y NO acepta localhost**

Mercado Libre **solo acepta Redirect URIs con HTTPS**. No puedes usar `http://localhost` directamente.

**✅ Solución Recomendada: Usar siempre la URI de Producción**

Aunque estés probando en staging, usa la URI de producción en Mercado Libre Developers:

```
https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/
```

o tu dominio de producción:
```
https://tu-dominio-produccion.com/api/tiendas/mercadolibre/callback/
```

**¿Por qué funciona esto?**
- ✅ La URI de producción está siempre disponible (funciona tanto para staging como producción)
- ✅ El campo `ml_modo_test = True` en la tienda controla si usa el ambiente de testing de Mercado Libre
- ✅ Puedes probar en staging localmente pero el callback se recibirá en producción (donde está tu backend)

**Alternativa (solo si realmente necesitas un túnel HTTPS para desarrollo):**

Si necesitas un túnel HTTPS temporal para desarrollo local, puedes usar:
- [ngrok](https://ngrok.com/) con cuenta gratuita: `ngrok http 8000` → usa la URL HTTPS que te da
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [localtunnel](https://localtunnel.github.io/www/) (algunos planes ofrecen HTTPS)

Pero **no es necesario** - usar la URI de producción es más simple y funciona perfectamente.

**Múltiples Redirect URIs (Opcional):**
Puedes agregar múltiples URIs separadas por saltos de línea si tienes diferentes ambientes:
```
https://abc123.ngrok.io/api/tiendas/mercadolibre/callback/
https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/
```

**Recomendación:**
Para simplificar, usa **solo la URI de producción** en Mercado Libre Developers. Funcionará tanto para staging como para producción.

**Nota importante sobre Redirect URIs:**
- ✅ **Debe usar HTTPS** (Mercado Libre no acepta HTTP)
- ✅ El URI debe ser **exactamente igual** al que uses en el flujo OAuth
- ✅ Debe ser accesible desde internet (no puedes usar `http://localhost` directamente)
- ✅ El path debe terminar en `/api/tiendas/mercadolibre/callback/`
- ℹ️ El campo `ml_modo_test` en la tienda controla el ambiente de ML (testing vs producción), no la URI

**Otros campos (si los hay):**

- **Tipo de aplicación**: Selecciona "Marketplace" o "E-commerce"
- **Permisos necesarios**: Selecciona los permisos que necesites:
  - `offline_access` (para obtener refresh token) ✅ **RECOMENDADO**
  - `read` (lectura de datos)
  - `write` (escritura de datos)
  - `public` (acceso a datos públicos)

3. Acepta los términos y condiciones
4. Haz clic en **"Crear aplicación"** o **"Guardar"**

### Paso 3: Obtener Credenciales

Una vez creada la aplicación, verás:

- **App ID** (también llamado Client ID): Es un número, ejemplo: `1234567890123456`
- **Client Secret** (también llamado Secret Key): Una cadena alfanumérica larga

⚠️ **IMPORTANTE**: 
- Guarda estas credenciales de forma segura
- **NO compartas** el Client Secret públicamente
- El Client Secret solo se muestra una vez al crear la aplicación
- Si lo pierdes, deberás generar uno nuevo desde el panel de Mercado Libre

### Paso 4: Configurar la Aplicación para Testing

Si vas a probar en staging:

1. En el panel de tu aplicación, busca la opción **"Ambiente de pruebas"** o **"Sandbox"**
2. Activa el modo de pruebas
3. En algunos casos, puede que necesites crear una aplicación separada para testing

**Nota**: En Mercado Libre, el ambiente de testing usa el mismo dominio pero con datos de prueba. El flag `ml_modo_test` en nuestro código controla qué endpoints usar.

## Configuración en Staging

### 1. Aplicar Migración

```bash
cd backend
DJANGO_ENVIRONMENT=staging python manage.py migrate inventario
```

O usando el script:

```bash
./scripts/run_staging.sh migrate inventario
```

### 2. Configurar Tienda para Mercado Libre

Después de obtener las credenciales de Mercado Libre, configúralas en tu tienda.

#### Opción A: Mediante Django Admin

1. Accede al admin de Django en staging:
   ```
   http://localhost:8000/admin/
   ```
   o tu URL de staging

2. Inicia sesión como superusuario

3. Ve a **"Tiendas"** → Selecciona la tienda que deseas configurar

4. Configura los siguientes campos en la sección **"Configuración E-commerce - Mercado Libre"**:
   - `Plataforma E-commerce`: Selecciona **"Mercado Libre"** del dropdown
   - `ml_app_id`: Pega tu **App ID** (Client ID) obtenido de Mercado Libre
     - Ejemplo: `1234567890123456`
   - `ml_client_secret`: Pega tu **Client Secret** obtenido de Mercado Libre
     - Ejemplo: `ABC123XYZ789...` (cadena larga alfanumérica)
   - `ml_modo_test`: ✅ **Marca esta casilla** (True) para staging/testing
   - `ml_sync_habilitado`: Puedes dejarlo sin marcar por ahora (lo activarás después)
   - Los demás campos de sincronización puedes dejarlos con valores por defecto

5. Haz clic en **"Guardar"** o **"Save"**

**Nota importante**: 
- El `ml_client_secret` debe ser exactamente como lo obtuviste (sin espacios adicionales)
- El `ml_app_id` es numérico, sin espacios ni guiones

#### Opción B: Mediante API

```bash
# Actualizar tienda con credenciales ML
PATCH /api/tiendas/{tienda_id}/
Headers: Authorization: Bearer {token}
Body: {
  "plataforma_ecommerce": "MERCADO_LIBRE",
  "ml_app_id": "TU_APP_ID",
  "ml_client_secret": "TU_CLIENT_SECRET",
  "ml_modo_test": true
}
```

### 3. Flujo de Autenticación OAuth

#### Paso 1: Obtener URL de Autorización

⚠️ **IMPORTANTE**: Usa la misma Redirect URI que configuraste en Mercado Libre Developers (debe ser HTTPS).

```bash
GE/aT pi/tiendas/{tienda_id}/mercadolibre/auth-url/?redirect_uri=https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/
Headers: Authorization: Bearer {token}
```

**Nota**: Aunque estés en staging, usa la URI de producción aquí también. Debe coincidir exactamente con la configurada en Mercado Libre Developers.

Respuesta:
```json
{
  "auth_url": "https://auth.mercadolibre.com.ar/authorization?...",
  "redirect_uri": "https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/",
  "app_id": "TU_APP_ID"
}
```

#### Paso 2: Redirigir al Usuario

Redirige al usuario a la `auth_url` obtenida. El usuario autorizará la aplicación y será redirigido a tu `redirect_uri` con un código:

```
https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/?code=TG-XXXXX
```

**Nota**: Asegúrate de que tu backend en producción esté accesible para recibir este callback.

#### Paso 3: Intercambiar Código por Token

Usa el mismo `redirect_uri` que usaste en el Paso 1:

```bash
POST /api/tiendas/{tienda_id}/mercadolibre/callback/
Headers: Authorization: Bearer {token}
Body: {
  "code": "TG-XXXXX",
  "redirect_uri": "https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/"
}
```

⚠️ **CRÍTICO**: El `redirect_uri` debe ser **exactamente igual** al usado en el Paso 1 y al configurado en Mercado Libre Developers.

Respuesta:
```json
{
  "message": "Autenticación exitosa con Mercado Libre",
  "user_id": "123456789",
  "access_token": "APP_USR-XXXXX..."
}
```

### 4. Verificar Estado de la Integración

```bash
GET /api/tiendas/{tienda_id}/mercadolibre/status/
Headers: Authorization: Bearer {token}
```

Respuesta:
```json
{
  "plataforma_ecommerce": "MERCADO_LIBRE",
  "ml_sync_habilitado": false,
  "ml_sincronizar_stock": true,
  "ml_sincronizar_precios": true,
  "ml_sincronizar_productos": true,
  "ml_modo_test": true,
  "authenticated": true,
  "user_id": "123456789",
  "token_expires_at": "2026-01-10T22:00:00Z",
  "app_id": "TU_APP_ID",
  "token_expired": false
}
```

### 5. Sincronización de Productos (Manual)

```bash
POST /api/tiendas/{tienda_id}/mercadolibre/sync-products/
Headers: Authorization: Bearer {token}
```

**Nota**: La sincronización completa aún está en desarrollo. Por ahora solo registra los intentos.

## Campos del Modelo Tienda

### Configuración Básica

- `plataforma_ecommerce`: Plataforma seleccionada ('NINGUNA', 'MERCADO_LIBRE', 'TIENDA_NUBE')
- `ml_app_id`: Application ID de Mercado Libre
- `ml_client_secret`: Client Secret de Mercado Libre
- `ml_modo_test`: True para ambiente de testing/sandbox

### Tokens OAuth (Se generan automáticamente)

- `ml_access_token`: Token de acceso (NO se expone en API)
- `ml_refresh_token`: Token de renovación (NO se expone en API)
- `ml_user_id`: ID del usuario/vendedor
- `ml_token_expires_at`: Fecha de expiración del token

### Configuración de Sincronización

- `ml_sync_habilitado`: Habilitar sincronización automática
- `ml_sincronizar_stock`: Sincronizar cambios de stock
- `ml_sincronizar_precios`: Sincronizar cambios de precios
- `ml_sincronizar_productos`: Sincronizar nuevos productos

## Seguridad

⚠️ **IMPORTANTE**: Los siguientes campos NO se exponen en la API por seguridad:
- `ml_access_token`
- `ml_refresh_token`
- `ml_client_secret`
- `certificado_afip`
- `clave_privada_afip`

## Solución de problemas: Error 403 en OAuth

Si al conectar con Mercado Libre recibís **403 Forbidden** en el callback OAuth (mensaje "Request blocked" de CloudFront), suele deberse a que CloudFront bloquea la IP de tu servidor (p. ej. Render, Railway).

### Solución recomendada: Cloudflare Worker (proxy OAuth)

Desplegando un Worker en Cloudflare, el exchange de tokens se hace desde la red de Cloudflare en lugar de Render, evitando el bloqueo.

#### 1. Desplegar el Worker

```bash
cd cloudflare/ml-oauth-worker
npm init -y  # si no existe package.json
npx wrangler deploy
```

#### 2. Configurar secrets

```bash
npx wrangler secret put ML_OAUTH_BACKEND_URL
# Ingresar: https://totalstock.onrender.com (o tu dominio backend)

npx wrangler secret put ML_OAUTH_WORKER_SECRET
# Ingresar: una clave aleatoria larga (ej. openssl rand -hex 32)
```

#### 3. Configurar en Render (o tu host)

Variables de entorno del backend:

- `ML_OAUTH_WORKER_URL` = `https://ml-oauth-proxy.TU-SUBDOMINIO.workers.dev/callback`
- `ML_OAUTH_WORKER_SECRET` = **la misma clave** que en el Worker

#### 4. Agregar Redirect URI en Mercado Libre DevCenter

En tu aplicación ML → Redirect URIs, agregar:

```
https://ml-oauth-proxy.TU-SUBDOMINIO.workers.dev/callback
```

(Reemplazá por la URL real que te da `wrangler deploy`)

#### 5. Re-deploy del backend

Con las variables configuradas, el auth-url usará automáticamente el Worker como redirect_uri.

---

### Otras opciones

1. **ML_OAUTH_PROXY** (proxy HTTP residencial):
   ```bash
   ML_OAUTH_PROXY=http://usuario:contraseña@proxy-ejemplo.com:8080
   ```

2. **Contactar a Mercado Libre** con el Request ID del error para pedir whitelist de IP

3. **Probar desde otra IP** (ngrok local) para confirmar que es bloqueo por IP

## Próximos Pasos

1. **Interfaz Frontend**: Crear componente React para configurar la integración
2. **Sincronización Automática**: Implementar sincronización bidireccional completa
3. **Webhooks**: Recibir actualizaciones de Mercado Libre en tiempo real
4. **Mapeo de Categorías**: Mapear categorías entre Total Stock y Mercado Libre
5. **Gestión de Órdenes**: Recibir órdenes de Mercado Libre y crear ventas automáticamente

## Testing

Para probar en staging:

1. Usa el ambiente de testing de Mercado Libre (`ml_modo_test: true`)
2. Crea una aplicación de prueba en [Mercado Libre Developers](https://developers.mercadolibre.com.ar/)
3. Configura las credenciales en la tienda de staging
4. Sigue el flujo OAuth descrito arriba
5. Verifica el estado de la integración

## Referencias

- [API de Mercado Libre](https://developers.mercadolibre.com.ar/es_ar/api-docs-es)
- [Autenticación OAuth 2.0](https://developers.mercadolibre.com.ar/es_ar/autenticacion-y-autorizacion)
- [Items API](https://developers.mercadolibre.com.ar/es_ar/items-y-busquedas)
