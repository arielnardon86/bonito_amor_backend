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

TN_API_BASE  = "https://api.tiendanube.com/v1"
TN_AUTH_URL  = "https://www.tiendanube.com/apps/{app_id}/authorize"
TN_TOKEN_URL = "https://www.tiendanube.com/apps/authorize/token"

USER_AGENT = "TotalStock (soporte@totalstock.com.ar)"


class TiendaNubeService:
    """Wrapper sobre la API de Tienda Nube para una tienda ya autenticada."""

    def __init__(self, tienda):
        from django.conf import settings
        self.tienda        = tienda
        self.access_token  = tienda.tn_access_token
        self.store_id      = tienda.tn_store_id
        self.app_id        = settings.TIENDANUBE_APP_ID
        self.client_secret = settings.TIENDANUBE_CLIENT_SECRET

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
                "grant_type":    "authorization_code",
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

    # ── Productos ────────────────────────────────────────────────────────────

    def get_products(self, page=1, per_page=25):
        """Devuelve una página de productos con sus variantes."""
        return self._get("products", params={"page": page, "per_page": per_page})

    def get_all_products(self):
        """Itera todas las páginas y devuelve la lista completa de productos."""
        all_products = []
        page = 1
        per_page = 25
        while True:
            try:
                batch = self.get_products(page=page, per_page=per_page)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    break
                raise
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return all_products

    def get_product(self, product_id):
        """Obtiene un producto con sus variantes por ID."""
        return self._get(f"products/{product_id}")

    def find_product_containing_variant(self, variant_id):
        """
        Recorre el catálogo buscando el producto padre de una variante.

        Fallback para cuando el ID pegado no es de producto sino de variante:
        en el panel de Tienda Nube el ID visible por SKU/fila suele ser el de
        la variante, distinto por cada talle/color, y no hay endpoint para
        pedirlo directo — hay que recorrer los productos y mirar adentro.
        Devuelve el dict del producto o None si no se encontró.
        """
        page = 1
        per_page = 50
        while True:
            try:
                batch = self.get_products(page=page, per_page=per_page)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    break
                raise
            if not batch:
                break
            for producto in batch:
                for v in producto.get("variants", []):
                    if str(v.get("id")) == str(variant_id):
                        return producto
            if len(batch) < per_page:
                break
            page += 1
        return None

    # ── Órdenes ──────────────────────────────────────────────────────────────

    def get_order(self, order_id):
        """Obtiene los detalles de una orden."""
        return self._get(f"orders/{order_id}")

    def _put(self, path, data):
        resp = requests.put(self._url(path), headers=self._headers(), json=data, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def create_product(self, nombre, precio, stock, sku=None):
        """
        Crea un producto en Tienda Nube con una sola variante.
        Devuelve (tn_product_id, tn_variant_id).
        """
        variant = {"price": str(precio), "stock": stock}
        if sku:
            variant["sku"] = sku
        data = {
            "name": {"es": nombre},
            "variants": [variant],
        }
        result = self._post("products", data)
        tn_product_id = str(result.get("id", ""))
        variants = result.get("variants", [])
        tn_variant_id = str(variants[0]["id"]) if variants else ""
        return tn_product_id, tn_variant_id

    def create_product_with_variants(self, nombre, variantes):
        """
        Crea un producto en TN con múltiples variantes.
        variantes: list of {precio, stock, sku (opt), talle (opt)}
        Devuelve (tn_product_id, tn_variants_list)

        TN requiere que si alguna variante usa 'values', el producto tenga
        'attributes' definidos con exactamente el mismo número de ejes.
        """
        has_talle = any(v.get('talle') for v in variantes)

        variants_data = []
        for v in variantes:
            variant = {"price": str(v['precio']), "stock": v.get('stock', 0)}
            if v.get('sku'):
                variant["sku"] = v['sku']
            if has_talle:
                # Siempre incluir values para TODOS los variantes cuando hay atributo
                variant["values"] = [{"es": str(v.get('talle') or '')}]
            variants_data.append(variant)

        data = {
            "name": {"es": nombre},
            "variants": variants_data,
        }
        if has_talle:
            # El eje de variante — TN lo llama "attribute"
            data["attributes"] = [{"es": "Variante"}]

        result = self._post("products", data)
        tn_product_id = str(result.get("id", ""))
        tn_variants = result.get("variants", [])
        return tn_product_id, tn_variants

    def add_variant(self, tn_product_id, precio, stock, sku=None, talle=None):
        """
        Agrega una variante a un producto TN existente.
        El producto ya debe tener 'attributes' definidos si se usan 'values'.
        Devuelve tn_variant_id.
        """
        variant = {"price": str(precio), "stock": stock}
        if sku:
            variant["sku"] = sku
        if talle:
            variant["values"] = [{"es": str(talle)}]
        result = self._post(f"products/{tn_product_id}/variants", variant)
        return str(result.get("id", ""))

    # ── Stock ────────────────────────────────────────────────────────────────

    def update_variant_stock(self, product_id, variant_id, quantity):
        """Actualiza el stock de una variante (anidada bajo su producto en la API de TN)."""
        resp = requests.put(
            self._url(f"products/{product_id}/variants/{variant_id}"),
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


def sincronizar_stock_producto(producto):
    """
    Empuja el stock actual de un producto hacia Tienda Nube, si está vinculado
    (tn_product_id/tn_variant_id) y la tienda tiene la integración conectada.
    Pensado para llamarse después de cualquier baja de stock local (venta,
    cambio/devolución) para que TN no quede desactualizado — la dirección
    TN → Total Stock ya se mantiene sola vía el webhook de order/paid.

    Nunca rompe al llamador si falla: la sincronización de stock es
    best-effort, no puede tirar abajo una venta.
    """
    tienda = producto.tienda
    if not producto.tn_product_id or not producto.tn_variant_id:
        return
    if not tienda.tn_access_token or not tienda.tn_store_id or not tienda.tn_sync_habilitado:
        return
    try:
        tn = TiendaNubeService(tienda)
        tn.update_variant_stock(producto.tn_product_id, producto.tn_variant_id, producto.stock)
    except Exception as e:
        logger.warning("No se pudo sincronizar stock a Tienda Nube para producto %s: %s", producto.nombre, e)
