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
import time
import requests

logger = logging.getLogger(__name__)

TN_API_BASE  = "https://api.tiendanube.com/v1"
TN_AUTH_URL  = "https://www.tiendanube.com/apps/{app_id}/authorize"
TN_TOKEN_URL = "https://www.tiendanube.com/apps/authorize/token"

USER_AGENT = "TotalStock (soporte@totalstock.com.ar)"

# Límite oficial de la API de Tiendanube (leaky bucket): 40 requests de ráfaga,
# tasa de fuga de 2 req/seg (x10 en planes Next/Evolution) -- ver
# https://nuvemshop.dev/en-US/apps/erp-guide/api-usage. 0.55s de margen sobre
# el teórico 0.5s para no quedar al límite exacto.
MIN_INTERVAL_SECONDS = 0.55
# Techo al tiempo de espera ante un 429, aunque x-rate-limit-reset pida más --
# esto corre adentro del hilo del webhook (o de un request síncrono del panel),
# no puede colgarse indefinidamente.
MAX_RETRY_WAIT_SECONDS = 5.0


class TiendaNubeService:
    """Wrapper sobre la API de Tienda Nube para una tienda ya autenticada."""

    def __init__(self, tienda):
        from django.conf import settings
        self.tienda        = tienda
        self.access_token  = tienda.tn_access_token
        self.store_id      = tienda.tn_store_id
        self.app_id        = settings.TIENDANUBE_APP_ID
        self.client_secret = settings.TIENDANUBE_CLIENT_SECRET
        self._last_request_ts = 0.0
        # Cache en memoria del id de location por defecto, para no repetir el
        # GET /locations en cada llamada dentro del mismo request/hilo (ver
        # _resolver_location_id_default).
        self._location_id_default = None
        self._location_id_resuelto = False

    # ── Helpers de petición ──────────────────────────────────────────────────

    def _headers(self):
        return {
            "Authentication": f"bearer {self.access_token}",
            "Content-Type":   "application/json; charset=utf-8",
            "User-Agent":     USER_AGENT,
        }

    def _url(self, path):
        return f"{TN_API_BASE}/{self.store_id}/{path.lstrip('/')}"

    def _throttle(self):
        """Autothrottle a ~2 req/seg por instancia: los loops que ya reusan una
        misma instancia (tn_sync_stock, tn_export_products) quedan protegidos
        sin tocar esos call sites."""
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)

    def _request(self, method, path, **kwargs):
        """Punto único de salida a la API de TN. Si pega un 429, espera lo que
        indica x-rate-limit-reset (ms, con techo MAX_RETRY_WAIT_SECONDS) y
        reintenta una sola vez -- nunca reintenta en loop infinito."""
        url = self._url(path)
        for intento in range(2):
            self._throttle()
            self._last_request_ts = time.monotonic()
            resp = requests.request(method, url, headers=self._headers(), timeout=15, **kwargs)
            if resp.status_code == 429 and intento == 0:
                try:
                    espera = min(int(resp.headers.get('x-rate-limit-reset', 1000)) / 1000, MAX_RETRY_WAIT_SECONDS)
                except (TypeError, ValueError):
                    espera = 1.0
                logger.warning("429 de Tiendanube en %s %s -- esperando %.2fs y reintentando", method, path, espera)
                time.sleep(espera)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def _get(self, path, params=None):
        return self._request('GET', path, params=params).json()

    def _post(self, path, data):
        return self._request('POST', path, json=data).json()

    def _put(self, path, data):
        return self._request('PUT', path, json=data).json()

    def _delete(self, path):
        return self._request('DELETE', path).status_code

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
        # 200 es el máximo de per_page que admite la API de Tienda Nube -- con
        # catálogos grandes (~400 productos) usar el default de 25 significaba ~16
        # llamadas de red solo para traer el catálogo, antes de siquiera empezar a
        # procesar variantes.
        per_page = 200
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
        variantes: list of {precio, stock, sku (opt), talle (opt), variante2 (opt)}
        Devuelve (tn_product_id, tn_variants_list)

        TN requiere que si alguna variante usa 'values', el producto tenga
        'attributes' definidos con exactamente el mismo número de ejes, y que
        TODAS las variantes traigan 'values' con esa misma longitud.
        """
        ejes = []
        if any(v.get('talle') for v in variantes):
            ejes.append(('talle', 'Variante'))
        if any(v.get('variante2') for v in variantes):
            ejes.append(('variante2', 'Variante 2'))

        variants_data = []
        for v in variantes:
            variant = {"price": str(v['precio']), "stock": v.get('stock', 0)}
            if v.get('sku'):
                variant["sku"] = v['sku']
            if ejes:
                # Siempre incluir values (con la misma longitud) para TODAS las
                # variantes cuando hay al menos un eje presente.
                variant["values"] = [{"es": str(v.get(campo) or '')} for campo, _ in ejes]
            variants_data.append(variant)

        data = {
            "name": {"es": nombre},
            "variants": variants_data,
        }
        if ejes:
            # Los ejes de variante — TN los llama "attributes"
            data["attributes"] = [{"es": label} for _, label in ejes]

        result = self._post("products", data)
        tn_product_id = str(result.get("id", ""))
        tn_variants = result.get("variants", [])
        return tn_product_id, tn_variants

    def add_variant(self, tn_product_id, precio, stock, sku=None, talle=None, variante2=None):
        """
        Agrega una variante a un producto TN existente.
        El producto ya debe tener 'attributes' definidos si se usan 'values'.
        Devuelve tn_variant_id.
        """
        variant = {"price": str(precio), "stock": stock}
        if sku:
            variant["sku"] = sku
        values = []
        if talle:
            values.append({"es": str(talle)})
        if variante2:
            values.append({"es": str(variante2)})
        if values:
            variant["values"] = values
        result = self._post(f"products/{tn_product_id}/variants", variant)
        return str(result.get("id", ""))

    # ── Stock ────────────────────────────────────────────────────────────────

    def get_locations(self):
        """Lista las locations (centros de distribución) de la tienda. Requiere
        el scope read_locations -- si la app no lo tiene pedido, o la tienda no
        tiene multi-inventory activado, la llamada falla y el caller
        (_resolver_location_id_default) cae al campo 'stock' plano de siempre."""
        return self._get("locations")

    def _resolver_location_id_default(self):
        """Resuelve (y cachea en self.tienda.tn_location_id) el id de la
        location marcada is_default en Tiendanube, para poder mandar
        inventory_levels en vez del campo 'stock' plano -- que en tiendas
        multi-CD Tiendanube solo lo aplica a la PRIMERA location (ver
        nuvemshop.dev/api/guides/multi-inventory/products: "if only
        variant.stock is sent, we'll update the first inventory_level"), así
        que sin esto un comercio con más de un centro de distribución nunca
        vería actualizado el stock del resto.

        Se resuelve una sola vez por tienda (persistido en el modelo), no en
        cada sincronización de stock -- evita duplicar la cantidad de
        requests a la API en el path más frecuente (después de cada venta).
        Si /locations falla (401/403 por falta del scope read_locations en la
        configuración de la app, o 404 en tiendas sin multi-inventory
        activado) devuelve None sin propagar el error."""
        if self._location_id_resuelto:
            return self._location_id_default
        self._location_id_resuelto = True
        if self.tienda.tn_location_id:
            self._location_id_default = self.tienda.tn_location_id
            return self._location_id_default
        try:
            locations = self.get_locations()
        except requests.exceptions.RequestException as e:
            logger.info("No se pudo resolver la location por defecto de TN (tienda %s): %s", self.tienda.nombre, e)
            return None
        default = next((loc for loc in locations if loc.get('is_default')), None) or (locations[0] if locations else None)
        if not default:
            return None
        location_id = str(default.get('id'))
        self._location_id_default = location_id
        self.tienda.tn_location_id = location_id
        self.tienda.save(update_fields=['tn_location_id'])
        return location_id

    def update_variant_stock(self, product_id, variant_id, quantity):
        """Actualiza el stock de una variante (anidada bajo su producto en la
        API de TN). Ver _resolver_location_id_default: si se pudo resolver la
        location por defecto de la tienda, manda inventory_levels (formato
        multi-inventory); si no, cae al campo 'stock' plano de siempre."""
        location_id = self._resolver_location_id_default()
        if location_id:
            data = {"inventory_levels": [{"location_id": location_id, "stock": quantity}]}
        else:
            data = {"stock": quantity}
        return self._put(f"products/{product_id}/variants/{variant_id}", data)

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
    except requests.exceptions.HTTPError as e:
        # 404 confirmado = el producto/variante ya no existe del lado de TN
        # (se borró ahí) -- desvincular para no volver a intentarlo por
        # siempre en cada venta futura. Cualquier otro status (429, 500, etc)
        # es una falla transitoria: no tocar el vínculo, solo loguear.
        if e.response is not None and e.response.status_code == 404:
            logger.warning(
                "Producto/variante de %s ya no existe en Tiendanube (404) -- desvinculando", producto.nombre
            )
            producto.tn_product_id = None
            producto.tn_variant_id = None
            producto.tn_sincronizado = False
            producto.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado'])
        else:
            logger.warning("No se pudo sincronizar stock a Tienda Nube para producto %s: %s", producto.nombre, e)
    except Exception as e:
        logger.warning("No se pudo sincronizar stock a Tienda Nube para producto %s: %s", producto.nombre, e)
