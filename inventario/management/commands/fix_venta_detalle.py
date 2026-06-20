from django.core.management.base import BaseCommand
from decimal import Decimal


class Command(BaseCommand):
    help = 'Corrige la cantidad de un DetalleVenta y recalcula el total de la venta'

    def add_arguments(self, parser):
        parser.add_argument('venta_id', type=str, help='UUID de la venta a corregir')
        parser.add_argument('--cantidad', type=int, default=1, help='Cantidad correcta del detalle (default: 1)')
        parser.add_argument('--dry-run', action='store_true', help='Muestra qué haría sin guardar')

    def handle(self, *args, **options):
        from inventario.models import Venta, DetalleVenta

        venta_id = options['venta_id']
        cantidad_correcta = options['cantidad']
        dry_run = options['dry_run']

        try:
            venta = Venta.objects.get(id=venta_id)
        except Venta.DoesNotExist:
            self.stderr.write(f'❌ Venta {venta_id} no encontrada')
            return

        self.stdout.write(f'\n📋 Venta: {venta.id}')
        self.stdout.write(f'   Total actual: ${venta.total}')
        self.stdout.write(f'   Descuento monto: ${venta.descuento_monto or 0}')
        self.stdout.write(f'   Descuento %: {venta.descuento_porcentaje or 0}%')
        self.stdout.write(f'   Recargo monto: ${venta.recargo_monto or 0}')
        self.stdout.write(f'   Recargo %: {venta.recargo_porcentaje or 0}%')
        self.stdout.write('\n   Detalles actuales:')

        detalles = list(venta.detalles.filter(anulado_individualmente=False))
        for d in detalles:
            nombre = d.producto.nombre if d.producto else '(sin producto)'
            self.stdout.write(f'   - {nombre}: cantidad={d.cantidad}, precio={d.precio_unitario}, subtotal={d.subtotal}')

        if len(detalles) != 1:
            self.stderr.write(f'\n⚠️  La venta tiene {len(detalles)} detalles activos. Este comando asume 1 solo detalle.')
            self.stderr.write('   Revisá manualmente cuál corregir.')
            return

        detalle = detalles[0]
        subtotal_correcto = detalle.precio_unitario * cantidad_correcta

        # Recalcular total respetando descuentos/recargos originales
        desc_monto = venta.descuento_monto or Decimal('0.00')
        desc_pct   = venta.descuento_porcentaje or Decimal('0.00')
        rec_monto  = venta.recargo_monto or Decimal('0.00')
        rec_pct    = venta.recargo_porcentaje or Decimal('0.00')

        if desc_monto > 0:
            total_correcto = max(Decimal('0.00'), subtotal_correcto - desc_monto)
        elif desc_pct > 0:
            total_correcto = subtotal_correcto * (Decimal('1') - desc_pct / Decimal('100'))
        elif rec_monto > 0:
            total_correcto = subtotal_correcto + rec_monto
        elif rec_pct > 0:
            total_correcto = subtotal_correcto * (Decimal('1') + rec_pct / Decimal('100'))
        else:
            total_correcto = subtotal_correcto

        self.stdout.write(f'\n✏️  Correcciones a aplicar:')
        self.stdout.write(f'   detalle.cantidad: {detalle.cantidad} → {cantidad_correcta}')
        self.stdout.write(f'   detalle.subtotal: {detalle.subtotal} → {subtotal_correcto}')
        self.stdout.write(f'   venta.total:      {venta.total} → {total_correcto}')

        if dry_run:
            self.stdout.write('\n⚠️  DRY RUN: no se guardó nada. Corré sin --dry-run para aplicar.')
            return

        detalle.cantidad = cantidad_correcta
        detalle.subtotal = subtotal_correcto
        detalle.save(update_fields=['cantidad', 'subtotal'])

        venta.total = total_correcto
        venta.save(update_fields=['total'])

        self.stdout.write('\n✅ Corrección aplicada.')
