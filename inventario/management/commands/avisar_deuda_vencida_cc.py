"""
Avisa por mail a los clientes de Cuenta Corriente cuya fecha límite de pago vence hoy.

Ejecutar diariamente (ej. cron job en Render):
    python manage.py avisar_deuda_vencida_cc

Lógica:
  1. Busca ventas a Cuenta Corriente (no anuladas) cuya fecha_limite_pago sea hoy.
  2. Agrupa por cliente (un cliente puede tener más de una venta que vence el mismo día).
  3. Si el cliente todavía tiene saldo pendiente > 0 y tiene email cargado, le envía
     un mail con el saldo total a pagar.

El saldo informado es el saldo pendiente TOTAL de la cuenta corriente (el libro de
movimientos es un saldo corrido, no por comprobante), no solo el importe de la venta
que vence hoy.
"""

import logging
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Envía un mail de aviso a los clientes de Cuenta Corriente cuya deuda vence hoy."

    def handle(self, *args, **options):
        from inventario.models import Venta
        from inventario.serializers import calcular_saldo_pendiente

        hoy = timezone.now().date()

        ventas_vencen_hoy = Venta.objects.filter(
            metodo_pago='Cuenta Corriente',
            anulada=False,
            fecha_limite_pago=hoy,
            cliente__isnull=False,
        ).select_related('cliente', 'tienda')

        clientes_avisados = {}  # cliente_id -> cliente (dedupe si tiene varias ventas que vencen hoy)
        for venta in ventas_vencen_hoy:
            clientes_avisados[venta.cliente_id] = venta.cliente

        if not clientes_avisados:
            self.stdout.write("No hay vencimientos de Cuenta Corriente para hoy.")
            return

        enviados = 0
        for cliente in clientes_avisados.values():
            saldo = calcular_saldo_pendiente(cliente)
            if saldo <= 0:
                self.stdout.write(f"{cliente.nombre_razon_social}: ya no tiene saldo pendiente, se omite.")
                continue
            if not cliente.email:
                self.stdout.write(self.style.WARNING(
                    f"{cliente.nombre_razon_social}: no tiene email cargado, no se pudo avisar."
                ))
                continue

            tienda_nombre = cliente.tienda.nombre
            asunto = f"[{tienda_nombre}] Tu cuenta corriente vence hoy"
            cuerpo = (
                f"Hola {cliente.nombre_razon_social},\n\n"
                f"Te recordamos que hoy vence el plazo acordado para cancelar tu cuenta "
                f"corriente en {tienda_nombre}.\n\n"
                f"Saldo pendiente: ${saldo:.2f}\n\n"
                f"Por favor, acercate a abonar o contactanos para coordinar el pago.\n\n"
                f"— {tienda_nombre}"
            )
            try:
                send_mail(
                    subject=asunto,
                    message=cuerpo,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
                    recipient_list=[cliente.email],
                    fail_silently=False,
                )
                enviados += 1
                self.stdout.write(self.style.SUCCESS(
                    f"{cliente.nombre_razon_social} ({cliente.email}): aviso enviado. Saldo: ${saldo:.2f}"
                ))
                logger.info("Aviso de deuda vencida enviado a %s (cliente %s)", cliente.email, cliente.id)
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"{cliente.nombre_razon_social}: error al enviar el mail: {e}"
                ))
                logger.error("Error enviando aviso de deuda vencida a cliente %s: %s", cliente.id, e)

        self.stdout.write(self.style.SUCCESS(
            f"avisar_deuda_vencida_cc completado: {enviados} aviso(s) enviado(s) de {len(clientes_avisados)} cliente(s) con vencimiento hoy."
        ))
