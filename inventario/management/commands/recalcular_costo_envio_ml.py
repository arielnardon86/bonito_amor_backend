"""
Recalcula arancel_total (impuestos) y costo_envio_ml de ventas de Mercado Libre
ya creadas, usando el mismo fallback por familia de variantes que ya usa el
webhook de ventas (_buscar_arancel_ml_producto en views.py).

Pensado para el caso típico: el vendedor carga (o corrige) el costo de envío/
impuestos de un producto con variantes DESPUÉS de que ya hubo ventas de esa
familia -- esas ventas viejas quedaron con $0 porque en su momento no había
ningún ArancelMercadoLibreProducto que matcheara (ni siquiera por la familia,
si además el arancel se cargó recién ahora).

Uso:
    python manage.py recalcular_costo_envio_ml --dry-run
    python manage.py recalcular_costo_envio_ml --tienda Oxford --desde 2026-09-01
    python manage.py recalcular_costo_envio_ml --tienda Oxford --desde 2026-09-01 --hasta 2026-09-30
"""

from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Recalcula el costo de envío e impuestos (Mercado Libre) de ventas ya "
        "creadas, aplicando el arancel configurado por producto o heredado de "
        "su familia de variantes."
    )

    def add_arguments(self, parser):
        parser.add_argument('--tienda', type=str, default=None, help='Nombre de la tienda a procesar (default: todas).')
        parser.add_argument('--desde', type=str, default=None, help='Fecha desde, YYYY-MM-DD (default: primer día del mes actual).')
        parser.add_argument('--hasta', type=str, default=None, help='Fecha hasta, YYYY-MM-DD (default: hoy).')
        parser.add_argument('--dry-run', action='store_true', help='Muestra qué cambiaría sin guardar nada.')

    def handle(self, *args, **options):
        from inventario.models import Venta
        from inventario.views import _buscar_arancel_ml_producto

        dry_run = options['dry_run']
        hoy = timezone.localdate()
        desde = datetime.strptime(options['desde'], '%Y-%m-%d').date() if options['desde'] else hoy.replace(day=1)
        hasta = datetime.strptime(options['hasta'], '%Y-%m-%d').date() if options['hasta'] else hoy

        ventas = Venta.objects.filter(
            origen_mercadolibre=True,
            anulada=False,
            fecha_venta__date__gte=desde,
            fecha_venta__date__lte=hasta,
        ).select_related('tienda').prefetch_related('detalles__producto').order_by('fecha_venta')

        if options['tienda']:
            ventas = ventas.filter(tienda__nombre=options['tienda'])

        etiqueta_tienda = f" de \"{options['tienda']}\"" if options['tienda'] else ''
        self.stdout.write(f"Revisando ventas ML{etiqueta_tienda} entre {desde} y {hasta}...")
        if dry_run:
            self.stdout.write(self.style.WARNING("Modo --dry-run: no se guarda nada.\n"))

        revisadas = 0
        actualizadas = 0
        total_envio_agregado = Decimal('0.00')
        total_impuestos_agregado = Decimal('0.00')

        for venta in ventas:
            revisadas += 1
            nuevo_costo_envio = Decimal('0.00')
            nuevo_arancel = Decimal('0.00')
            detalle_lineas = []

            for detalle in venta.detalles.all():
                if detalle.anulado_individualmente or not detalle.producto:
                    continue
                arancel_ml, via_familia = _buscar_arancel_ml_producto(venta.tienda, detalle.producto)
                if not arancel_ml:
                    continue
                impuestos_pct = arancel_ml.impuestos_porcentaje or Decimal('0')
                arancel_item = detalle.subtotal * (impuestos_pct / Decimal('100'))
                costo_envio_item = (arancel_ml.costo_envio or Decimal('0')) * detalle.cantidad
                nuevo_arancel += arancel_item
                nuevo_costo_envio += costo_envio_item
                if via_familia:
                    detalle_lineas.append(
                        f"      - {detalle.producto.nombre}: envío ${costo_envio_item} "
                        f"(heredado de \"{arancel_ml.producto.nombre}\")"
                    )

            costo_envio_actual = venta.costo_envio_ml or Decimal('0.00')
            arancel_actual = venta.arancel_total or Decimal('0.00')

            if nuevo_costo_envio != costo_envio_actual or nuevo_arancel != arancel_actual:
                diff_envio = nuevo_costo_envio - costo_envio_actual
                diff_arancel = nuevo_arancel - arancel_actual
                self.stdout.write(
                    f"  Venta {venta.id} ({venta.fecha_venta.date()}, {venta.tienda.nombre}): "
                    f"envío ${costo_envio_actual} → ${nuevo_costo_envio} (Δ${diff_envio}), "
                    f"impuestos ${arancel_actual} → ${nuevo_arancel} (Δ${diff_arancel})"
                )
                for linea in detalle_lineas:
                    self.stdout.write(linea)

                total_envio_agregado += diff_envio
                total_impuestos_agregado += diff_arancel
                actualizadas += 1

                if not dry_run:
                    venta.costo_envio_ml = nuevo_costo_envio
                    venta.arancel_total = nuevo_arancel
                    venta.save(update_fields=['costo_envio_ml', 'arancel_total'])

        self.stdout.write('')
        prefijo = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefijo}Ventas revisadas: {revisadas} | actualizadas: {actualizadas} | "
            f"envío agregado: ${total_envio_agregado} | impuestos agregado: ${total_impuestos_agregado}"
        ))
        if dry_run and actualizadas:
            self.stdout.write("Corré de nuevo sin --dry-run para guardar los cambios.")
