"""
Servicio de integración con Tienda Nube / Nuvemshop.

Flujo OAuth:
  1. Usuario ingresa app_id + client_secret en el panel.
  2. Frontend abre popup con la URL de autorización.
  3. Tienda Nube redirige al callback con ?code=...
  4. Backend intercambia code → access_token + store_id (user_id).
  5. Token no expira → no hay refresh.

Webhook:
  - Se registra event "order/paid" via POST /webhooks.
  - Tienda Nube envía POST con header x-linkedstore-hmac-sha256.
  - Se verifica la firma con HMAC-SHA256(client_secret, body).
"""
import hashlib
import hmac
import logging
import requests

logger = logging.getLogger(__name__)

TN_API_BASE  = "https://api.tiendanube.com/2025-03"
TN_AUTH_URL  = "https://www.tiendanube.com/apps/{app_id}/authorize"
TN_TOKEN_URL = "https://www.tiendanube.com/apps/authorize/token"

USER_AGENT = "TotalStock (soporte@totalstock.com.ar)"


class TiendaNubeService:
    """Wrapper sobre la API de Tienda Nube para una tienda ya autenticada."""

    def __init__(self, tienda):
        self.tienda        = tienda
        self.access_token  = tienda.tn_access_token
        self.store_id      = tienda.tn_store_id
        self.app_id        = tienda.tn_app_id
        self.client_secret = tienda.tn_client_secret

    # ── Helpers de petición ──────────────────────────────────────────────────

    def _headers(self):
        return {
            "Authentication": f"bearer {self.access_token}",
            "Content-Type":   "application/json; charset=utf-8",
            "User-Agent":     USER_AGENT,
        }

    def _url(self, path):
        return f"{TN_API_BASE}/{self.store_id}/{path.lstrip('/')}"

    def _get(self, path, params=None):
        resp = requests.get(self._url(path), headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path, data):
        resp = requests.post(self._url(path), headers=self._headers(), json=data, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path):
        resp = requests.delete(self._url(path), headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.status_code

    # ── OAuth ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_authorization_url(app_id):
        """Devuelve la URL para iniciar el flujo OAuth."""
        return TN_AUTH_URL.format(app_id=app_id)

    @staticmethod
    def exchange_code_for_token(app_id, client_secret, code):
        """
        Intercambia el código de autorización por un access_token.
        Devuelve (access_token, store_id) o lanza excepción.
        """
        resp = requests.post(
            TN_TOKEN_URL,
            data={
                "client_id":     app_id,
                "client_secret": client_secret,
                "code":          code,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        store_id     = str(data.get("user_id", ""))
        if not access_token or not store_id:
            raise ValueError(f"Respuesta inesperada de Tienda Nube: {data}")
        return access_token, store_id

    # ── Órdenes ──────────────────────────────────────────────────────────────

    def get_order(self, order_id):
        """Obtiene los detalles de una orden."""
        return self._get(f"orders/{order_id}")

    # ── Stock ────────────────────────────────────────────────────────────────

    def update_variant_stock(self, variant_id, quantity):
        """Actualiza el stock de una variante."""
        resp = requests.put(
            self._url(f"variants/{variant_id}"),
            headers=self._headers(),
            json={"stock": quantity},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Webhooks ─────────────────────────────────────────────────────────────

    def register_webhook(self, event, url):
        """
        Registra un webhook en Tienda Nube.
        Devuelve el ID del webhook creado.
        """
        data = self._post("webhooks", {"event": event, "url": url})
        return str(data.get("id"))

    def delete_webhook(self, webhook_id):
        """Elimina un webhook registrado."""
        try:
            self._delete(f"webhooks/{webhook_id}")
        except Exception as e:
            logger.warning("No se pudo eliminar webhook %s: %s", webhook_id, e)

    def list_webhooks(self):
        return self._get("webhooks")

    @staticmethod
    def verify_signature(client_secret, raw_body, signature_header):
        """
        Verifica la firma HMAC-SHA256 enviada por Tienda Nube.
        Header: x-linkedstore-hmac-sha256
        """
        if not signature_header:
            return False
        expected = hmac.new(
            client_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header.lower())
