"""
Backfill de código de barras para productos que quedaron sin uno.

Motivado por un caso real: productos importados desde Tiendanube
(tn_import_products) que no traían SKU, o el propio bug de tn_import_products
que hasta hace poco no completaba codigo_barras al crear un producto nuevo
(ver el fix en TiendaViewSet.tn_import_products). Sin código de barras, el
Punto de Venta/impresión de etiquetas cae al fallback "PROD-{id}" (CODE128,
mucho más largo que un EAN13) -- en la hoja de etiquetas 4x9 esto se ve como
un código angosto/estirado, además de no poder escanearse con un lector real.

Este comando no está limitado a productos de Tiendanube: cualquier producto
vendible (no el "padre" de una familia de variantes, que no se vende directo)
sin codigo_barras cargado tiene el mismo problema, venga de donde venga
(carga masiva con la columna vacía, alta manual sin tildar "generar", etc.).
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, Exists, OuterRef

from inventario.models import Producto


class Command(BaseCommand):
    help = (
        "Genera un código de barras (EAN13) para productos vendibles que no tienen uno. "
        "Por defecto corre en modo dry-run (no guarda nada) -- pasar --confirmar para aplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmar', action='store_true',
            help='Guarda los cambios. Sin este flag, solo muestra qué se generaría (dry-run).',
        )
        parser.add_argument(
            '--tienda', type=str, default=None,
            help='Limitar a una tienda puntual por nombre (slug). Sin esto, corre sobre todas.',
        )

    def handle(self, *args, **options):
        from inventario.views import _generar_codigo_barras_unico

        confirmar = options['confirmar']
        tienda_nombre = options['tienda']

        # Excluir productos "padre" de una familia de variantes (tienen variantes
        # propias) -- no se venden directo, no aparecen en Punto de Venta ni se
        # imprimen, así que no necesitan código de barras.
        tiene_variantes = Producto.objects.filter(producto_padre_id=OuterRef('pk'))
        qs = (
            Producto.objects
            .filter(Q(codigo_barras__isnull=True) | Q(codigo_barras=''))
            .annotate(es_padre=Exists(tiene_variantes))
            .filter(es_padre=False)
            .select_related('tienda')
            .order_by('tienda__nombre', 'nombre')
        )
        if tienda_nombre:
            qs = qs.filter(tienda__nombre=tienda_nombre)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No hay productos sin código de barras. Nada para hacer."))
            return

        self.stdout.write(f"Productos sin código de barras encontrados: {total}")
        if not confirmar:
            self.stdout.write(self.style.WARNING("Modo dry-run (no se guarda nada) -- correr con --confirmar para aplicar.\n"))

        actualizados = 0
        for producto in qs.iterator():
            nuevo_codigo = _generar_codigo_barras_unico(producto.tienda)
            variante = f" ({producto.talle}{', ' + producto.variante2 if producto.variante2 else ''})" if producto.talle else ""
            self.stdout.write(f"  [{producto.tienda.nombre}] {producto.nombre}{variante} -> {nuevo_codigo}")
            if confirmar:
                producto.codigo_barras = nuevo_codigo
                producto.save(update_fields=['codigo_barras'])
                actualizados += 1

        if confirmar:
            self.stdout.write(self.style.SUCCESS(f"\nListo: {actualizados} producto(s) actualizados."))
        else:
            self.stdout.write(self.style.WARNING(f"\nDry-run: {total} producto(s) se actualizarían. Nada se guardó."))
