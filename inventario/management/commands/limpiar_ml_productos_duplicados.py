"""
Detecta y fusiona productos duplicados que quedaron sincronizados desde Mercado Libre
para un mismo ml_item_id (bug: dos métodos con el mismo nombre en MercadoLibreService
donde el segundo pisaba en silencio al primero, que era el atómico -- ver el commit que
agrega este comando para el detalle completo).

Uso:
    python manage.py limpiar_ml_productos_duplicados                # solo reporta (default)
    python manage.py limpiar_ml_productos_duplicados --aplicar      # fusiona de verdad
    python manage.py limpiar_ml_productos_duplicados --tienda slug  # acota a una tienda

Por defecto NO cambia nada en la base -- hace falta pasar --aplicar explícitamente.
Es más conservador que el resto de los comandos del proyecto a propósito: acá se están
fusionando y borrando productos con ventas/presupuestos/cambios reales enganchados.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Detecta y fusiona productos duplicados por ml_item_id (Mercado Libre)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--aplicar', action='store_true',
            help='Ejecuta la fusión de verdad. Sin este flag solo se reporta (dry-run).',
        )
        parser.add_argument(
            '--tienda', type=str, default=None,
            help='Nombre/slug de tienda para acotar la limpieza (default: todas).',
        )

    def handle(self, *args, **options):
        from inventario.models import (
            Producto, Tienda, DetalleVenta, DetallePresupuesto,
            ArancelMercadoLibreProducto,
        )
        try:
            from inventario.models import DetalleCambioDevolucion
        except ImportError:
            DetalleCambioDevolucion = None

        aplicar = options['aplicar']
        tienda_filtro = options.get('tienda')

        qs = Producto.objects.filter(ml_item_id__isnull=False).exclude(ml_item_id='')
        if tienda_filtro:
            tienda = Tienda.objects.filter(nombre=tienda_filtro).first()
            if not tienda:
                self.stderr.write(f"No se encontró la tienda '{tienda_filtro}'.")
                return
            qs = qs.filter(tienda=tienda)

        grupos = defaultdict(list)
        for p in qs.select_related('tienda').order_by('fecha_creacion'):
            grupos[(p.tienda_id, p.ml_item_id)].append(p)

        duplicados = {k: v for k, v in grupos.items() if len(v) > 1}

        if not duplicados:
            self.stdout.write(self.style.SUCCESS("No se encontraron productos duplicados por ml_item_id."))
            return

        modo = "APLICANDO" if aplicar else "DRY-RUN (nada se guarda)"
        self.stdout.write(f"\n{modo} -- {len(duplicados)} grupo(s) de productos duplicados encontrados.\n")

        total_fusionados = 0
        total_saltados = 0

        for (tienda_id, ml_item_id), productos in duplicados.items():
            tienda_nombre = productos[0].tienda.nombre

            # Por seguridad, no tocar grupos donde algún integrante sea parte de una
            # familia de variantes (padre o hijo) -- no debería pasar con productos de
            # ML, pero mejor no arriesgar ese feature acá.
            conflictivo = next(
                (p for p in productos if p.producto_padre_id or p.variantes.exists()),
                None,
            )
            if conflictivo:
                self.stdout.write(self.style.WARNING(
                    f"SALTEADO {tienda_nombre} / ml_item_id={ml_item_id}: "
                    f"el producto {conflictivo.id} es parte de una familia de variantes, revisar a mano."
                ))
                total_saltados += 1
                continue

            # Ganador: el que tenga más ventas relacionadas (historial real); empate -> más antiguo.
            ganador = max(
                productos,
                key=lambda p: (p.detalles_venta.count(), -productos.index(p)),
            )
            perdedores = [p for p in productos if p.id != ganador.id]

            # Stock final: el del integrante sincronizado más recientemente con ML (no la
            # suma -- son lecturas repetidas del mismo stock de ML, no cantidades separadas).
            mas_reciente = max(
                productos,
                key=lambda p: p.ml_ultima_sincronizacion or p.fecha_actualizacion,
            )
            stock_final = mas_reciente.stock

            self.stdout.write(
                f"\n{tienda_nombre} / ml_item_id={ml_item_id}: "
                f"{len(productos)} duplicados -> ganador \"{ganador.nombre}\" ({ganador.id})"
            )
            self.stdout.write(f"   stock final: {stock_final} (según sync más reciente de {mas_reciente.id})")

            ventas_repuntadas = sum(p.detalles_venta.count() for p in perdedores)
            presupuestos_repuntados = sum(p.detalles_presupuesto.count() for p in perdedores)
            cambios_repuntados = (
                sum(p.cambios_recibidos.count() for p in perdedores)
                if DetalleCambioDevolucion is not None else 0
            )
            self.stdout.write(
                f"   se repuntan: {ventas_repuntadas} línea(s) de venta, "
                f"{presupuestos_repuntados} línea(s) de presupuesto, "
                f"{cambios_repuntados} cambio(s)/devolución(es)"
            )
            for p in perdedores:
                self.stdout.write(f"   se borra: {p.id} (stock={p.stock}, creado={p.fecha_creacion:%d/%m/%Y})")

            if aplicar:
                with transaction.atomic():
                    for perdedor in perdedores:
                        # DetalleVenta tiene unique_together=('venta','producto'): si esa
                        # misma venta ya tiene una línea del ganador (podría pasar si la
                        # concurrencia que generó el duplicado también duplicó la línea de
                        # venta), no se puede repuntar sin violar la constraint -- se deja
                        # esa línea puntual, que al borrar el perdedor queda en NULL
                        # (SET_NULL) en vez de perder la venta entera.
                        for dv in DetalleVenta.objects.filter(producto=perdedor):
                            si_ya_existe = DetalleVenta.objects.filter(venta_id=dv.venta_id, producto=ganador).exists()
                            if si_ya_existe:
                                self.stdout.write(self.style.WARNING(
                                    f"   venta {dv.venta_id} ya tiene una línea del ganador; "
                                    f"la línea {dv.id} del perdedor {perdedor.id} queda sin producto (SET_NULL)."
                                ))
                                continue
                            dv.producto = ganador
                            dv.save(update_fields=['producto'])

                        DetallePresupuesto.objects.filter(producto=perdedor).update(producto=ganador)
                        if DetalleCambioDevolucion is not None:
                            DetalleCambioDevolucion.objects.filter(producto_nuevo=perdedor).update(producto_nuevo=ganador)

                        # unique_together=('tienda','producto'): si el ganador ya tiene su
                        # propio arancel, el del perdedor se descarta (cascade al borrarlo).
                        if not ArancelMercadoLibreProducto.objects.filter(tienda_id=tienda_id, producto=ganador).exists():
                            ArancelMercadoLibreProducto.objects.filter(producto=perdedor).update(producto=ganador)

                        perdedor.delete()

                    if ganador.stock != stock_final:
                        ganador.stock = stock_final
                    ganador.ml_sincronizado = True
                    ganador.save(update_fields=['stock', 'ml_sincronizado'])

            total_fusionados += 1

        self.stdout.write(
            f"\n{modo}: {total_fusionados} grupo(s) fusionado(s), {total_saltados} salteado(s).\n"
        )
        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "Nada se guardó. Corré con --aplicar para ejecutar la fusión de verdad."
            ))
