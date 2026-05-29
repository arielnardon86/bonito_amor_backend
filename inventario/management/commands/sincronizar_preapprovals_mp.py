"""
Busca en MP todos los preapprovals de cada plan y los vincula con las
suscripciones en la BD usando external_reference (UUID de la tienda).

Soluciona el caso donde el webhook nunca llegó y mp_preapproval_id quedó vacío.
También actualiza la notification_url en cada preapproval encontrado.

Ejecutar una vez:
    python manage.py sincronizar_preapprovals_mp
"""

import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)
MP_API_BASE = "https://api.mercadopago.com"


class Command(BaseCommand):
    help = "Vincula preapprovals de MP con suscripciones de la BD."

    def handle(self, *args, **options):
        from inventario.models import Plan, Suscripcion

        token = getattr(settings, 'MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
        if not token:
            self.stdout.write(self.style.ERROR("MP_ACCESS_TOKEN_SUSCRIPCIONES no configurada."))
            return

        backend_url = getattr(settings, 'BACKEND_URL', '').rstrip('/')
        notification_url = f"{backend_url}/api/mp-webhook-suscripcion/" if backend_url else None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        planes = Plan.objects.exclude(mp_plan_id='').exclude(mp_plan_id__isnull=True)
        total_vinculados = 0
        total_errores = 0

        for plan in planes:
            self.stdout.write(f"\nBuscando preapprovals del plan '{plan.nombre}' ({plan.mp_plan_id})...")

            # Buscar todos los preapprovals de este plan en MP
            offset = 0
            limit = 100
            preapprovals = []
            while True:
                try:
                    resp = requests.get(
                        f"{MP_API_BASE}/preapproval/search",
                        params={
                            "preapproval_plan_id": plan.mp_plan_id,
                            "limit": limit,
                            "offset": offset,
                        },
                        headers=headers,
                        timeout=15,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    resultados = data.get("results", [])
                    preapprovals.extend(resultados)
                    if len(resultados) < limit:
                        break
                    offset += limit
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Error buscando preapprovals en MP: {e}"))
                    break

            self.stdout.write(f"  Encontrados {len(preapprovals)} preapprovals en MP")

            for pa in preapprovals:
                pa_id = pa.get("id", "")
                external_ref = pa.get("external_reference", "")
                estado_mp = pa.get("status", "")
                payer_email = pa.get("payer_email", "") or pa.get("payer", {}).get("email", "")

                if not external_ref:
                    self.stdout.write(f"  — Preapproval {pa_id}: sin external_reference, se omite")
                    continue

                # Buscar la suscripción por UUID de tienda
                try:
                    sus = Suscripcion.objects.select_related('tienda', 'plan').get(
                        tienda__id=external_ref
                    )
                except Suscripcion.DoesNotExist:
                    self.stdout.write(f"  — Preapproval {pa_id}: tienda {external_ref} no encontrada en BD")
                    continue
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Error buscando suscripción: {e}"))
                    continue

                fields_to_save = []

                # Vincular preapproval_id si no estaba
                if not sus.mp_preapproval_id:
                    sus.mp_preapproval_id = str(pa_id)
                    fields_to_save.append("mp_preapproval_id")
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ {sus.tienda.nombre}: preapproval_id vinculado ({pa_id})"
                    ))
                elif sus.mp_preapproval_id != str(pa_id):
                    self.stdout.write(
                        f"  ~ {sus.tienda.nombre}: ya tiene preapproval_id diferente, se omite"
                    )
                    continue

                if payer_email and not sus.mp_payer_email:
                    sus.mp_payer_email = payer_email
                    fields_to_save.append("mp_payer_email")

                if fields_to_save:
                    sus.save(update_fields=fields_to_save)
                    total_vinculados += 1

                # Actualizar notification_url en el preapproval
                if notification_url and pa.get("notification_url") != notification_url:
                    try:
                        put_resp = requests.put(
                            f"{MP_API_BASE}/preapproval/{pa_id}",
                            json={"notification_url": notification_url},
                            headers=headers,
                            timeout=15,
                        )
                        put_resp.raise_for_status()
                        self.stdout.write(f"    → notification_url actualizada en MP")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(
                            f"    ⚠ No se pudo actualizar notification_url: {e}"
                        ))
                        total_errores += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nFinalizado: {total_vinculados} suscripciones vinculadas, {total_errores} advertencias."
        ))
