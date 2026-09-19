"""
Avisa por mail a los clientes de Cuenta Corriente a los que les faltan 10 días para
el vencimiento de su fecha límite de pago. Complementa a avisar_deuda_vencida_cc, que
avisa el día mismo del vencimiento.

Ejecutar diariamente (ej. cron job en Render):
    python manage.py avisar_cierre_proximo_cc

Lógica: igual que avisar_deuda_vencida_cc, pero filtrando ventas cuya fecha_limite_pago
sea hoy + 10 días en vez de hoy.
"""

import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DIAS_ANTICIPACION = 10


class Command(BaseCommand):
    help = "Envía un mail de aviso a los clientes de Cuenta Corriente a los que les faltan 10 días para el vencimiento."

    def handle(self, *args, **options):
        from inventario.models import Venta
        from inventario.serializers import calcular_saldo_pendiente

        fecha_aviso = timezone.now().date() + timedelta(days=DIAS_ANTICIPACION)

        ventas_por_vencer = Venta.objects.filter(
            metodo_pago='Cuenta Corriente',
            anulada=False,
            fecha_limite_pago=fecha_aviso,
            cliente__isnull=False,
        ).select_related('cliente', 'tienda')

        clientes_avisados = {}  # cliente_id -> cliente (dedupe si tiene varias ventas que vencen ese día)
        for venta in ventas_por_vencer:
            clientes_avisados[venta.cliente_id] = venta.cliente

        if not clientes_avisados:
            self.stdout.write(f"No hay vencimientos de Cuenta Corriente para dentro de {DIAS_ANTICIPACION} días ({fecha_aviso}).")
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
            fecha_vencimiento_texto = fecha_aviso.strftime('%d/%m/%Y')
            asunto = f"[{tienda_nombre}] Tu cuenta corriente vence en {DIAS_ANTICIPACION} días"
            cuerpo = (
                f"Hola {cliente.nombre_razon_social},\n\n"
                f"Te avisamos que en {DIAS_ANTICIPACION} días (el {fecha_vencimiento_texto}) vence el plazo "
                f"acordado para cancelar tu cuenta corriente en {tienda_nombre}.\n\n"
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
                logger.info("Aviso de cierre próximo (10 días) enviado a %s (cliente %s)", cliente.email, cliente.id)
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"{cliente.nombre_razon_social}: error al enviar el mail: {e}"
                ))
                logger.error("Error enviando aviso de cierre próximo a cliente %s: %s", cliente.id, e)

        self.stdout.write(self.style.SUCCESS(
            f"avisar_cierre_proximo_cc completado: {enviados} aviso(s) enviado(s) de {len(clientes_avisados)} cliente(s) "
            f"con vencimiento el {fecha_aviso}."
        ))
