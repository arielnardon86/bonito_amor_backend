"""
Actualiza la notification_url en cada preapproval individual de MP.

El plan ya tiene la notification_url seteada, pero los preapprovals creados
antes pueden tener su propia URL (o ninguna) que tiene prioridad sobre la del plan.

Ejecutar una vez, o cada vez que cambie BACKEND_URL:
    python manage.py actualizar_preapprovals_mp
"""

import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)
MP_API_BASE = "https://api.mercadopago.com"


class Command(BaseCommand):
    help = "Actualiza notification_url en cada preapproval individual de MP."

    def handle(self, *args, **options):
        from inventario.models import Suscripcion

        backend_url = getattr(settings, 'BACKEND_URL', '').rstrip('/')
        if not backend_url:
            self.stdout.write(self.style.ERROR("BACKEND_URL no configurada."))
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

        suscripciones = Suscripcion.objects.exclude(
            mp_preapproval_id__isnull=True
        ).exclude(
            mp_preapproval_id=''
        ).select_related('tienda', 'plan')

        if not suscripciones.exists():
            self.stdout.write("No hay preapprovals individuales registrados.")
            return

        ok = 0
        errores = 0
        for sus in suscripciones:
            try:
                # GET para obtener los campos actuales del preapproval
                get_resp = requests.get(
                    f"{MP_API_BASE}/preapproval/{sus.mp_preapproval_id}",
                    headers=headers,
                    timeout=15,
                )
                get_resp.raise_for_status()
                datos = get_resp.json()

                # Solo actualizar si la notification_url es diferente
                if datos.get('notification_url') == notification_url:
                    self.stdout.write(f"  — {sus.tienda.nombre}: ya actualizado, se omite")
                    ok += 1
                    continue

                put_resp = requests.put(
                    f"{MP_API_BASE}/preapproval/{sus.mp_preapproval_id}",
                    json={"notification_url": notification_url},
                    headers=headers,
                    timeout=15,
                )
                put_resp.raise_for_status()
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ {sus.tienda.nombre} ({sus.mp_preapproval_id[:12]}...) actualizado"
                ))
                ok += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ {sus.tienda.nombre} ({sus.mp_preapproval_id[:12]}...): {e}"
                ))
                errores += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nListo: {ok} actualizados, {errores} errores."
        ))
