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
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

MP_API_BASE = "https://api.mercadopago.com"

# Importe del cargo de verificación durante el trial
MONTO_VERIFICACION = 1.00


def _headers():
    return {
        "Authorization": f"Bearer {settings.MP_ACCESS_TOKEN_SUSCRIPCIONES}",
        "Content-Type": "application/json",
    }


def crear_preaprobacion(suscripcion, back_url: str, notification_url: str) -> str:
    """
    Crea una preaprobación en MP para el plan dado.
    Devuelve la init_point (URL a la que redirigir al usuario).

    - Los primeros 7 días son trial; se cobra $1 al vincular tarjeta.
    - Luego se cobra el precio mensual del plan automáticamente.
    """
    plan = suscripcion.plan
    fecha_inicio_cobro = timezone.now() + timedelta(days=suscripcion.DIAS_TRIAL)

    payload = {
        "reason": f"Total Stock — Plan {plan.get_nombre_display()}",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(plan.precio_mensual),
            "currency_id": "ARS",
            "start_date": fecha_inicio_cobro.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
            # Cargo de $1 como verificación de fondos al activar
            "free_trial": {
                "frequency": suscripcion.DIAS_TRIAL,
                "frequency_type": "days",
            },
        },
        "back_url": back_url,
        "notification_url": notification_url,
        "status": "pending",
    }

    resp = requests.post(
        f"{MP_API_BASE}/preapproval",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    # Guardar el preapproval_id en la suscripción
    suscripcion.mp_preapproval_id = str(data.get("id", ""))
    suscripcion.fecha_fin_trial = fecha_inicio_cobro
    suscripcion.fecha_proximo_cobro = fecha_inicio_cobro
    suscripcion.save(update_fields=["mp_preapproval_id", "fecha_fin_trial", "fecha_proximo_cobro"])

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
    Marca la suscripción como activa tras la autorización del usuario en MP.
    Intenta cobrar $1 de verificación.
    """
    suscripcion.estado = "trial"
    suscripcion.save(update_fields=["estado"])

    try:
        cobrar_verificacion(suscripcion)
        logger.info("Cobro de verificación $1 OK — suscripción %s", suscripcion.id)
    except Exception as e:
        logger.warning("No se pudo cobrar $1 de verificación (%s): %s", suscripcion.id, e)


def cancelar_suscripcion(suscripcion):
    """Cancela la suscripción (por webhook o acción del usuario)."""
    suscripcion.estado = "cancelada"
    suscripcion.save(update_fields=["estado"])
    logger.info("Suscripción cancelada: %s", suscripcion.id)


def pausar_suscripcion(suscripcion):
    """Pausa la suscripción (sin cobros, sin acceso)."""
    suscripcion.estado = "pausada"
    suscripcion.save(update_fields=["estado"])
    logger.info("Suscripción pausada: %s", suscripcion.id)


def iniciar_periodo_gracia(suscripcion):
    """
    Inicia el período de gracia de 5 días por fallo de cobro.
    Se llama desde la task diaria al primer intento fallido.
    """
    if suscripcion.estado != "gracia":
        suscripcion.estado = "gracia"
        suscripcion.fecha_inicio_gracia = timezone.now()
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
