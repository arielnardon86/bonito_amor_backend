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
  0.5. Suscripciones en 'pending' hace más de DIAS_LIMITE_PENDING (el cliente
     nunca completó la autorización en MP) → pausar directo, sin pasar por
     gracia (nunca llegó a pagar, no hay nada "en gracia" que esperar).
  1. Suscripciones en trial/activa cuyo fecha_proximo_cobro ya pasó y no llegó
     webhook de pago → iniciar gracia (5 días).
  2. Suscripciones ya en gracia → avanzar contador y avisar.
  3. Si llevan DIAS_GRACIA días en gracia → pausar (sin pérdida de datos).
  4. Suscripciones en 'pausada' hace más de DIAS_LIMITE_PAUSADA sin que nadie
     las reactive → cancelar (arranca la cuenta regresiva de DIAS_RETENCION
     días del paso 0.1 de la corrida siguiente, que ya borra canceladas viejas).

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
    DIAS_LIMITE_PENDING = 7   # 'pending' sin completar el pago en MP → pausar
    DIAS_LIMITE_PAUSADA = 30  # 'pausada' sin reactivar → cancelar

    # fecha_proximo_cobro se guarda como medianoche del día 10 (_proximo_dia_10
    # en suscripcion_service.py), pero MP no cobra instantáneo a las 00:00 -- lo
    # procesa en algún momento de ese día. Sin este margen, el cron (que corre a
    # las 9am) trataba "fecha_proximo_cobro < ahora" como "no pagó" para
    # CUALQUIER tienda con ciclo el día 10 apenas pasaba la medianoche, mandando
    # el mail de "tu pago está pendiente, tenés 5 días" a clientes que en
    # realidad iban a pagar bien más tarde ese mismo día. Con el margen, recién
    # se considera "sin cobro" al otro día.
    MARGEN_VERIFICACION_COBRO = timedelta(hours=24)

    # Estados desde los que tiene sentido reconciliar. 'activa' estaba afuera
    # originalmente bajo el supuesto de "si ya está activa, está al día" -- pero
    # ese supuesto solo cubre el caso "no llegó el webhook de PAGO" (pending/
    # trial/gracia/pausada -> activa). No cubre el caso inverso: una tienda que
    # YA estaba activa y el cliente cancela directo en MP -- si ese webhook de
    # cancelación se pierde, nunca se la vuelve a chequear y queda activa acá
    # para siempre aunque en MP figure cancelada. Solo 'cancelada' queda afuera
    # (una vez cancelada de verdad, no hay nada más que reconciliar).
    ESTADOS_A_RECONCILIAR = ('pending', 'trial', 'activa', 'gracia', 'pausada')

    def handle(self, *args, **options):
        from inventario.models import Suscripcion
        from inventario.services.suscripcion_service import (
            iniciar_periodo_gracia,
            pausar_suscripcion,
            cancelar_suscripcion,
            cancelar_preaprobacion_mp,
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

        # 0.5. 'pending' hace más de DIAS_LIMITE_PENDING (nunca completó la
        #      autorización en MP) → pausar directo, sin pasar por gracia --
        #      no hay ningún pago previo del que "estar en gracia".
        limite_pending = ahora - timedelta(days=self.DIAS_LIMITE_PENDING)
        pendientes_vencidas = Suscripcion.objects.filter(
            estado='pending',
            fecha_inicio__lt=limite_pending,
        ).select_related('plan', 'tienda')

        for sus in pendientes_vencidas:
            self.stdout.write(
                self.style.WARNING(
                    f"Pausando por pago nunca confirmado: {sus.tienda.nombre} "
                    f"({sus.plan.nombre}) — pendiente desde el {sus.fecha_inicio:%d/%m/%Y}"
                )
            )
            pausar_suscripcion(sus)
            self._enviar_aviso_pending_pausada(sus)

        # 1. Suscripciones trial/activa con fecha_proximo_cobro vencida hace más
        #    de MARGEN_VERIFICACION_COBRO (no apenas pasó la medianoche del día
        #    10 -- ver el comentario en esa constante) y MP no notificó pago exitoso.
        sin_cobro = Suscripcion.objects.filter(
            estado__in=('trial', 'activa'),
            fecha_proximo_cobro__isnull=False,
            fecha_proximo_cobro__lt=ahora - self.MARGEN_VERIFICACION_COBRO,
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

        # 4. 'pausada' hace más de DIAS_LIMITE_PAUSADA sin que nadie la
        #    reactive → cancelar. Deja que el paso 0.1 de la corrida siguiente
        #    (30 días post-cancelación) termine de borrar sus datos -- así una
        #    tienda suspendida y abandonada ya no queda viva para siempre.
        limite_pausada = ahora - timedelta(days=self.DIAS_LIMITE_PAUSADA)
        pausadas_vencidas = Suscripcion.objects.filter(
            estado='pausada',
            fecha_pausada__isnull=False,
            fecha_pausada__lt=limite_pausada,
        ).select_related('plan', 'tienda')

        for sus in pausadas_vencidas:
            dias_pausada = (ahora - sus.fecha_pausada).days
            self.stdout.write(
                self.style.WARNING(
                    f"Cancelando por suspensión prolongada: {sus.tienda.nombre} "
                    f"({dias_pausada} días pausada sin reactivar)"
                )
            )
            # Esta baja la inicia nuestro sistema por inactividad, no MP -- si
            # todavía queda un preapproval vivo del lado de MP (ej. nunca llegó
            # a agotar sus propios reintentos), hay que cancelarlo nosotros o
            # podría seguir intentando cobrarle la tarjeta a un cliente que ya
            # vamos a borrar. Best-effort: un error acá no debe frenar la baja
            # local (ver mismo criterio que el resto del comando).
            if sus.mp_preapproval_id:
                try:
                    cancelar_preaprobacion_mp(sus.mp_preapproval_id)
                except Exception as e:
                    logger.warning(
                        "No se pudo cancelar preapproval %s en MP para %s (se cancela igual localmente): %s",
                        sus.mp_preapproval_id, sus.tienda.nombre, e,
                    )
            cancelar_suscripcion(sus)
            self._enviar_aviso_pausada_cancelada(sus)

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
            # MP no cancela ni pausa el preapproval apenas falla un cobro: lo
            # reintenta varias veces primero (el panel de MP lo muestra como
            # "Atrasado — intento N de 4"), y durante todo ese período el
            # preapproval sigue con status='authorized'. pending_charge_quantity
            # resultó NO ser confiable para detectar esto: confirmado contra un
            # payload real de una tienda que en el dashboard de MP se veía como
            # "Atrasado — intento 3 de 4", pending_charge_quantity vino `null`
            # (se lee `or 0`, así que nunca se habría detectado el atraso). El
            # campo que sí refleja ese estado en ese mismo payload es
            # summarized.semaphore = "yellow" (verde = al día). Se deja
            # cobros_pendientes como señal secundaria por si algún otro caso sí
            # lo popula.
            cobros_pendientes = resumen.get('pending_charge_quantity') or 0
            semaforo = resumen.get('semaphore')

            if estado_mp == 'cancelled' and sus.estado != 'cancelada':
                # MP la canceló (o nunca llegó a autorizarla) pero acá seguía con acceso.
                self.stdout.write(self.style.WARNING(
                    f"Reconciliado con MP: {sus.tienda.nombre} estaba cancelada en MP "
                    f"pero localmente seguía en '{sus.get_estado_display()}' → cancelada"
                ))
                cancelar_suscripcion(sus)
                corregidas += 1
                continue

            if estado_mp != 'authorized':
                continue

            if (
                sus.estado != 'activa' and cobros_realizados >= 1 and cobros_pendientes == 0
            ):
                # MP ya cobró al menos una vez y no tiene nada pendiente, pero acá
                # seguíamos sin reflejarlo (pending/trial/gracia/pausada) → el
                # webhook de pago se perdió.
                self.stdout.write(self.style.SUCCESS(
                    f"Reconciliado con MP: {sus.tienda.nombre} estaba en "
                    f"'{sus.get_estado_display()}' con {cobros_realizados} cobro(s) "
                    f"confirmado(s) en MP → activa"
                ))
                renovar_suscripcion(sus)
                corregidas += 1

            # pago_atrasado es independiente del bloque anterior y se revisa para
            # CUALQUIER suscripción con acceso (incluida 'activa'): a diferencia
            # de gracia/pausada, no le saca el acceso a la tienda, solo prende o
            # apaga el aviso que ve el usuario al iniciar sesión -- por eso se
            # actualiza en los dos sentidos acá, todos los días.
            nuevo_atrasado = cobros_pendientes > 0 or semaforo in ('yellow', 'red')
            if sus.pago_atrasado != nuevo_atrasado:
                if nuevo_atrasado:
                    self.stdout.write(self.style.WARNING(
                        f"MP: {sus.tienda.nombre} tiene un cobro pendiente en curso "
                        f"(sigue con acceso, se activa el aviso) — summarized={resumen}"
                    ))
                    logger.warning(
                        "Reconciliación MP: %s con cobro pendiente, se marca pago_atrasado — datos=%s",
                        sus.tienda.nombre, datos,
                    )
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f"MP: {sus.tienda.nombre} regularizó su cobro pendiente — se apaga el aviso"
                    ))
                sus.pago_atrasado = nuevo_atrasado
                sus.save(update_fields=['pago_atrasado'])
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

    def _enviar_aviso_pending_pausada(self, sus):
        """Email cuando se pausa una suscripción que nunca llegó a completar
        el pago en MP (estado 'pending' vencido, ver paso 0.5 de handle)."""
        email_destino = sus.tienda.email
        if not email_destino:
            return
        try:
            send_mail(
                subject="🚫 Total Stock: tu cuenta fue suspendida (pago sin confirmar)",
                message=(
                    f"Hola,\n\n"
                    f"Nunca llegamos a confirmar el pago de tu suscripción "
                    f"({sus.plan.get_nombre_display()}) para la tienda {sus.tienda.nombre}, "
                    f"así que tu cuenta fue suspendida.\n\n"
                    f"Tus datos están intactos. Para reactivar tu cuenta, "
                    f"completá la suscripción en Mercado Pago o contactanos.\n\n"
                    f"— El equipo de Total Stock"
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@totalstock.com.ar'),
                recipient_list=[email_destino],
                fail_silently=True,
            )
            logger.info("Aviso de pausa por pending vencido enviado a %s", email_destino)
        except Exception as e:
            logger.warning("No se pudo enviar aviso de pausa (pending) a %s: %s", email_destino, e)

    def _enviar_aviso_pausada_cancelada(self, sus):
        """Email cuando se cancela automáticamente una suscripción que llevaba
        demasiado tiempo pausada sin que nadie la reactivara (ver paso 4 de
        handle). A partir de acá arranca la cuenta regresiva de
        DIAS_RETENCION días antes de borrar los datos de la tienda."""
        email_destino = sus.tienda.email
        if not email_destino:
            return
        try:
            send_mail(
                subject="🗑️ Total Stock: tu cuenta suspendida fue cancelada",
                message=(
                    f"Hola,\n\n"
                    f"Tu cuenta de {sus.tienda.nombre} estuvo suspendida más de "
                    f"{self.DIAS_LIMITE_PAUSADA} días sin que se reactivara, así que fue cancelada.\n\n"
                    f"Tus datos se conservan {self.DIAS_RETENCION} días más por si querés "
                    f"recuperar la cuenta -- después de eso se eliminan de forma permanente. "
                    f"Contactanos si querés reactivarla.\n\n"
                    f"— El equipo de Total Stock"
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@totalstock.com.ar'),
                recipient_list=[email_destino],
                fail_silently=True,
            )
            logger.info("Aviso de cancelación por pausa prolongada enviado a %s", email_destino)
        except Exception as e:
            logger.warning("No se pudo enviar aviso de cancelación (pausada) a %s: %s", email_destino, e)
