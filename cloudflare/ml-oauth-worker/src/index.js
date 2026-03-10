/**
 * Cloudflare Worker - Proxy OAuth para Mercado Libre
 *
 * Evita el 403 de CloudFront cuando el backend (Render) hace el exchange desde
 * una IP de datacenter. El Worker ejecuta en la red de Cloudflare.
 *
 * Variables de entorno (secrets en wrangler):
 * - ML_OAUTH_BACKEND_URL: https://totalstock.onrender.com (o bonito-amor-backend.onrender.com)
 * - ML_OAUTH_WORKER_SECRET: mismo valor que en el backend
 *
 * En ML DevCenter, agregar como Redirect URI:
 *   https://TU-WORKER.workers.dev/callback
 */

const TOKEN_URL = 'https://api.mercadolibre.com/oauth/token';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/callback' && request.method === 'GET') {
      return handleCallback(request, env);
    }
    return new Response('ML OAuth Worker - use /callback as redirect_uri', { status: 404 });
  },
};

async function handleCallback(request, env) {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');

  if (!code || !state) {
    return htmlResponse(400, 'Error: faltan code o state en la URL');
  }

  const backend = (env.ML_OAUTH_BACKEND_URL || '').replace(/\/$/, '');
  const secret = env.ML_OAUTH_WORKER_SECRET;

  if (!backend || !secret) {
    return htmlResponse(500, 'Worker no configurado: faltan ML_OAUTH_BACKEND_URL o ML_OAUTH_WORKER_SECRET');
  }

  // 1. Obtener credenciales del backend
  const credRes = await fetch(`${backend}/api/internal/ml-oauth-credentials/?state=${encodeURIComponent(state)}`, {
    headers: { 'X-ML-OAuth-Proxy-Key': secret },
  });

  if (!credRes.ok) {
    const err = await credRes.text();
    return htmlResponse(credRes.status, `Error al obtener credenciales: ${err}`);
  }

  const cred = await credRes.json();
  const { client_id, client_secret, redirect_uri } = cred;

  // redirect_uri debe ser esta misma URL (Worker callback)
  const myRedirectUri = `${url.origin}${url.pathname}`;
  const finalRedirectUri = redirect_uri || myRedirectUri;

  // 2. Intercambiar code por tokens (desde IP de Cloudflare)
  const tokenBody = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id,
    client_secret,
    code,
    redirect_uri: finalRedirectUri,
  });

  const tokenRes = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Accept': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    },
    body: tokenBody.toString(),
  });

  if (!tokenRes.ok) {
    const errText = await tokenRes.text();
    return htmlResponse(400, `Error de Mercado Libre (${tokenRes.status}): ${errText.slice(0, 300)}`);
  }

  const tokenData = await tokenRes.json();

  // 3. Enviar tokens al backend
  const saveRes = await fetch(`${backend}/api/internal/ml-oauth-save-tokens/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-ML-OAuth-Proxy-Key': secret,
    },
    body: JSON.stringify({
      state,
      access_token: tokenData.access_token,
      refresh_token: tokenData.refresh_token,
      user_id: tokenData.user_id,
      expires_in: tokenData.expires_in || 21600,
    }),
  });

  if (!saveRes.ok) {
    const err = await saveRes.text();
    return htmlResponse(500, `Error al guardar tokens: ${err}`);
  }

  const saveData = await saveRes.json();

  // 4. Mostrar éxito y postMessage al opener
  return htmlResponse(200, null, {
    tienda_id: saveData.tienda_id,
    nombre: saveData.nombre || 'Tienda',
    success: true,
  });
}

function htmlResponse(status, errorMsg, successData = null) {
  const isSuccess = status === 200 && successData;

  const html = isSuccess
    ? `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Autenticación exitosa</title></head><body>
<h1>✅ Autenticación exitosa</h1>
<p>La integración con Mercado Libre se configuró correctamente para la tienda: ${successData.nombre}</p>
<p>Puedes cerrar esta ventana.</p>
<script>
if (window.opener) {
  window.opener.postMessage({
    type: "ML_OAUTH_SUCCESS",
    tienda_id: "${successData.tienda_id}",
    message: "Autenticación exitosa"
  }, "*");
  setTimeout(function(){ window.close(); }, 2000);
} else {
  setTimeout(function(){ window.close(); }, 3000);
}
</script></body></html>`
    : `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Error OAuth</title></head><body>
<h1>❌ Error en autenticación</h1>
<p>${errorMsg || 'Error desconocido'}</p>
<script>setTimeout(function(){ window.close(); }, 5000);</script></body></html>`;

  return new Response(html, {
    status,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}
