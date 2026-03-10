# ML OAuth Proxy - Cloudflare Worker

Proxy para el exchange de tokens OAuth de Mercado Libre. Evita el 403 de CloudFront cuando el backend (Render, Railway, etc.) hace la petición desde una IP de datacenter bloqueada.

## Requisitos

- Cuenta en [Cloudflare](https://cloudflare.com) (plan gratuito alcanza)
- [Node.js](https://nodejs.org) y npm

## Despliegue

```bash
cd cloudflare/ml-oauth-worker
npm install
npx wrangler deploy
```

Anotá la URL que te da (ej. `https://ml-oauth-proxy.xxx.workers.dev`).

## Secrets

```bash
# URL base del backend (sin / al final)
npx wrangler secret put ML_OAUTH_BACKEND_URL
# Ej: https://totalstock.onrender.com

# Clave compartida con el backend (mismo valor que ML_OAUTH_WORKER_SECRET)
npx wrangler secret put ML_OAUTH_WORKER_SECRET
# Ej: openssl rand -hex 32
```

## Configuración en el backend (Render)

Variables de entorno:

- `ML_OAUTH_WORKER_URL` = `https://ml-oauth-proxy.xxx.workers.dev/callback`
- `ML_OAUTH_WORKER_SECRET` = (la misma clave que en el Worker)

## Mercado Libre DevCenter

Agregar como Redirect URI:

```
https://ml-oauth-proxy.xxx.workers.dev/callback
```

## Flujo

1. Usuario hace clic en "Conectar" → backend devuelve auth_url con redirect_uri = Worker/callback
2. ML redirige al usuario al Worker con code y state
3. Worker pide credenciales al backend
4. Worker hace POST a api.mercadolibre.com/oauth/token (desde IP Cloudflare)
5. Worker envía tokens al backend
6. Worker muestra HTML de éxito y cierra ventana (postMessage al opener)
