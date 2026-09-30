"""
Avisa por mail a los clientes de Cuenta Corriente en dos casos, en una sola corrida:
  1. Vencimiento HOY: la fecha límite de pago de alguna venta es hoy.
  2. Aviso previo: la fecha límite de pago de alguna venta es dentro de 10 días.

Los dos casos comparten un solo comando (y por lo tanto un solo cron job) a propósito:
agregar un cron job aparte en Render tiene costo, así que el aviso previo se resuelve
reusando el disparador diario que ya existe para el aviso de vencimiento.

Ejecutar diariamente (ej. cron job en Render):
    python manage.py avisar_deuda_vencida_cc

Lógica (igual para los dos casos, solo cambia la fecha objetivo y el texto del mail):
  1. Busca ventas a Cuenta Corriente (no anuladas) cuya fecha_limite_pago sea la fecha
     objetivo (hoy, o hoy + 10 días).
  2. Agrupa por cliente (puede tener más de una venta que vence el mismo día).
  3. Si el cliente todavía tiene saldo pendiente > 0 y tiene email cargado, le envía
     un mail con el saldo total a pagar, el detalle de consumos y pagos DE ESTE MES
     (para que el saldo se entienda, no sea solo un número suelto), y adjunta el PDF
     de resumen de cuenta completo (desglose mensual + detalle transacción por
     transacción con fecha de todo el historial).

El saldo informado es el saldo pendiente TOTAL de la cuenta corriente (el libro de
movimientos es un saldo corrido, no por comprobante), no solo el importe de la venta
que vence en la fecha objetivo.
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DIAS_ANTICIPACION_AVISO_PREVIO = 10


def _texto_detalle_mes(consumos, pagos):
    """Arma el bloque de texto plano con los consumos y pagos del mes en curso,
    cada uno con su fecha, para que el saldo informado no sea un número suelto
    sino algo que el cliente pueda verificar. `consumos`/`pagos` vienen de
    detalle_transacciones_cliente() (más reciente primero)."""
    lineas = ["Consumos de este mes:"]
    if not consumos:
        lineas.append("  (sin consumos este mes)")
    else:
        for c in consumos:
            lineas.append(f"  - {c['fecha'].strftime('%d/%m/%Y')}: {c['detalle']} — ${c['monto']:.2f}")

    lineas.append("")
    lineas.append("Pagos de este mes:")
    if not pagos:
        lineas.append("  (sin pagos este mes)")
    else:
        for p in pagos:
            lineas.append(f"  - {p['fecha'].strftime('%d/%m/%Y')}: {p['detalle']} — ${p['monto']:.2f}")

    return "\n".join(lineas)


class Command(BaseCommand):
    help = "Envía mails de Cuenta Corriente: vencimiento hoy y aviso previo (10 días antes)."

    def handle(self, *args, **options):
        hoy = timezone.now().date()

        enviados_hoy = self._avisar(
            fecha_objetivo=hoy,
            asunto_tpl="[{tienda}] Tu cuenta corriente vence hoy",
            cuerpo_tpl=(
                "Hola {cliente},\n\n"
                "Te recordamos que hoy vence el plazo acordado para cancelar tu cuenta "
                "corriente en {tienda}.\n\n"
                "Saldo pendiente: ${saldo:.2f}\n\n"
                "{detalle_mes}\n\n"
                "Adjuntamos el resumen de cuenta completo en PDF, con el detalle de "
                "todos tus consumos y pagos.\n\n"
                "Por favor, acercate a abonar o contactanos para coordinar el pago.\n\n"
                "— {tienda}"
            ),
            etiqueta="vencimiento hoy",
        )
        enviados_previo = self._avisar(
            fecha_objetivo=hoy + timedelta(days=DIAS_ANTICIPACION_AVISO_PREVIO),
            asunto_tpl=f"[{{tienda}}] Tu cuenta corriente vence en {DIAS_ANTICIPACION_AVISO_PREVIO} días",
            cuerpo_tpl=(
                "Hola {cliente},\n\n"
                f"Te avisamos que en {DIAS_ANTICIPACION_AVISO_PREVIO} días "
                "({fecha_vencimiento}) vence el plazo acordado para cancelar tu cuenta "
                "corriente en {tienda}.\n\n"
                "Saldo pendiente: ${saldo:.2f}\n\n"
                "{detalle_mes}\n\n"
                "Adjuntamos el resumen de cuenta completo en PDF, con el detalle de "
                "todos tus consumos y pagos.\n\n"
                "Por favor, acercate a abonar o contactanos para coordinar el pago.\n\n"
                "— {tienda}"
            ),
            etiqueta=f"aviso previo ({DIAS_ANTICIPACION_AVISO_PREVIO} días)",
        )

        self.stdout.write(self.style.SUCCESS(
            f"avisar_deuda_vencida_cc completado: {enviados_hoy} aviso(s) de vencimiento hoy, "
            f"{enviados_previo} aviso(s) previo(s) ({DIAS_ANTICIPACION_AVISO_PREVIO} días)."
        ))

    def _avisar(self, fecha_objetivo, asunto_tpl, cuerpo_tpl, etiqueta):
        from inventario.models import Venta
        from inventario.serializers import calcular_saldo_pendiente
        from inventario.views import (
            detalle_transacciones_cliente, construir_pdf_resumen_cuenta, REPORTLAB_AVAILABLE,
        )

        hoy = timezone.now().date()
        primer_dia_mes = hoy.replace(day=1)

        ventas = Venta.objects.filter(
            metodo_pago='Cuenta Corriente',
            anulada=False,
            fecha_limite_pago=fecha_objetivo,
            cliente__isnull=False,
        ).select_related('cliente', 'tienda')

        clientes_a_avisar = {}  # cliente_id -> cliente (dedupe si tiene varias ventas con la misma fecha)
        for venta in ventas:
            clientes_a_avisar[venta.cliente_id] = venta.cliente

        if not clientes_a_avisar:
            self.stdout.write(f"Sin vencimientos ({etiqueta}) para {fecha_objetivo}.")
            return 0

        enviados = 0
        for cliente in clientes_a_avisar.values():
            saldo = calcular_saldo_pendiente(cliente)
            if saldo <= 0:
                self.stdout.write(f"{cliente.nombre_razon_social}: ya no tiene saldo pendiente, se omite ({etiqueta}).")
                continue
            if not cliente.email:
                self.stdout.write(self.style.WARNING(
                    f"{cliente.nombre_razon_social}: no tiene email cargado, no se pudo avisar ({etiqueta})."
                ))
                continue

            consumos_mes, pagos_mes = detalle_transacciones_cliente(cliente, desde=primer_dia_mes, hasta=hoy)

            tienda_nombre = cliente.tienda.nombre
            asunto = asunto_tpl.format(tienda=tienda_nombre)
            cuerpo = cuerpo_tpl.format(
                cliente=cliente.nombre_razon_social,
                tienda=tienda_nombre,
                saldo=saldo,
                fecha_vencimiento=fecha_objetivo.strftime('%d/%m/%Y'),
                detalle_mes=_texto_detalle_mes(consumos_mes, pagos_mes),
            )
            try:
                email = EmailMessage(
                    subject=asunto,
                    body=cuerpo,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
                    to=[cliente.email],
                )
                if REPORTLAB_AVAILABLE:
                    try:
                        pdf_buffer = construir_pdf_resumen_cuenta(cliente)
                        email.attach(f'resumen_cuenta_{cliente.id}.pdf', pdf_buffer.getvalue(), 'application/pdf')
                    except Exception as e:
                        # No bloquea el envío del mail -- el cliente igual se entera por
                        # el cuerpo del mail, aunque esta vez se quede sin el PDF adjunto.
                        logger.error("No se pudo generar el PDF de resumen de cuenta para cliente %s: %s", cliente.id, e)
                email.send(fail_silently=False)
                enviados += 1
                self.stdout.write(self.style.SUCCESS(
                    f"{cliente.nombre_razon_social} ({cliente.email}): aviso enviado ({etiqueta}). Saldo: ${saldo:.2f}"
                ))
                logger.info("Aviso de Cuenta Corriente (%s) enviado a %s (cliente %s)", etiqueta, cliente.email, cliente.id)
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"{cliente.nombre_razon_social}: error al enviar el mail ({etiqueta}): {e}"
                ))
                logger.error("Error enviando aviso de Cuenta Corriente (%s) a cliente %s: %s", etiqueta, cliente.id, e)

        return enviados
