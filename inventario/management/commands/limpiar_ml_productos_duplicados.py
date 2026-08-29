"""
Detecta y fusiona productos duplicados que quedaron sincronizados desde Mercado Libre.

Dos causas distintas de duplicados, dos pasadas:
  1. Mismo ml_item_id exacto (bug: dos métodos con el mismo nombre en
     MercadoLibreService donde el segundo pisaba en silencio al primero, que era
     el atómico -- ver el commit que agrega este comando para el detalle completo).
  2. Publicaciones distintas agrupadas por el programa Catálogo de ML (comparten
     catalog_product_id): ML no permite variantes internas en productos de Catálogo,
     así que un producto con variantes termina con una publicación (ml_item_id) por
     cada una. Si hay una diferencia real de talle/color entre ellas se arma una
     familia padre+variantes; si no hay ninguna diferencia real, se fusionan en una
     sola (se elige la de más stock/ventas, el resto queda sin vincular localmente
     -- el usuario decide si las pausa en Mercado Libre).

Uso:
    python manage.py limpiar_ml_productos_duplicados                # solo reporta (default)
    python manage.py limpiar_ml_productos_duplicados --aplicar      # fusiona/arma familias de verdad
    python manage.py limpiar_ml_productos_duplicados --tienda slug  # acota a una tienda

Por defecto NO cambia nada en la base -- hace falta pasar --aplicar explícitamente.
Es más conservador que el resto de los comandos del proyecto a propósito: acá se están
fusionando y borrando productos con ventas/presupuestos/cambios reales enganchados.

La pasada 2 consulta la API de Mercado Libre en vivo (una request por publicación
todavía no clasificada) para conocer su catalog_product_id y attributes -- puede
tardar según cuántos productos tenga la tienda.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Detecta y fusiona productos duplicados de Mercado Libre (por ml_item_id y por Catálogo)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--aplicar', action='store_true',
            help='Ejecuta la fusión/creación de familias de verdad. Sin este flag solo se reporta (dry-run).',
        )
        parser.add_argument(
            '--tienda', type=str, default=None,
            help='Nombre/slug de tienda para acotar la limpieza (default: todas).',
        )

    def handle(self, *args, **options):
        from inventario.models import Producto, Tienda

        self.aplicar = options['aplicar']
        self.modo = "APLICANDO" if self.aplicar else "DRY-RUN (nada se guarda)"
        tienda_filtro = options.get('tienda')

        self.tienda_unica = None
        if tienda_filtro:
            self.tienda_unica = Tienda.objects.filter(nombre=tienda_filtro).first()
            if not self.tienda_unica:
                self.stderr.write(f"No se encontró la tienda '{tienda_filtro}'.")
                return

        qs_base = Producto.objects.filter(ml_item_id__isnull=False).exclude(ml_item_id='')
        if self.tienda_unica:
            qs_base = qs_base.filter(tienda=self.tienda_unica)

        self.stdout.write(f"\n{self.modo}\n")

        self.stdout.write("=== Pasada 1: duplicados por ml_item_id exacto ===")
        fusionados_1, saltados_1 = self._pasada_ml_item_id(qs_base)

        self.stdout.write("\n=== Pasada 2: publicaciones agrupadas por Catálogo de ML ===")
        fusionados_2, promovidos_2, saltados_2, errores_api = self._pasada_catalogo(qs_base)

        self.stdout.write(
            f"\n{self.modo}: {fusionados_1 + fusionados_2} grupo(s) fusionado(s), "
            f"{promovidos_2} familia(s) de variantes creada(s), "
            f"{saltados_1 + saltados_2} salteado(s), {errores_api} error(es) de API.\n"
        )
        if not self.aplicar:
            self.stdout.write(self.style.WARNING(
                "Nada se guardó. Corré con --aplicar para ejecutar de verdad."
            ))

    # ── Pasada 1: mismo ml_item_id exacto ───────────────────────────────────────

    def _pasada_ml_item_id(self, qs_base):
        grupos = defaultdict(list)
        for p in qs_base.select_related('tienda').order_by('fecha_creacion'):
            grupos[(p.tienda_id, p.ml_item_id)].append(p)
        duplicados = {k: v for k, v in grupos.items() if len(v) > 1}

        if not duplicados:
            self.stdout.write("Sin duplicados por ml_item_id exacto.")
            return 0, 0

        fusionados = saltados = 0
        for (tienda_id, ml_item_id), productos in duplicados.items():
            conflictivo = self._conflicto_familia(productos)
            if conflictivo:
                self.stdout.write(self.style.WARNING(
                    f"SALTEADO {productos[0].tienda.nombre} / ml_item_id={ml_item_id}: "
                    f"el producto {conflictivo.id} es parte de una familia de variantes, revisar a mano."
                ))
                saltados += 1
                continue
            self._fusionar_grupo(f"{productos[0].tienda.nombre} / ml_item_id={ml_item_id}", productos)
            fusionados += 1
        return fusionados, saltados

    # ── Pasada 2: agrupadas por catalog_product_id (Catálogo de ML) ────────────

    def _pasada_catalogo(self, qs_base):
        from inventario.services.mercadolibre_service import MercadoLibreService, ejes_candidatos_ml

        # Se re-consultan TODOS los productos con ml_item_id (no solo los que todavía no
        # tienen ml_catalog_product_id): una publicación nueva del mismo grupo puede
        # aparecer más tarde (import manual, nueva venta) sin que el resto del grupo
        # quede marcado de nuevo -- filtrar por ml_catalog_product_id vacío haría que esa
        # publicación nueva no se detecte contra sus hermanas ya clasificadas.
        candidatos = list(
            qs_base.select_related('tienda').order_by('tienda_id', 'fecha_creacion')
        )
        if not candidatos:
            self.stdout.write("Sin publicaciones para clasificar por Catálogo.")
            return 0, 0, 0, 0

        grupos = defaultdict(list)
        errores_api = 0
        servicios = {}
        for p in candidatos:
            svc = servicios.get(p.tienda_id)
            if svc is None:
                svc = MercadoLibreService(p.tienda)
                servicios[p.tienda_id] = svc
            try:
                item = svc.get_item(p.ml_item_id)
            except Exception as e:
                errores_api += 1
                self.stdout.write(self.style.WARNING(
                    f"   no se pudo consultar {p.ml_item_id} ({p.tienda.nombre}) en ML: {e} -- se saltea"
                ))
                continue
            catalog_id = (item or {}).get('catalog_product_id')
            if not catalog_id:
                continue
            p._ml_attributes = (item or {}).get('attributes')
            grupos[(p.tienda_id, catalog_id)].append(p)

        grupos = {k: v for k, v in grupos.items() if len(v) > 1}
        if not grupos:
            self.stdout.write("Sin publicaciones agrupables por catalog_product_id (con más de 1 c/u).")
            return 0, 0, 0, errores_api

        fusionados = promovidos = saltados = 0
        for (tienda_id, catalog_id), productos in grupos.items():
            conflictivo = self._conflicto_familia(productos)
            if conflictivo:
                self.stdout.write(self.style.WARNING(
                    f"SALTEADO {productos[0].tienda.nombre} / catalog_product_id={catalog_id}: "
                    f"el producto {conflictivo.id} es parte de una familia de variantes, revisar a mano."
                ))
                saltados += 1
                continue

            candidatos_por_producto = {
                p.id: ejes_candidatos_ml(getattr(p, '_ml_attributes', None)) for p in productos
            }
            valores_distintos = set(candidatos_por_producto.values())

            etiqueta = f"{productos[0].tienda.nombre} / catalog_product_id={catalog_id}"
            if len(valores_distintos) <= 1:
                # Todas las publicaciones del grupo tienen el mismo talle/variante2
                # candidato (o ninguna tiene atributo distinguible): no hay variante
                # real, se fusionan en una sola.
                self._fusionar_grupo(etiqueta, productos, catalog_id=catalog_id)
                fusionados += 1
            else:
                self._promover_familia_catalogo(etiqueta, catalog_id, productos, candidatos_por_producto)
                promovidos += 1

        return fusionados, promovidos, saltados, errores_api

    def _promover_familia_catalogo(self, etiqueta, catalog_id, productos, candidatos_por_producto):
        # Padre: el que tenga más ventas relacionadas (historial real); empate -> más stock.
        productos_ordenados = sorted(productos, key=lambda p: p.fecha_creacion)
        padre = max(
            productos,
            key=lambda p: (p.detalles_venta.count(), p.stock, -productos_ordenados.index(p)),
        )
        hijos = [p for p in productos if p.id != padre.id]

        self.stdout.write(f"\n{etiqueta}: {len(productos)} publicaciones con variante real -> familia")
        self.stdout.write(f"   padre: \"{padre.nombre}\" ({padre.id}, {padre.ml_item_id}) -- stock actual {padre.stock} se resetea a 0")
        for h in hijos:
            talle, variante2 = candidatos_por_producto[h.id]
            eje_str = ', '.join(filter(None, [talle, variante2])) or '(sin atributo distinguible)'
            self.stdout.write(f"   variante: \"{h.nombre}\" ({h.id}, {h.ml_item_id}) -> talle/variante2 = {eje_str}, stock={h.stock}")

        if self.aplicar:
            with transaction.atomic():
                padre.stock = 0
                padre.talle = None
                padre.variante2 = None
                padre.ml_catalog_product_id = catalog_id
                padre.save(update_fields=['stock', 'talle', 'variante2', 'ml_catalog_product_id'])

                for h in hijos:
                    talle, variante2 = candidatos_por_producto[h.id]
                    h.producto_padre = padre
                    h.nombre = padre.nombre
                    h.talle = talle
                    h.variante2 = variante2
                    h.ml_catalog_product_id = catalog_id
                    h.save(update_fields=['producto_padre', 'nombre', 'talle', 'variante2', 'ml_catalog_product_id'])

    # ── Compartido ───────────────────────────────────────────────────────────

    def _conflicto_familia(self, productos):
        """Por seguridad, no tocar grupos donde algún integrante ya sea parte de una
        familia de variantes previa (padre o hijo) ajena a esta limpieza."""
        return next((p for p in productos if p.producto_padre_id or p.variantes.exists()), None)

    def _fusionar_grupo(self, etiqueta, productos, catalog_id=None):
        from inventario.models import DetalleVenta, DetallePresupuesto, ArancelMercadoLibreProducto
        try:
            from inventario.models import DetalleCambioDevolucion
        except ImportError:
            DetalleCambioDevolucion = None

        productos_ordenados = sorted(productos, key=lambda p: p.fecha_creacion)
        # Ganador: el que tenga más ventas relacionadas (historial real); empate -> más antiguo.
        ganador = max(
            productos,
            key=lambda p: (p.detalles_venta.count(), -productos_ordenados.index(p)),
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
            f"\n{etiqueta}: {len(productos)} duplicados -> ganador \"{ganador.nombre}\" ({ganador.id})"
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
            self.stdout.write(f"   se ignora/borra: {p.id} (stock={p.stock}, creado={p.fecha_creacion:%d/%m/%Y})")

        if not self.aplicar:
            return

        with transaction.atomic():
            for perdedor in perdedores:
                # DetalleVenta tiene unique_together=('venta','producto'): si esa
                # misma venta ya tiene una línea del ganador (podría pasar si la
                # concurrencia que generó el duplicado también duplicó la línea de
                # venta), no se puede repuntar sin violar la constraint -- se deja
                # esa línea puntual, que al borrar el perdedor queda en NULL
                # (SET_NULL) en vez de perder la venta entera.
                for dv in DetalleVenta.objects.filter(producto=perdedor):
                    ya_existe = DetalleVenta.objects.filter(venta_id=dv.venta_id, producto=ganador).exists()
                    if ya_existe:
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
                if not ArancelMercadoLibreProducto.objects.filter(tienda_id=ganador.tienda_id, producto=ganador).exists():
                    ArancelMercadoLibreProducto.objects.filter(producto=perdedor).update(producto=ganador)

                perdedor.delete()

            if ganador.stock != stock_final:
                ganador.stock = stock_final
            ganador.ml_sincronizado = True
            update_fields = ['stock', 'ml_sincronizado']
            # Clave para que una publicación nueva del mismo grupo, descubierta más
            # adelante, se reconozca contra este ganador en vez de crearse suelta de
            # nuevo (el bug que generó este mismo caso: el ganador de una fusión
            # anterior se había quedado sin este campo).
            if catalog_id and ganador.ml_catalog_product_id != catalog_id:
                ganador.ml_catalog_product_id = catalog_id
                update_fields.append('ml_catalog_product_id')
            ganador.save(update_fields=update_fields)
