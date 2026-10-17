"""
Backfill puntual: genera la Venta (recibo, sin facturar -- ver
_facturar_cobro_suscripcion en views.py) de los cobros de Mercado Pago que
CobroMPSuscripcion ya tiene registrados pero que nunca pasaron por el
webhook real (estuvo roto hasta que se corrigió la validación de firma).
Sin esto, esos cobros quedan visibles en el panel de Clientes SaaS pero sin
ningún registro de venta/recibo en la tienda interna de Total Stock.

Idempotente: cada Venta que crea queda marcada con un
mp_authorized_payment_id sintético derivado del id del CobroMPSuscripcion
(no uno real de MP, porque no lo tenemos -- el webhook nunca llegó a
procesar esos pagos), así que correrlo de nuevo no duplica nada.

Uso:
    python manage.py backfill_recibos_cobros_mp              # mes actual
    python manage.py backfill_recibos_cobros_mp --anio 2026 --mes 10
    python manage.py backfill_recibos_cobros_mp --dry-run     # solo mostrar
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


def _payment_id_backfill(cobro):
    return f"backfill-cobro-mp-{cobro.id}"


class Command(BaseCommand):
    help = "Genera la Venta/recibo (sin facturar) de los cobros MP ya registrados en CobroMPSuscripcion que no tienen venta asociada."

    def add_arguments(self, parser):
        hoy = timezone.localdate()
        parser.add_argument('--anio', type=int, default=hoy.year)
        parser.add_argument('--mes', type=int, default=hoy.month)
        parser.add_argument('--dry-run', action='store_true', help="Solo mostrar qué se crearía, sin crear nada.")

    def handle(self, *args, **options):
        from inventario.models import CobroMPSuscripcion, Tienda, Venta, DetalleVenta, Producto, User

        anio = options['anio']
        mes = options['mes']
        dry_run = options['dry_run']

        nombre_tienda_facturacion = getattr(settings, 'TIENDA_SUSCRIPCIONES_NOMBRE', 'Total Stock')
        tienda_facturacion = Tienda.objects.filter(nombre=nombre_tienda_facturacion).first()
        if not tienda_facturacion:
            self.stdout.write(self.style.ERROR(
                f"No existe la tienda '{nombre_tienda_facturacion}' (TIENDA_SUSCRIPCIONES_NOMBRE) -- nada para hacer."
            ))
            return

        cobros = CobroMPSuscripcion.objects.filter(anio=anio, mes=mes).select_related('tienda').order_by('tienda__nombre')
        if not cobros.exists():
            self.stdout.write(f"No hay CobroMPSuscripcion para {mes:02d}/{anio}.")
            return

        usuario_sistema = None
        producto_suscripcion_cache = {}
        creadas = 0
        ya_existian = 0
        total_creado = Decimal('0')

        for cobro in cobros:
            payment_id = _payment_id_backfill(cobro)
            if Venta.objects.filter(tienda=tienda_facturacion, mp_authorized_payment_id=payment_id).exists():
                ya_existian += 1
                continue
            # También evita duplicar si YA existe una venta real (con el
            # payment_id verdadero de MP) para esta tienda en este mes --
            # ej. si el webhook ya arregló esto para cobros más recientes.
            if Venta.objects.filter(
                tienda=tienda_facturacion, tienda_cliente=cobro.tienda,
                origen_mp_suscripcion=True,
                fecha_venta__year=anio, fecha_venta__month=mes,
            ).exclude(mp_authorized_payment_id=payment_id).exists():
                self.stdout.write(f"  {cobro.tienda.nombre}: ya tiene una venta real este mes, se omite.")
                ya_existian += 1
                continue

            self.stdout.write(f"{'[DRY-RUN] ' if dry_run else ''}{cobro.tienda.nombre}: ${cobro.monto} ({cobro.fecha_cobro:%d/%m/%Y})")
            if dry_run:
                creadas += 1
                total_creado += cobro.monto
                continue

            if usuario_sistema is None:
                usuario_sistema, _ = User.objects.get_or_create(
                    username='mercadopago_suscripciones',
                    defaults={
                        'is_staff': False, 'is_active': True, 'tienda': tienda_facturacion,
                        'first_name': 'Mercado Pago', 'last_name': 'Suscripciones',
                    },
                )
            if tienda_facturacion.id not in producto_suscripcion_cache:
                producto_suscripcion_cache[tienda_facturacion.id], _ = Producto.objects.get_or_create(
                    tienda=tienda_facturacion, nombre='Suscripción Total Stock',
                    defaults={'precio': cobro.monto, 'stock': 0},
                )
            producto_suscripcion = producto_suscripcion_cache[tienda_facturacion.id]

            venta = Venta.objects.create(
                tienda=tienda_facturacion,
                usuario=usuario_sistema,
                total=cobro.monto,
                metodo_pago='Mercado Pago',
                mp_authorized_payment_id=payment_id,
                origen_mp_suscripcion=True,
                tienda_cliente=cobro.tienda,
                cliente_nombre=cobro.tienda.nombre,
                cliente_cuit=cobro.tienda.cuit or '',
            )
            DetalleVenta.objects.create(
                venta=venta, producto=producto_suscripcion,
                cantidad=1, precio_unitario=cobro.monto, subtotal=cobro.monto,
            )
            # fecha_venta es auto_now_add -- se pisa después para que quede la
            # fecha real del cobro (summarized.last_charged_date), no la de
            # hoy que es cuando se corrió este backfill.
            if cobro.fecha_cobro:
                Venta.objects.filter(pk=venta.pk).update(fecha_venta=cobro.fecha_cobro)

            creadas += 1
            total_creado += cobro.monto

        self.stdout.write(self.style.SUCCESS(
            f"\n{'Se crearían' if dry_run else 'Creadas'}: {creadas} venta(s) por un total de ${total_creado} "
            f"-- ya existían/omitidas: {ya_existian}."
        ))
