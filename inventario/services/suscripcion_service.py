"""
Servicio de suscripciones recurrentes con Mercado Pago (preaprobaciones).

Flujo de alta:
  1. Usuario elige plan en el registro.
  2. Backend llama a crear_preaprobacion() → obtiene init_point (URL de MP).
  3. Usuario autoriza en MP → MP redirige al callback con preapproval_id.
  4. Backend llama a activar_suscripcion() con el preapproval_id.

Cobros:
  - Trial: 7 días gratis con cargo de $1 al vincular la tarjeta.
  - Luego: cargo mensual automático por MP.

Webhooks MP → manejar en views.py:
  - "authorized"       → activar_suscripcion()
  - "payment_created"  / "payment_approved" → registrar pago OK
  - "cancelled"        → cancelar_suscripcion()
  - "paused"           → pausar_suscripcion()
"""

import logging
import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone as tz

logger = logging.getLogger(__name__)

MP_API_BASE = "https://api.mercadopago.com"

# Importe del cargo de verificación durante el trial
MONTO_VERIFICACION = 1.00


def _proximo_dia_10(desde=None):
    """
    Devuelve el próximo día 10 de cobro de MP a partir de `desde`.
    Si `desde` ya pasó el día 10 del mes, devuelve el día 10 del mes siguiente.
    """
    if desde is None:
        desde = tz.now()
    candidate = desde.replace(day=10, hour=0, minute=0, second=0, microsecond=0)
    if candidate <= desde:
        if desde.month == 12:
            candidate = candidate.replace(year=desde.year + 1, month=1)
        else:
            candidate = candidate.replace(month=desde.month + 1)
    return candidate


def _headers():
    return {
        "Authorization": f"Bearer {settings.MP_ACCESS_TOKEN_SUSCRIPCIONES}",
        "Content-Type": "application/json",
    }


def crear_preaprobacion(suscripcion, back_url: str, notification_url: str, omitir_trial: bool = False) -> str:
    """
    Crea una preaprobación INDIVIDUAL en MP para esta suscripción puntual (no
    ligada al preapproval_plan_id compartido del Plan). Devuelve la init_point
    (URL a la que redirigir al usuario para que autorice).

    El alta normal (registro_publico/cambiar_plan) redirige al checkout del
    preapproval_plan_id del Plan, que tiene el período de prueba que se haya
    configurado en el panel de MP para ESE plan -- igual para cualquiera que se
    suscriba. Esta función existe para el caso puntual de "reautorizar con otra
    cuenta de MP sin darle otro trial a alguien que ya lo usó" (omitir_trial=True):
    al no pasar por el preapproval_plan_id compartido, el trial de ese plan no
    aplica, y si omitir_trial=True tampoco se manda ningún free_trial propio, así
    que MP cobra desde el momento en que el cliente autoriza.

    No guarda nada en `suscripcion` -- igual que el resto del sistema, el
    preapproval_id queda vinculado recién cuando llega el webhook
    subscription_preapproval (por external_reference), no al crear el checkout.
    """
    plan = suscripcion.plan

    auto_recurring = {
        "frequency": 1,
        "frequency_type": "months",
        "transaction_amount": float(plan.precio_mensual),
        "currency_id": "ARS",
    }
    if not omitir_trial:
        fecha_inicio_cobro = tz.now() + timedelta(days=suscripcion.DIAS_TRIAL)
        auto_recurring["start_date"] = fecha_inicio_cobro.strftime("%Y-%m-%dT%H:%M:%S.000-03:00")
        auto_recurring["free_trial"] = {
            "frequency": suscripcion.DIAS_TRIAL,
            "frequency_type": "days",
        }

    payload = {
        "reason": f"Total Stock — Plan {plan.get_nombre_display()}",
        "external_reference": str(suscripcion.tienda_id),
        "payer_email": suscripcion.mp_payer_email or suscripcion.tienda.email,
        "auto_recurring": auto_recurring,
        "back_url": back_url,
        "status": "pending",
    }
    if notification_url:
        payload["notification_url"] = notification_url

    resp = requests.post(
        f"{MP_API_BASE}/preapproval",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    init_point = data.get("init_point", "")
    if not init_point:
        raise ValueError(f"MP no devolvió init_point: {data}")
    return init_point


def cobrar_verificacion(suscripcion) -> dict:
    """
    Cobra $1 como verificación de fondos usando la preaprobación ya autorizada.
    Llama al endpoint de cobro inmediato (authorized payment) sobre la preaprobación.
    """
    if not suscripcion.mp_preapproval_id:
        raise ValueError("La suscripción no tiene preapproval_id.")

    payload = {
        "preapproval_id": suscripcion.mp_preapproval_id,
        "transaction_amount": MONTO_VERIFICACION,
        "description": "Verificación de fondos — Total Stock",
        "currency_id": "ARS",
    }
    resp = requests.post(
        f"{MP_API_BASE}/authorized_payments",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def obtener_preaprobacion(preapproval_id: str) -> dict:
    """Consulta el estado de una preaprobación en MP."""
    resp = requests.get(
        f"{MP_API_BASE}/preapproval/{preapproval_id}",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def activar_suscripcion(suscripcion):
    """
    Marca la suscripción como trial tras la primera autorización de MP (pending → trial).
    Setea fecha_proximo_cobro al próximo día 10 después del período de trial,
    que es la fecha en que MP comenzará a cobrar mensualmente.
    """
    ahora = tz.now()
    suscripcion.estado = "trial"
    if not suscripcion.fecha_fin_trial:
        suscripcion.fecha_fin_trial = ahora + timedelta(days=suscripcion.DIAS_TRIAL)
    # El primer cobro de MP será el día 10 que quede después del trial
    fin_trial = suscripcion.fecha_fin_trial or (ahora + timedelta(days=suscripcion.DIAS_TRIAL))
    suscripcion.fecha_proximo_cobro = _proximo_dia_10(fin_trial)
    suscripcion.save(update_fields=["estado", "fecha_fin_trial", "fecha_proximo_cobro"])
    logger.info("Suscripción activada (trial) tras confirmación MP: %s", suscripcion.id)


def renovar_suscripcion(suscripcion):
    """
    Confirma el pago mensual de MP y avanza fecha_proximo_cobro al siguiente día 10.
    Se llama desde el webhook subscription_authorized_payment o subscription_preapproval
    cuando el estado de MP es 'authorized' en un ciclo de renovación.
    """
    suscripcion.estado = "activa"
    suscripcion.fecha_inicio_gracia = None
    suscripcion.fecha_proximo_cobro = _proximo_dia_10()
    suscripcion.save(update_fields=["estado", "fecha_inicio_gracia", "fecha_proximo_cobro"])
    logger.info("Suscripción renovada (activa) tras cobro MP: %s", suscripcion.id)


def cancelar_preaprobacion_mp(preapproval_id: str):
    """Cancela la preaprobación en MP (para bajas iniciadas desde nuestro panel)."""
    try:
        resp = requests.put(
            f"{MP_API_BASE}/preapproval/{preapproval_id}",
            json={"status": "cancelled"},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Preaprobación %s cancelada en MP", preapproval_id)
    except Exception as e:
        logger.error("Error cancelando preaprobación %s en MP: %s", preapproval_id, e)
        raise


def cancelar_suscripcion(suscripcion):
    """
    Cancela la suscripción en nuestra BD.
    Los datos se mantienen 30 días; luego el cron los elimina.
    Llamar cancelar_preaprobacion_mp() ANTES si la baja viene del usuario (no de MP).
    """
    suscripcion.estado = "cancelada"
    suscripcion.fecha_cancelacion = tz.now()
    suscripcion.mp_preapproval_id = None   # permite vincular nuevo preapproval en re-suscripción
    suscripcion.fecha_fin_trial = None     # permite nuevo trial si se re-suscribe
    suscripcion.save(update_fields=["estado", "fecha_cancelacion", "mp_preapproval_id", "fecha_fin_trial"])
    logger.info("Suscripción cancelada: %s", suscripcion.id)


def pausar_suscripcion(suscripcion):
    """Pausa la suscripción (sin cobros, sin acceso). fecha_pausada es lo que
    usa el cron (procesar_gracia_suscripciones) para cancelarla sola a los 30
    días si nadie la reactiva -- se pisa cada vez que se llama (ej. si ya
    estaba pausada y se vuelve a pausar), así el contador de 30 días siempre
    arranca desde la pausa más reciente."""
    suscripcion.estado = "pausada"
    suscripcion.fecha_pausada = tz.now()
    suscripcion.save(update_fields=["estado", "fecha_pausada"])
    logger.info("Suscripción pausada: %s", suscripcion.id)


def iniciar_periodo_gracia(suscripcion):
    """
    Inicia el período de gracia de 5 días por fallo de cobro.
    Se llama desde la task diaria al primer intento fallido.
    """
    if suscripcion.estado != "gracia":
        suscripcion.estado = "gracia"
        suscripcion.fecha_inicio_gracia = tz.now()
        suscripcion.save(update_fields=["estado", "fecha_inicio_gracia"])
        logger.info("Período de gracia iniciado: %s", suscripcion.id)


def reintentar_cobro_mp(preapproval_id: str) -> bool:
    """
    Solicita a MP que reintente el cobro de la preaprobación.
    Devuelve True si MP aceptó el reintento (no garantiza que el cobro sea exitoso).
    """
    try:
        resp = requests.put(
            f"{MP_API_BASE}/preapproval/{preapproval_id}",
            json={"status": "authorized"},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Reintento de cobro falló para %s: %s", preapproval_id, e)
        return False


def cambiar_plan_mp(suscripcion, plan_nuevo):
    """
    Actualiza el monto de la preaprobación en MP al precio del nuevo plan.
    El cambio de plan ya fue aplicado en la BD; este método sincroniza MP.
    El próximo ciclo se cobrará el nuevo precio.
    """
    if not suscripcion.mp_preapproval_id:
        return

    try:
        resp = requests.put(
            f"{MP_API_BASE}/preapproval/{suscripcion.mp_preapproval_id}",
            json={
                "auto_recurring": {
                    "transaction_amount": float(plan_nuevo.precio_mensual),
                }
            },
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Plan MP actualizado a %s para suscripción %s", plan_nuevo.nombre, suscripcion.id)
    except Exception as e:
        logger.error("Error actualizando plan en MP (%s): %s", suscripcion.id, e)


def registrar_venta_recibo_suscripcion(tienda_cliente, monto, metodo_pago, mp_authorized_payment_id=None,
                                        origen_mp_suscripcion=False, fecha_venta=None):
    """
    Crea la Venta + DetalleVenta del cobro de la suscripción de
    `tienda_cliente` en la tienda interna de facturación (settings.
    TIENDA_SUSCRIPCIONES_NOMBRE) -- a propósito SIN facturar electrónicamente
    (sin AFIP/CAE): queda facturada=False, y el recibo no fiscal queda
    disponible bajo demanda vía GET /api/ventas/{id}/pdf-recibo/, igual que
    cualquier otra venta no facturada del sistema. Decisión explícita del
    dueño: "que no se facture, que se haga recibo" -- vale tanto para los
    cobros automáticos de Mercado Pago (ver mp_webhook_suscripcion en
    views.py) como para los pagos que Ariel carga a mano desde el panel de
    Clientes SaaS (ver PagosManualesTiendaView en admin_saas_views.py).

    mp_authorized_payment_id es la clave de dedup: si ya existe una Venta con
    ese id para la tienda de facturación, se devuelve esa en vez de crear
    otra (evita duplicar si MP reintenta el webhook, o si se vuelve a llamar
    para el mismo pago manual). Sin ese id (None) siempre crea una Venta
    nueva -- no hay forma de detectar duplicados sin un identificador único.

    Devuelve la Venta (creada o la ya existente), o None si la tienda de
    facturación interna no existe.
    """
    from django.db import transaction
    from ..models import Tienda, Venta, DetalleVenta, Producto, User

    nombre_tienda_facturacion = getattr(settings, 'TIENDA_SUSCRIPCIONES_NOMBRE', 'Total Stock')
    tienda_facturacion = Tienda.objects.filter(nombre=nombre_tienda_facturacion).first()
    if not tienda_facturacion:
        logger.warning(
            "registrar_venta_recibo_suscripcion: no existe la tienda '%s' (TIENDA_SUSCRIPCIONES_NOMBRE) -- no se registra el cobro de %s",
            nombre_tienda_facturacion, tienda_cliente.nombre,
        )
        return None

    if mp_authorized_payment_id:
        existente = Venta.objects.filter(tienda=tienda_facturacion, mp_authorized_payment_id=mp_authorized_payment_id).first()
        if existente:
            return existente

    usuario_sistema, _ = User.objects.get_or_create(
        username='mercadopago_suscripciones',
        defaults={
            'is_staff': False, 'is_active': True, 'tienda': tienda_facturacion,
            'first_name': 'Mercado Pago', 'last_name': 'Suscripciones',
        },
    )
    producto_suscripcion, _ = Producto.objects.get_or_create(
        tienda=tienda_facturacion, nombre='Suscripción Total Stock',
        defaults={'precio': monto, 'stock': 0},
    )

    with transaction.atomic():
        venta = Venta.objects.create(
            tienda=tienda_facturacion,
            usuario=usuario_sistema,
            total=monto,
            metodo_pago=metodo_pago,
            mp_authorized_payment_id=mp_authorized_payment_id,
            origen_mp_suscripcion=origen_mp_suscripcion,
            tienda_cliente=tienda_cliente,
            cliente_nombre=tienda_cliente.nombre,
            cliente_cuit=tienda_cliente.cuit or '',
        )
        DetalleVenta.objects.create(
            venta=venta, producto=producto_suscripcion,
            cantidad=1, precio_unitario=monto, subtotal=monto,
        )

    if fecha_venta:
        # fecha_venta es auto_now_add -- se pisa después del create para que
        # quede la fecha real del cobro/pago, no la de este momento.
        Venta.objects.filter(pk=venta.pk).update(fecha_venta=fecha_venta)
        venta.fecha_venta = fecha_venta

    return venta
