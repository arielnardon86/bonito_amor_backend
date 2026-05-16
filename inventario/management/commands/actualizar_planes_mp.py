"""
Actualiza los planes de Mercado Pago con la notification_url del backend.

Ejecutar UNA VEZ tras configurar BACKEND_URL en las variables de entorno:
    python manage.py actualizar_planes_mp

Esto garantiza que MP sepa a dónde mandar los webhooks de suscripción
(altas, cancelaciones, cobros) sin depender de la config del panel de MP.
"""

import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)
MP_API_BASE = "https://api.mercadopago.com"


class Command(BaseCommand):
    help = "Actualiza notification_url en todos los planes de MP."

    def handle(self, *args, **options):
        from inventario.models import Plan

        backend_url = getattr(settings, 'BACKEND_URL', '').rstrip('/')
        if not backend_url:
            self.stdout.write(self.style.ERROR(
                "BACKEND_URL no configurada. Agregala a las variables de entorno."
            ))
            return

        notification_url = f"{backend_url}/api/mp-webhook-suscripcion/"
        self.stdout.write(f"Notification URL: {notification_url}")

        token = getattr(settings, 'MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
        if not token:
            self.stdout.write(self.style.ERROR("MP_ACCESS_TOKEN_SUSCRIPCIONES no configurada."))
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        planes = Plan.objects.exclude(mp_plan_id='').exclude(mp_plan_id__isnull=True)
        if not planes.exists():
            self.stdout.write("No hay planes con mp_plan_id configurado.")
            return

        for plan in planes:
            try:
                resp = requests.put(
                    f"{MP_API_BASE}/preapproval_plan/{plan.mp_plan_id}",
                    json={"notification_url": notification_url},
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Plan '{plan.nombre}' ({plan.mp_plan_id}) actualizado"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"✗ Error actualizando plan '{plan.nombre}': {e}"
                ))
