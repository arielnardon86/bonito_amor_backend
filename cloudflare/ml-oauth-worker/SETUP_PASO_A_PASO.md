# Setup Worker ML OAuth - Paso a paso

## Paso 1: Cuenta Cloudflare

Si no tenés cuenta: https://dash.cloudflare.com/sign-up (plan gratuito alcanza).

---

## Paso 2: Instalar Wrangler e iniciar sesión

En PowerShell (o terminal):

```powershell
cd "c:\Users\Usuario\Documents\Proyectos\Total_Stock\backend\bonito_amor_backend-main\cloudflare\ml-oauth-worker"
npm install
npx wrangler login
```

Se abrirá el navegador para iniciar sesión en Cloudflare.

---

## Paso 3: Desplegar el Worker

```powershell
npx wrangler deploy
```

Al terminar, wrangler mostrará la URL, algo como:
```
Published ml-oauth-proxy (1.23 sec)
  https://ml-oauth-proxy.TU-USUARIO.workers.dev
```

**Anotá esa URL.** La callback será: `https://ml-oauth-proxy.TU-USUARIO.workers.dev/callback`

---

## Paso 4: Generar la clave secreta

En PowerShell:

```powershell
# Generar clave aleatoria (si tenés OpenSSL)
openssl rand -hex 32
```

O usá cualquier string largo y aleatorio (ej. 64 caracteres). **Guardalo**, lo vas a usar dos veces.

---

## Paso 5: Configurar secrets del Worker

```powershell
npx wrangler secret put ML_OAUTH_BACKEND_URL
```
Cuando pregunte, ingresá (sin / final): `https://bonito-amor-backend.onrender.com`

```powershell
npx wrangler secret put ML_OAUTH_WORKER_SECRET
```
Ingresá la **misma clave** que generaste antes.

---

## Paso 6: Variables en Render

En el dashboard de Render → tu servicio backend → Environment:

Agregar:

| Key | Value |
|-----|-------|
| `ML_OAUTH_WORKER_URL` | `https://ml-oauth-proxy.TU-USUARIO.workers.dev/callback` |
| `ML_OAUTH_WORKER_SECRET` | La misma clave que pusiste en el Worker |

*(Reemplazá TU-USUARIO por lo que te dio wrangler)*

---

## Paso 7: Mercado Libre DevCenter

1. Ir a https://applications.mercadolibre.com.ar (o Developers → Mis aplicaciones)
2. Abrir tu aplicación (High Duo)
3. En **Redirect URIs**, **agregar** (no reemplazar, agregar una nueva):
   ```
   https://ml-oauth-proxy.TU-USUARIO.workers.dev/callback
   ```
4. Guardar

---

## Paso 8: Deploy del backend

En Render, hacer **Manual Deploy** (o push si tenés auto-deploy) para que tome las nuevas variables.

---

## Paso 9: Probar

1. En tu app Total Stock, ir a Configuración > Mercado Libre
2. Clic en "Conectar con Mercado Libre"
3. Autorizar en la ventana de ML
4. Debería mostrar "Autenticación exitosa"

Si falla, revisar los logs en Render y en Cloudflare (Workers → ml-oauth-proxy → Logs).
