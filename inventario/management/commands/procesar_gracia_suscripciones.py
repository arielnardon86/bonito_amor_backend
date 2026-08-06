"""
Management command para procesar el período de gracia de suscripciones.

Ejecutar diariamente (ej. cron job en Render):
    python manage.py procesar_gracia_suscripciones

Lógica (MP cobra el día 10 de cada mes):
  0. Reconciliar contra MP: suscripciones en pending/trial/gracia/pausada con
     preapproval vinculado se consultan contra la API de MP. Si MP ya cobró
     (charged_quantity >= 1) pero localmente seguimos sin reflejarlo, es que
     el webhook de pago nunca se procesó → se corrige llamando a
     renovar_suscripcion(). Si MP la cancelló y acá seguimos con acceso, se
     cancela. Corre ANTES del resto para no mandar a gracia/pausa a una
     tienda que en realidad está pagando bien (solo perdimos su webhook).
  1. Suscripciones en trial/activa cuyo fecha_proximo_cobro ya pasó y no llegó
     webhook de pago → iniciar gracia (5 días).
  2. Suscripciones ya en gracia → avanzar contador y avisar.
  3. Si llevan DIAS_GRACIA días en gracia → pausar (sin pérdida de datos).

Nota: los webhooks de MP son la fuente primaria. Este comando es el safety net
para cuando un webhook no llega o llega tarde.
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Procesa período de gracia de suscripciones con cobros pendientes."

    DIAS_RETENCION = 30  # Días de retención de datos tras cancelación

    # Estados desde los que tiene sentido reconciliar: si ya está 'activa' o
    # 'cancelada' asumimos que está al día (evita pegarle a MP por cada una en
    # cada corrida del cron).
    ESTADOS_A_RECONCILIAR = ('pending', 'trial', 'gracia', 'pausada')

    def handle(self, *args, **options):
        from inventario.models import Suscripcion
        from inventario.services.suscripcion_service import (
            iniciar_periodo_gracia,
            pausar_suscripcion,
        )

        ahora = timezone.now()

        # 0. Reconciliar estado local contra el estado real en Mercado Pago
        #    (safety net para webhooks de pago que nunca se procesaron).
        self._reconciliar_con_mp()

        # 0.1. Canceladas hace más de 30 días → eliminar todos los datos
        limite_borrado = ahora - timedelta(days=self.DIAS_RETENCION)
        a_borrar = Suscripcion.objects.filter(
            estado='cancelada',
            fecha_cancelacion__isnull=False,
            fecha_cancelacion__lt=limite_borrado,
        ).select_related('tienda')

        for sus in a_borrar:
            tienda = sus.tienda
            nombre = tienda.nombre
            try:
                tienda.delete()  # Cascade: elimina productos, ventas, usuarios, etc.
                self.stdout.write(
                    self.style.WARNING(
                        f"Datos eliminados (30 días post-cancelación): {nombre}"
                    )
                )
                logger.info("Tienda eliminada por cancelación: %s", nombre)
            except Exception as e:
                logger.error("Error eliminando tienda %s: %s", nombre, e)

        # 1. Suscripciones trial/activa con fecha_proximo_cobro vencida
        #    (el día 10 pasó y MP no notificó pago exitoso)
        sin_cobro = Suscripcion.objects.filter(
            estado__in=('trial', 'activa'),
            fecha_proximo_cobro__isnull=False,
            fecha_proximo_cobro__lt=ahora,
        ).select_related('plan', 'tienda')

        for sus in sin_cobro:
            self.stdout.write(
                f"Sin cobro confirmado: {sus.tienda.nombre} ({sus.plan.nombre}) "
                f"— vencido el {sus.fecha_proximo_cobro:%d/%m/%Y}"
            )
            iniciar_periodo_gracia(sus)
            self._enviar_aviso(sus, dia=0)

        # 2. Suscripciones en gracia → avanzar y avisar o pausar
        en_gracia = Suscripcion.objects.filter(
            estado='gracia',
            fecha_inicio_gracia__isnull=False,
        ).select_related('plan', 'tienda')

        for sus in en_gracia:
            dias_en_gracia = (ahora - sus.fecha_inicio_gracia).days

            if dias_en_gracia >= sus.DIAS_GRACIA:
                self.stdout.write(
                    self.style.WARNING(
                        f"Pausando por gracia agotada: {sus.tienda.nombre} "
                        f"({dias_en_gracia} días sin pago)"
                    )
                )
                pausar_suscripcion(sus)
                self._enviar_aviso(sus, dia=-1)
            else:
                dias_restantes = sus.DIAS_GRACIA - dias_en_gracia
                self.stdout.write(
                    f"En gracia día {dias_en_gracia + 1}: {sus.tienda.nombre} "
                    f"— {dias_restantes} día(s) restante(s)"
                )
                self._enviar_aviso(sus, dia=dias_en_gracia + 1)

        self.stdout.write(self.style.SUCCESS("procesar_gracia_suscripciones completado."))

    def _reconciliar_con_mp(self):
        """Consulta en MP el estado real de cada preapproval vinculado y corrige
        la suscripción local si quedó desactualizada por un webhook perdido."""
        from inventario.models import Suscripcion
        from inventario.services.suscripcion_service import (
            obtener_preaprobacion,
            renovar_suscripcion,
            cancelar_suscripcion,
        )

        candidatas = Suscripcion.objects.filter(
            estado__in=self.ESTADOS_A_RECONCILIAR,
        ).exclude(
            mp_preapproval_id__isnull=True,
        ).exclude(
            mp_preapproval_id='',
        ).select_related('tienda', 'plan')

        corregidas = 0
        for sus in candidatas:
            try:
                datos = obtener_preaprobacion(sus.mp_preapproval_id)
            except Exception as e:
                logger.warning(
                    "Reconciliación MP: no se pudo consultar preapproval %s (%s): %s",
                    sus.mp_preapproval_id, sus.tienda.nombre, e,
                )
                continue

            estado_mp = datos.get('status', '')
            resumen = datos.get('summarized') or {}
            cobros_realizados = resumen.get('charged_quantity') or 0

            if estado_mp == 'authorized' and cobros_realizados >= 1:
                # MP ya cobró al menos una vez pero acá seguíamos sin reflejarlo
                # (pending/trial/gracia/pausada) → el webhook de pago se perdió.
                self.stdout.write(self.style.SUCCESS(
                    f"Reconciliado con MP: {sus.tienda.nombre} estaba en "
                    f"'{sus.get_estado_display()}' con {cobros_realizados} cobro(s) "
                    f"confirmado(s) en MP → activa"
                ))
                renovar_suscripcion(sus)
                corregidas += 1
            elif estado_mp == 'cancelled' and sus.estado != 'cancelada':
                # MP la canceló (o nunca llegó a autorizarla) pero acá seguía con acceso.
                self.stdout.write(self.style.WARNING(
                    f"Reconciliado con MP: {sus.tienda.nombre} estaba cancelada en MP "
                    f"pero localmente seguía en '{sus.get_estado_display()}' → cancelada"
                ))
                cancelar_suscripcion(sus)
                corregidas += 1

        self.stdout.write(
            f"Reconciliación MP: {len(candidatas)} suscripción(es) revisada(s), "
            f"{corregidas} corregida(s)."
        )

    def _enviar_aviso(self, sus, dia: int):
        """Envía email de aviso al admin de la tienda."""
        email_destino = sus.tienda.email
        if not email_destino:
            return

        nombre_tienda = sus.tienda.nombre
        nombre_plan   = sus.plan.get_nombre_display()

        if dia == 0:
            asunto = "⚠️ Total Stock: tu suscripción tiene un pago pendiente"
            cuerpo = (
                f"Hola,\n\n"
                f"Mercado Pago aún no confirmó el cobro de tu suscripción "
                f"({nombre_plan}) para la tienda {nombre_tienda}.\n\n"
                f"Tenés {sus.DIAS_GRACIA} días para regularizar el pago. "
                f"Si no se confirma, tu acceso será suspendido temporalmente "
                f"(sin pérdida de datos).\n\n"
                f"Verificá tu método de pago en Mercado Pago.\n\n"
                f"— El equipo de Total Stock"
            )
        elif dia == -1:
            asunto = "🚫 Total Stock: tu cuenta fue suspendida por falta de pago"
            cuerpo = (
                f"Hola,\n\n"
                f"Lamentablemente tu suscripción de {nombre_tienda} fue suspendida "
                f"por falta de pago.\n\n"
                f"Tus datos están intactos. Para reactivar tu cuenta, "
                f"actualizá tu método de pago en Mercado Pago o contactanos.\n\n"
                f"— El equipo de Total Stock"
            )
        else:
            dias_restantes = sus.DIAS_GRACIA - dia
            asunto = f"⚠️ Total Stock: {dias_restantes} día(s) para regularizar tu pago"
            cuerpo = (
                f"Hola,\n\n"
                f"Seguimos sin confirmar el cobro de tu suscripción "
                f"({nombre_plan}) para {nombre_tienda}.\n\n"
                f"Te quedan {dias_restantes} día(s) antes de que tu cuenta sea suspendida. "
                f"No perderás ningún dato.\n\n"
                f"Verificá tu método de pago en Mercado Pago.\n\n"
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
            logger.info("Aviso enviado a %s (día %s)", email_destino, dia)
        except Exception as e:
            logger.warning("No se pudo enviar aviso a %s: %s", email_destino, e)
