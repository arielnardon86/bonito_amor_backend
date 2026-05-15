"""
Management command para procesar el período de gracia de suscripciones.

Ejecutar diariamente (ej. cron job en Render):
    python manage.py procesar_gracia_suscripciones

Lógica:
  1. Detecta suscripciones activas cuyo fecha_proximo_cobro haya pasado.
  2. Si no estaban en gracia → las pone en gracia (día 0).
  3. Si ya estaban en gracia → reintenta el cobro en MP y advierte al usuario.
  4. Si llevan 5+ días en gracia → las pausa (bloqueo de acceso).
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Procesa período de gracia de suscripciones con cobros fallidos."

    def handle(self, *args, **options):
        from inventario.models import Suscripcion
        from inventario.services.suscripcion_service import (
            iniciar_periodo_gracia,
            reintentar_cobro_mp,
            pausar_suscripcion,
        )

        ahora = timezone.now()

        # 0. Trials vencidos sin suscripción activa en MP → pausar
        trials_vencidos = Suscripcion.objects.filter(
            estado='trial',
            fecha_fin_trial__lt=ahora,
        ).select_related('plan', 'tienda')

        for sus in trials_vencidos:
            self.stdout.write(
                self.style.WARNING(f"Trial vencido sin pago: {sus.tienda.nombre}")
            )
            pausar_suscripcion(sus)
            self._enviar_aviso(sus, dia=-1)

        # 1. Suscripciones activas con cobro vencido (no en gracia todavía)
        vencidas = Suscripcion.objects.filter(
            estado='activa',
            fecha_proximo_cobro__lt=ahora,
        ).select_related('plan', 'tienda')

        for sus in vencidas:
            self.stdout.write(f"Iniciando gracia: {sus.tienda.nombre} ({sus.plan.nombre})")
            iniciar_periodo_gracia(sus)
            self._enviar_aviso(sus, dia=0)

        # 2. Suscripciones ya en gracia → reintentar y avisar
        en_gracia = Suscripcion.objects.filter(
            estado='gracia',
            fecha_inicio_gracia__isnull=False,
        ).select_related('plan', 'tienda')

        for sus in en_gracia:
            dias_en_gracia = (ahora - sus.fecha_inicio_gracia).days

            if dias_en_gracia >= sus.DIAS_GRACIA:
                # Período de gracia agotado → pausar
                self.stdout.write(
                    self.style.WARNING(
                        f"Pausando por gracia agotada: {sus.tienda.nombre}"
                    )
                )
                pausar_suscripcion(sus)
                self._enviar_aviso(sus, dia=-1)  # -1 = suspendida
            else:
                # Reintentar cobro y avisar
                self.stdout.write(
                    f"Reintentando cobro (día {dias_en_gracia + 1}): {sus.tienda.nombre}"
                )
                if sus.mp_preapproval_id:
                    reintentar_cobro_mp(sus.mp_preapproval_id)
                self._enviar_aviso(sus, dia=dias_en_gracia + 1)

        self.stdout.write(self.style.SUCCESS("procesar_gracia_suscripciones completado."))

    def _enviar_aviso(self, sus, dia: int):
        """Envía email de aviso al admin de la tienda."""
        email_destino = sus.tienda.email
        if not email_destino:
            return

        if dia == 0:
            asunto = "⚠️ Total Stock: problema con el cobro de tu suscripción"
            cuerpo = (
                f"Hola,\n\n"
                f"No pudimos procesar el cobro de tu suscripción "
                f"({sus.plan.get_nombre_display()}) para la tienda {sus.tienda.nombre}.\n\n"
                f"Tenés {sus.DIAS_GRACIA} días para regularizar el pago antes de que "
                f"tu acceso sea suspendido.\n\n"
                f"Por favor verificá tus datos de pago en Mercado Pago.\n\n"
                f"— El equipo de Total Stock"
            )
        elif dia == -1:
            asunto = "🚫 Total Stock: tu suscripción fue suspendida"
            cuerpo = (
                f"Hola,\n\n"
                f"Lamentablemente tu suscripción de {sus.tienda.nombre} fue suspendida "
                f"por falta de pago.\n\n"
                f"Para reactivarla, contactanos o actualizá tu método de pago en "
                f"Mercado Pago.\n\n"
                f"— El equipo de Total Stock"
            )
        else:
            dias_restantes = sus.DIAS_GRACIA - dia
            asunto = f"⚠️ Total Stock: {dias_restantes} día(s) para regularizar tu suscripción"
            cuerpo = (
                f"Hola,\n\n"
                f"Seguimos sin poder cobrar tu suscripción "
                f"({sus.plan.get_nombre_display()}) para {sus.tienda.nombre}.\n\n"
                f"Te quedan {dias_restantes} día(s) antes de que tu acceso sea suspendido.\n\n"
                f"Verificá tus datos de pago en Mercado Pago.\n\n"
                f"— El equipo de Total Stock"
            )

        try:
            send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@totalstock.com.ar'),
                recipient_list=[email_destino],
                fail_silently=True,
            )
            logger.info("Aviso de gracia enviado a %s (día %s)", email_destino, dia)
        except Exception as e:
            logger.warning("No se pudo enviar aviso a %s: %s", email_destino, e)
