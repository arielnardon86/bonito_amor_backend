# inventario/services/mercadopago_pos_service.py
"""
Servicio de integración con la cuenta PROPIA de Mercado Pago de una tienda --
para que ELLA cobre a SUS clientes con QR dinámico desde el Punto de Venta.

Distinto de inventario/services/suscripcion_service.py, que usa
settings.MP_ACCESS_TOKEN_SUSCRIPCIONES (la cuenta de Total Stock, para
cobrarle la suscripción a cada tienda) -- acá cada tienda conecta su propia
cuenta por OAuth y este servicio opera siempre con SU token.

Flujo:
  1. Dueño de la tienda hace clic en "Conectar con Mercado Pago" (panel de
     Medios de Pago y Aranceles, al elegir el método "QR Mercado Pago").
  2. get_authorization_url() -> redirige a MP -> el dueño autoriza con su
     propia cuenta -> MP redirige de vuelta con un `code`.
  3. exchange_code_for_token(code, redirect_uri): guarda access_token/
     refresh_token/user_id en la Tienda, y de una vez provisiona la
     tienda+caja en MP (provisionar_store_y_pos) para poder emitir QR.
  4. En cada venta del Punto de Venta con método "QR Mercado Pago":
     crear_orden_qr(monto, external_reference) -> devuelve el QR para
     mostrarle al cliente, y consultar_orden(order_id) para saber si pagó
     (polling desde el frontend mientras el modal del QR está abierto).
"""
import base64
import logging
import uuid
from datetime import timedelta
from io import BytesIO

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MP_API_BASE = "https://api.mercadopago.com"
MP_AUTH_URL = "https://auth.mercadopago.com/authorization"

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


class MercadoPagoPosReconnectRequired(Exception):
    """Se lanza cuando el refresh_token ya no es válido (ej. el dueño
    desvinculó la app desde su cuenta de MP). La tienda debe reconectar."""
    pass


class MercadoPagoPosService:
    def __init__(self, tienda):
        self.tienda = tienda
        self.client_id = getattr(settings, 'MP_POS_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'MP_POS_CLIENT_SECRET', '')
        self.access_token = tienda.mp_pos_access_token
        self.refresh_token = tienda.mp_pos_refresh_token
        self.user_id = tienda.mp_pos_user_id

    def esta_conectada(self):
        return bool(self.access_token and self.tienda.mp_pos_external_id)

    def _headers(self, incluir_idempotency=False):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if incluir_idempotency:
            headers["X-Idempotency-Key"] = str(uuid.uuid4())
        return headers

    # ── OAuth ─────────────────────────────────────────────────────────────

    def get_authorization_url(self, redirect_uri, state=None):
        if not self.client_id:
            raise ValueError("MP_POS_CLIENT_ID no configurado (variable de entorno).")
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'platform_id': 'mp',
            'redirect_uri': redirect_uri,
        }
        if state:
            params['state'] = state
        query_string = '&'.join(f'{k}={v}' for k, v in params.items())
        return f"{MP_AUTH_URL}?{query_string}"

    def exchange_code_for_token(self, code, redirect_uri):
        if not self.client_id or not self.client_secret:
            raise ValueError("MP_POS_CLIENT_ID / MP_POS_CLIENT_SECRET no configurados.")
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        }
        resp = requests.post(f"{MP_API_BASE}/oauth/token", data=data, timeout=30)
        resp.raise_for_status()
        token_data = resp.json()

        self.tienda.mp_pos_access_token = token_data.get('access_token')
        self.tienda.mp_pos_refresh_token = token_data.get('refresh_token')
        self.tienda.mp_pos_user_id = str(token_data.get('user_id') or '')
        self.tienda.mp_pos_public_key = token_data.get('public_key')
        expires_in = token_data.get('expires_in', 15552000)
        self.tienda.mp_pos_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        self.tienda.save(update_fields=[
            'mp_pos_access_token', 'mp_pos_refresh_token', 'mp_pos_user_id',
            'mp_pos_public_key', 'mp_pos_token_expires_at',
        ])
        self.access_token = self.tienda.mp_pos_access_token
        self.refresh_token = self.tienda.mp_pos_refresh_token
        self.user_id = self.tienda.mp_pos_user_id

        logger.info("Mercado Pago (POS) conectado para tienda %s (user_id=%s)", self.tienda.nombre, self.user_id)

        self.provisionar_store_y_pos()
        return token_data

    def refresh_access_token(self):
        if not self.refresh_token or not self.client_id or not self.client_secret:
            raise ValueError("Refresh token / Client ID / Client Secret no configurado.")
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
        }
        try:
            resp = requests.post(f"{MP_API_BASE}/oauth/token", data=data, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (400, 401):
                logger.warning(
                    "Token de Mercado Pago (POS) inválido para %s -- limpiando, requiere reconectar: %s",
                    self.tienda.nombre, e.response.text,
                )
                self.desconectar()
                raise MercadoPagoPosReconnectRequired(
                    "La conexión con Mercado Pago ya no es válida (seguramente se desvinculó desde la "
                    "cuenta de MP). Reconectá desde Medios de Pago y Aranceles."
                )
            raise

        token_data = resp.json()
        self.tienda.mp_pos_access_token = token_data.get('access_token')
        if token_data.get('refresh_token'):
            self.tienda.mp_pos_refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 15552000)
        self.tienda.mp_pos_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        self.tienda.save(update_fields=['mp_pos_access_token', 'mp_pos_refresh_token', 'mp_pos_token_expires_at'])
        self.access_token = self.tienda.mp_pos_access_token
        self.refresh_token = self.tienda.mp_pos_refresh_token
        logger.info("Access token de Mercado Pago (POS) renovado para %s", self.tienda.nombre)
        return token_data

    def ensure_valid_token(self):
        if not self.access_token:
            raise ValueError("La tienda no tiene conectada su cuenta de Mercado Pago.")
        vence = self.tienda.mp_pos_token_expires_at
        margen = timedelta(minutes=10)
        if vence and timezone.now() >= (vence - margen):
            self.refresh_access_token()

    def desconectar(self):
        self.tienda.mp_pos_access_token = None
        self.tienda.mp_pos_refresh_token = None
        self.tienda.mp_pos_user_id = None
        self.tienda.mp_pos_public_key = None
        self.tienda.mp_pos_token_expires_at = None
        self.tienda.mp_pos_store_id = None
        self.tienda.mp_pos_external_id = None
        self.tienda.save(update_fields=[
            'mp_pos_access_token', 'mp_pos_refresh_token', 'mp_pos_user_id',
            'mp_pos_public_key', 'mp_pos_token_expires_at', 'mp_pos_store_id', 'mp_pos_external_id',
        ])
        self.access_token = None
        self.refresh_token = None

    # ── Provisioning (una sola vez, al conectar) ────────────────────────────

    def provisionar_store_y_pos(self):
        """Crea una sucursal (store) y una caja (POS) en la cuenta recién
        conectada -- requisito de la API de MP para poder emitir órdenes QR.
        Idempotente: si la tienda ya tiene mp_pos_external_id, no hace nada."""
        if self.tienda.mp_pos_external_id:
            return

        headers = self._headers()
        resp = requests.get(f"{MP_API_BASE}/users/me", headers=headers, timeout=15)
        resp.raise_for_status()
        user_id = resp.json().get('id')

        # city_name/state_name: la API de MP los valida contra una lista cerrada
        # de localidades (confirmado probando -- "Buenos Aires" como city_name
        # no es válido, pero "La Plata" sí) y Tienda no guarda ciudad/provincia
        # estructurada hoy, solo `direccion` en texto libre. Placeholder fijo:
        # no afecta el cobro ni el QR en sí, es solo metadata descriptiva de la
        # "sucursal" del lado de MP. Si en el futuro se agrega ciudad/provincia
        # estructurada a Tienda, reemplazar acá.
        external_store_id = f"TS{str(self.tienda.id).replace('-', '')[:18].upper()}"
        store_body = {
            'name': f"{self.tienda.nombre} (Total Stock)",
            'external_id': external_store_id,
            'location': {
                'street_number': '1',
                'street_name': self.tienda.direccion or 'Sin domicilio',
                'city_name': 'La Plata',
                'state_name': 'Buenos Aires',
                'latitude': -34.6037,
                'longitude': -58.3816,
            },
        }
        resp_store = requests.post(
            f"{MP_API_BASE}/users/{user_id}/stores", json=store_body, headers=headers, timeout=15
        )
        resp_store.raise_for_status()
        store_id = resp_store.json().get('id')

        pos_external_id = f"POS{str(self.tienda.id).replace('-', '')[:17].upper()}"
        pos_body = {
            'name': f"Caja {self.tienda.nombre}",
            'fixed_amount': False,
            'store_id': str(store_id),
            'external_id': pos_external_id,
        }
        resp_pos = requests.post(f"{MP_API_BASE}/pos", json=pos_body, headers=headers, timeout=15)
        resp_pos.raise_for_status()

        self.tienda.mp_pos_store_id = str(store_id)
        self.tienda.mp_pos_external_id = pos_external_id
        self.tienda.save(update_fields=['mp_pos_store_id', 'mp_pos_external_id'])
        logger.info(
            "Sucursal/caja de Mercado Pago provisionadas para %s (store_id=%s, pos=%s)",
            self.tienda.nombre, store_id, pos_external_id,
        )

    # ── Cobro con QR ─────────────────────────────────────────────────────

    def crear_orden_qr(self, monto, external_reference, descripcion="Venta Total Stock"):
        """Crea una orden QR dinámica por `monto` (Decimal/str/float) y
        devuelve (order_id, qr_base64_png). No vuelve a llamar a MP para
        armar la imagen: el qr_data (formato EMVCo) se renderiza local con
        la librería qrcode -- mismo mecanismo que el QR de ARCA/AFIP."""
        self.ensure_valid_token()
        if not self.tienda.mp_pos_external_id:
            self.provisionar_store_y_pos()

        monto_str = f"{float(monto):.2f}"
        body = {
            'type': 'qr',
            'total_amount': monto_str,
            'external_reference': external_reference,
            'config': {'qr': {'external_pos_id': self.tienda.mp_pos_external_id, 'mode': 'dynamic'}},
            'transactions': {'payments': [{'amount': monto_str}]},
            'items': [{'title': descripcion, 'unit_price': monto_str, 'quantity': 1, 'unit_measure': 'unit'}],
        }
        resp = requests.post(
            f"{MP_API_BASE}/v1/orders", json=body, headers=self._headers(incluir_idempotency=True), timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        order_id = data['id']
        qr_data = data['type_response']['qr_data']

        qr_base64 = None
        if QRCODE_AVAILABLE:
            img = qrcode.make(qr_data, border=2)
            buf = BytesIO()
            img.save(buf, format='PNG')
            qr_base64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

        return order_id, qr_base64

    def consultar_orden(self, order_id):
        """Devuelve el dict crudo de GET /v1/orders/{id} -- el frontend hace
        polling con esto mientras el modal del QR está abierto. status
        'processed'/status_detail 'accredited' = pagada."""
        self.ensure_valid_token()
        resp = requests.get(f"{MP_API_BASE}/v1/orders/{order_id}", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    def cancelar_orden(self, order_id):
        """Cancela una orden QR sin pagar (ej. el cajero cierra el modal
        antes de que el cliente pague) -- best-effort, igual vence sola a
        los 15 min si no se cancela."""
        self.ensure_valid_token()
        try:
            resp = requests.post(
                f"{MP_API_BASE}/v1/orders/{order_id}/cancel", headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning("No se pudo cancelar la orden QR %s (venció sola igual): %s", order_id, e)
