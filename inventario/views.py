# inventario/views.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/views.py
import base64
import logging
import secrets
import re
import threading
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status, pagination as rest_framework_pagination
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value, Subquery, OuterRef, Case, When
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import DecimalField 
from django.db import close_old_connections, models, transaction
from django.http import HttpResponse
from django.core.cache import cache
from io import BytesIO

logger = logging.getLogger(__name__)


def _registrar_accion(tienda, usuario, accion, detalle, objeto_id=None):
    try:
        HistorialAccion.objects.create(
            tienda=tienda, usuario=usuario,
            accion=accion, detalle=detalle, objeto_id=objeto_id,
        )
        # Limpiar registros con más de 90 días de esta tienda
        corte = timezone.now() - timedelta(days=90)
        HistorialAccion.objects.filter(tienda=tienda, fecha__lt=corte).delete()
    except Exception as e:
        logger.warning("No se pudo registrar historial accion '%s': %s", accion, e)


def _generar_codigo_barras_unico(tienda):
    """Genera un EAN13 (mismo criterio '779' + hash + checksum que ya usa el frontend
    al crear un producto sin código de barras), garantizando unicidad para la tienda."""
    import random
    for _ in range(20):
        base = '779' + ''.join(str(random.randint(0, 9)) for _ in range(9))
        suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
        checksum = (10 - (suma % 10)) % 10
        codigo = base + str(checksum)
        if not Producto.objects.filter(tienda=tienda, codigo_barras=codigo).exists():
            return codigo
    # Extremadamente improbable: fallback determinístico único
    import uuid as _uuid
    return '779' + str(_uuid.uuid4().int)[:10]


def _clonar_producto_a_tienda(producto, tienda, producto_padre, stock):
    """Crea en `tienda` un producto equivalente a `producto` (mismo nombre/talle/precio/etc),
    usado cuando una transferencia de stock no encuentra un producto ya existente en destino."""
    codigo_barras = producto.codigo_barras
    if codigo_barras and Producto.objects.filter(tienda=tienda, codigo_barras=codigo_barras).exists():
        # Evita romper el unique_together ('codigo_barras', 'tienda') si por casualidad
        # ya hay otro producto con ese código en la tienda destino.
        codigo_barras = None
    rubro_destino = None
    if producto.rubro_id:
        rubro_destino = Rubro.objects.filter(tienda=tienda, nombre=producto.rubro.nombre).first()
    return Producto.objects.create(
        nombre=producto.nombre,
        descripcion=producto.descripcion,
        precio=producto.precio,
        costo=producto.costo,
        talle=producto.talle,
        stock=stock,
        iva_porcentaje=producto.iva_porcentaje,
        codigo_barras=codigo_barras,
        rubro=rubro_destino,
        producto_padre=producto_padre,
        tienda=tienda,
    )


def _transferir_unidad(producto_origen, tienda_destino, cantidad, padre_destino_cache=None):
    """Resta `cantidad` de producto_origen.stock y la suma en el producto equivalente de
    `tienda_destino` (matcheando por codigo_barras o nombre+talle), creándolo si no existe.
    Si producto_origen es una variante, resuelve/crea también su padre en destino para no
    romper la agrupación de variantes. Devuelve (producto_destino, creado: bool)."""
    if padre_destino_cache is None:
        padre_destino_cache = {}

    if producto_origen.producto_padre_id:
        padre_origen = producto_origen.producto_padre
        padre_destino = padre_destino_cache.get(padre_origen.id)
        if padre_destino is None:
            padre_destino = Producto.objects.filter(
                tienda=tienda_destino, producto_padre__isnull=True, nombre__iexact=padre_origen.nombre,
            ).first()
            if padre_destino is None:
                padre_destino = _clonar_producto_a_tienda(padre_origen, tienda_destino, None, 0)
            padre_destino_cache[padre_origen.id] = padre_destino

        variante_destino = None
        if producto_origen.codigo_barras:
            variante_destino = Producto.objects.filter(
                tienda=tienda_destino, producto_padre=padre_destino, codigo_barras=producto_origen.codigo_barras,
            ).first()
        if variante_destino is None:
            variante_destino = Producto.objects.filter(
                tienda=tienda_destino, producto_padre=padre_destino, talle=producto_origen.talle,
            ).first()

        if variante_destino:
            variante_destino.stock = (variante_destino.stock or 0) + cantidad
            variante_destino.save(update_fields=['stock'])
            creado = False
        else:
            variante_destino = _clonar_producto_a_tienda(producto_origen, tienda_destino, padre_destino, cantidad)
            creado = True
        producto_destino = variante_destino
    else:
        match = None
        if producto_origen.codigo_barras:
            match = Producto.objects.filter(tienda=tienda_destino, codigo_barras=producto_origen.codigo_barras).first()
        if match is None:
            match = Producto.objects.filter(
                tienda=tienda_destino, producto_padre__isnull=True,
                nombre__iexact=producto_origen.nombre, talle=producto_origen.talle,
            ).first()
        if match:
            match.stock = (match.stock or 0) + cantidad
            match.save(update_fields=['stock'])
            creado = False
        else:
            match = _clonar_producto_a_tienda(producto_origen, tienda_destino, None, cantidad)
            creado = True
        producto_destino = match

    producto_origen.stock = (producto_origen.stock or 0) - cantidad
    producto_origen.save(update_fields=['stock'])
    return producto_destino, creado


try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import barcode
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

# CAMBIO 1: Importar ArancelMetodoTienda y ArancelMercadoLibre (con importación condicional)
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, CompraStock, ArancelMetodoTienda, CategoriaMercadoLibre, Factura, NotaCredito, CierreCaja, EgresoCaja, HistorialAccion, Cliente, MovimientoCuentaCorriente, Rubro, Presupuesto, DetallePresupuesto

# Importación condicional de ArancelMercadoLibre (puede no existir si la migración no se ha aplicado)
try:
    from .models import ArancelMercadoLibre
except ImportError:
    ArancelMercadoLibre = None
    logger.warning("⚠️ ArancelMercadoLibre no está disponible. Aplica la migración 0019_arancel_mercado_libre.")
# Importación condicional para CambioDevolucion
# Intentar importar directamente - si falla, los modelos no están disponibles
try:
    from .models import CambioDevolucion, DetalleCambioDevolucion
    logger.info("✅ Modelos CambioDevolucion y DetalleCambioDevolucion importados directamente")
except ImportError as e:
    logger.warning(f"⚠️ No se pudieron importar CambioDevolucion y DetalleCambioDevolucion: {e}")
    CambioDevolucion = None
    DetalleCambioDevolucion = None

def _get_cambio_devolucion_models():
    """
    Función auxiliar para obtener los modelos CambioDevolucion y DetalleCambioDevolucion.
    Se llama cuando se necesitan los modelos, no al momento de importar el módulo.
    """
    global CambioDevolucion, DetalleCambioDevolucion
    
    # Si ya están importados, retornarlos
    if CambioDevolucion is not None and DetalleCambioDevolucion is not None:
        return CambioDevolucion, DetalleCambioDevolucion
    
    # Intentar obtener usando apps.get_model() (la forma más segura)
    try:
        from django.apps import apps
        CambioDevolucion = apps.get_model('inventario', 'CambioDevolucion')
        DetalleCambioDevolucion = apps.get_model('inventario', 'DetalleCambioDevolucion')
        logger.info("✅ Modelos CambioDevolucion y DetalleCambioDevolucion obtenidos con apps.get_model()")
        return CambioDevolucion, DetalleCambioDevolucion
    except LookupError:
        logger.warning("⚠️ apps.get_model() falló - los modelos no están registrados en Django")
        # Si apps.get_model falla, los modelos no están registrados
        # Verificar si las tablas existen para dar un mensaje más útil
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                if connection.vendor == 'postgresql':
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name IN ('inventario_cambiodevolucion', 'inventario_detallecambiodevolucion')
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                else:
                    table_names = connection.introspection.table_names()
                    tables = [t for t in table_names if t in ('inventario_cambiodevolucion', 'inventario_detallecambiodevolucion')]
                
                if 'inventario_cambiodevolucion' in tables and 'inventario_detallecambiodevolucion' in tables:
                    logger.error("❌ CRÍTICO: Las tablas existen pero los modelos no están registrados en Django. Esto indica que los modelos no están siendo definidos correctamente en models.py o hay un error de sintaxis que impide su registro.")
                else:
                    logger.warning(f"⚠️ Tablas no encontradas. Ejecuta: python manage.py migrate inventario 0013")
        except Exception as e:
            logger.error(f"❌ Error verificando tablas: {e}", exc_info=True)
    
    return None, None
from django.core.exceptions import ObjectDoesNotExist 
# CAMBIO 2: Importar ArancelMetodoTiendaSerializer
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer, CompraStockSerializer, CompraStockCreateSerializer, ArancelMetodoTiendaSerializer,
    FacturaSerializer, EmitirFacturaSerializer,
    NotaCreditoSerializer, EmitirNotaCreditoSerializer,
    UserCreateSerializer, UserUpdateSerializer, ChangePasswordSerializer,
    ArancelMetodoTiendaCreateSerializer,
    CierreCajaSerializer, EgresoCajaSerializer,
    ClienteSerializer, MovimientoCuentaCorrienteSerializer,
    calcular_saldo_pendiente, obtener_deuda_vencida_info,
    RubroSerializer,
    PresupuestoSerializer, PresupuestoCreateSerializer,
)
# Importación condicional de serializers de ArancelMercadoLibre
try:
    from .serializers import ArancelMercadoLibreSerializer, ArancelMercadoLibreCreateSerializer
except ImportError:
    ArancelMercadoLibreSerializer = None
    ArancelMercadoLibreCreateSerializer = None
    logger.warning("⚠️ Serializers de ArancelMercadoLibre no están disponibles. Aplica la migración 0019_arancel_mercado_libre.")
# Importación ArancelMercadoLibreProducto (por producto: arancel % + costo envío)
try:
    from .models import ArancelMercadoLibreProducto
    from .serializers import ArancelMercadoLibreProductoSerializer, ArancelMercadoLibreProductoCreateSerializer
except (ImportError, AttributeError):
    ArancelMercadoLibreProducto = None
    ArancelMercadoLibreProductoSerializer = None
    ArancelMercadoLibreProductoCreateSerializer = None
# Importación condicional de serializers de CambioDevolucion
# Primero importar normalmente
try:
    from .serializers import CambioDevolucionSerializer, CambioDevolucionCreateSerializer, DetalleCambioDevolucionSerializer
except (ImportError, AttributeError):
    CambioDevolucionSerializer = None
    CambioDevolucionCreateSerializer = None
    DetalleCambioDevolucionSerializer = None

# Si los modelos existen después de la importación, verificar y potencialmente forzar reimportación
if CambioDevolucion is not None and DetalleCambioDevolucion is not None:
    from rest_framework import serializers as drf_serializers
    try:
        # Verificar si los serializers son dummy (Serializer) en lugar de reales (ModelSerializer)
        if (CambioDevolucionSerializer is not None and
            not issubclass(CambioDevolucionSerializer, drf_serializers.ModelSerializer)):
            # Los serializers son dummy, necesitamos forzar reimportación
            logger.warning("Serializers de CambioDevolucion son dummy, forzando reimportación...")
            import importlib
            import inventario.serializers as serializers_module
            importlib.reload(serializers_module)
            # Reimportar después del reload
            from inventario.serializers import CambioDevolucionSerializer, CambioDevolucionCreateSerializer, DetalleCambioDevolucionSerializer
            logger.info("✅ Serializers de CambioDevolucion reimportados correctamente")
    except (TypeError, AttributeError, ImportError) as e:
        logger.warning(f"Error al verificar/reimportar serializers: {e}")
# Importar modelos de facturación
from .models import Factura
from .services.facturacion_service import FacturacionService
from .filters import VentaFilter 

# Clase de permiso personalizada que permite tanto is_superuser como is_staff
class IsAdminOrSuperUser(BasePermission):
    """
    Permiso personalizado que permite acceso a usuarios que sean superusuarios O staff.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and 
                   (request.user.is_superuser or request.user.is_staff))


def _get_tiendas_ids_usuario(user):
    """PKs de todas las tiendas a las que el usuario tiene acceso (tienda principal + autorizadas)."""
    tiendas_ids = list(user.tiendas_autorizadas.values_list('pk', flat=True))
    if user.tienda:
        tiendas_ids.append(user.tienda.pk)
    return tiendas_ids


def _resolver_tienda_por_slug(request):
    """
    Resuelve la tienda efectiva para endpoints scoped-por-tienda que no son un
    ModelViewSet (suscripción, datos básicos de tienda), igual que el resto de
    la app: prioriza `tienda_slug` (querystring o body) para que un
    superuser/staff operando sobre una tienda autorizada distinta a la propia
    (vía selectedStoreSlug en el frontend) actúe sobre esa tienda y no sobre
    `user.tienda`. Si no viene `tienda_slug`, cae a `user.tienda`.
    """
    user = request.user
    tienda_slug = request.query_params.get('tienda_slug') or request.data.get('tienda_slug')
    if not tienda_slug:
        return user.tienda
    if user.is_superuser:
        return Tienda.objects.filter(nombre=tienda_slug).first()
    tiendas_ids = _get_tiendas_ids_usuario(user)
    return Tienda.objects.filter(nombre=tienda_slug, pk__in=tiendas_ids).first()


class ProductoPagination(rest_framework_pagination.PageNumberPagination):
    """Paginación de productos: 10 por página por defecto (comportamiento actual),
    pero acepta ?page_size= para casos puntuales que necesitan traer un lote grande
    de una sola vez (ej. 'seleccionar todos' para imprimir etiquetas de un rubro
    completo, que puede abarcar muchas más de 10 filas)."""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 5000  # mismo tope que carga_masiva, por la misma razón (memoria del navegador)


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ProductoPagination
    filter_backends = [DjangoFilterBackend]

    def _resolver_tienda(self, tienda_slug=None):
        """Devuelve el objeto Tienda autorizado para el usuario actual.
        Para superusers: cualquier tienda por slug.
        Para staff: tienda principal o cualquiera en tiendas_autorizadas.
        """
        user = self.request.user
        if user.is_superuser:
            if tienda_slug:
                return Tienda.objects.filter(nombre=tienda_slug).first()
            return user.tienda
        # Staff con tiendas autorizadas
        tiendas_ok = user.tiendas_autorizadas.all()
        if user.tienda:
            tiendas_ok = tiendas_ok | Tienda.objects.filter(pk=user.tienda.pk)
        if tienda_slug:
            return tiendas_ok.filter(nombre=tienda_slug).first()
        return user.tienda

    def get_object(self):
        """Permite retrieve/update/delete sobre variantes (tienen producto_padre),
        que están excluidas del queryset de lista para no ocupar slots de paginación."""
        pk = self.kwargs.get('pk')
        if pk:
            obj = get_object_or_404(Producto, pk=pk)
            self.check_object_permissions(self.request, obj)
            return obj
        return super().get_object()

    def get_queryset(self):
        user = self.request.user
        # Solo productos raíz (sin padre): las variantes vienen anidadas en 'variantes'.
        # Esto evita que variantes ocupen slots de paginación y desplacen el padre a la pág 2.
        queryset = Producto.objects.select_related('tienda').prefetch_related('variantes').filter(producto_padre__isnull=True).distinct()
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        rubro_id = self.request.query_params.get('rubro_id', None)
        if rubro_id:
            queryset = queryset.filter(rubro_id=rubro_id)

        # Nombre/talle: coincidencia parcial (para buscar escribiendo el nombre).
        # Códigos: coincidencia exacta — un código parcial (ej. escanear "ALB125" cuando
        # existen "ALB1250", "ALB1251", etc.) no debe traer todos los que empiezan igual,
        # solo el producto/variante cuyo código sea idéntico al buscado.
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(nombre__icontains=search) |
                Q(talle__icontains=search) |
                Q(codigo_barras__iexact=search) |
                Q(codigo_interno__iexact=search) |
                Q(variantes__codigo_barras__iexact=search) |
                Q(variantes__codigo_interno__iexact=search)
            ).distinct()

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug).order_by('nombre')
            return queryset.order_by('nombre')

        # Staff: puede ver productos de su tienda principal Y de las autorizadas
        tiendas_ids = list(user.tiendas_autorizadas.values_list('pk', flat=True))
        if user.tienda:
            tiendas_ids.append(user.tienda.pk)

        if tienda_slug:
            # Verificar que el slug sea una tienda autorizada
            if Tienda.objects.filter(nombre=tienda_slug, pk__in=tiendas_ids).exists():
                return queryset.filter(tienda__nombre=tienda_slug).order_by('nombre')
            return Producto.objects.none()

        if tiendas_ids:
            return queryset.filter(tienda__pk__in=tiendas_ids).order_by('nombre')
        return Producto.objects.none()

    def perform_create(self, serializer):
        tienda_slug = self.request.data.get('tienda_slug')
        tienda = self._resolver_tienda(tienda_slug)
        if not tienda:
            tienda = self.request.user.tienda
        serializer.save(tienda=tienda)

    def perform_update(self, serializer):
        if self.request.user.is_supervisor and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            campos_enviados = set(self.request.data.keys())
            if not campos_enviados.issubset({'stock'}):
                raise PermissionDenied("Los supervisores no pueden editar productos.")

        nuevo_stock = serializer.validated_data.get('stock')
        instancia = serializer.instance
        if nuevo_stock is not None and nuevo_stock != (instancia.stock or 0):
            talle_str = f' (T: {instancia.talle})' if instancia.talle else ''
            stock_anterior = instancia.stock or 0
            if nuevo_stock > stock_anterior:
                serializer.save(
                    stock_ultimo_ingreso=nuevo_stock,
                    fecha_ultimo_ingreso=timezone.now(),
                )
                diff = nuevo_stock - stock_anterior
                _registrar_accion(
                    tienda=instancia.tienda,
                    usuario=self.request.user,
                    accion='ingreso_stock',
                    detalle=f'Ingreso +{diff} · {instancia.nombre}{talle_str} · stock anterior: {stock_anterior} → nuevo: {nuevo_stock}',
                    objeto_id=instancia.id,
                )
            else:
                serializer.save(
                    stock_ultimo_ingreso=nuevo_stock,
                    fecha_ultimo_ingreso=timezone.now(),
                )
                diff = stock_anterior - nuevo_stock
                _registrar_accion(
                    tienda=instancia.tienda,
                    usuario=self.request.user,
                    accion='ajuste_stock',
                    detalle=f'Ajuste -{diff} · {instancia.nombre}{talle_str} · stock anterior: {stock_anterior} → nuevo: {nuevo_stock}',
                    objeto_id=instancia.id,
                )
        else:
            serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.is_supervisor and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Los supervisores no pueden eliminar productos.")
        instance.variantes.all().delete()
        instance.delete()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def productos_sin_codigo(self, request):
        productos = self.get_queryset().filter(codigo_barras__isnull=True)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        codigo = request.query_params.get('barcode', None)
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if not codigo or not tienda_slug:
            return Response({"detail": "Código de barras y slug de tienda son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)

        producto = Producto.objects.filter(codigo_barras=codigo, tienda__nombre=tienda_slug).first()
        if not producto:
            # Permite tipear/escanear el Código Interno (el de la carga masiva) en el
            # mismo buscador rápido, no solo el código de barras.
            producto = Producto.objects.filter(codigo_interno=codigo, tienda__nombre=tienda_slug).first()
        if not producto:
            return Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(producto)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='nombre_por_barcode')
    def nombre_por_barcode(self, request):
        """Busca el nombre de un producto por código de barras en CUALQUIER tienda."""
        codigo = request.query_params.get('barcode', None)
        if not codigo:
            return Response({"detail": "Parámetro barcode es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        producto = Producto.objects.filter(codigo_barras=codigo).first()
        if not producto:
            return Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"nombre": producto.nombre})

    @action(detail=False, methods=['get'])
    def productos_con_stock(self, request):
        productos = self.get_queryset().filter(stock__gt=0)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='editar_masivo')
    def editar_masivo(self, request):
        """
        Edición masiva de precio/IVA para todos los productos (y variantes) de un rubro.
        Body: {tienda_slug, rubro_id, modo: 'iva'|'margen'|'ajuste_precio', valor}
          - iva: fija iva_porcentaje = valor para todos los productos del rubro.
          - margen: recalcula precio = costo_con_iva * (1 + valor%) usando el IVA actual
            de cada producto (se salta los que no tienen costo cargado).
          - ajuste_precio: aplica un % de aumento (positivo) o baja (negativo) sobre el
            precio actual de cada producto, sin tocar costo ni IVA.
        """
        from decimal import InvalidOperation

        if self.request.user.is_supervisor and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Los supervisores no pueden editar precios de productos.")

        tienda_slug = request.data.get('tienda_slug')
        rubro_id = request.data.get('rubro_id')
        modo = request.data.get('modo')
        valor = request.data.get('valor')

        if not tienda_slug or not rubro_id or modo not in ('iva', 'margen', 'ajuste_precio') or valor is None:
            return Response(
                {"error": "Faltan parámetros: tienda_slug, rubro_id, modo ('iva'|'margen'|'ajuste_precio') y valor."},
                status=status.HTTP_400_BAD_REQUEST
            )

        tienda = self._resolver_tienda(tienda_slug)
        if not tienda:
            return Response({"error": "Tienda no encontrada o no autorizada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            valor_decimal = Decimal(str(valor))
        except (InvalidOperation, TypeError):
            return Response({"error": "Valor inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if not Rubro.objects.filter(id=rubro_id, tienda=tienda).exists():
            return Response({"error": "Rubro no encontrado en esta tienda."}, status=status.HTTP_404_NOT_FOUND)

        productos = Producto.objects.filter(tienda=tienda, rubro_id=rubro_id)
        actualizados = 0
        omitidos = 0

        if modo == 'iva':
            if valor_decimal < 0 or valor_decimal > 100:
                return Response({"error": "El IVA debe estar entre 0 y 100%."}, status=status.HTTP_400_BAD_REQUEST)
            actualizados = productos.update(iva_porcentaje=valor_decimal)
        elif modo == 'margen':
            for producto in productos:
                if producto.costo is None:
                    omitidos += 1
                    continue
                iva_actual = producto.iva_porcentaje or Decimal('0.00')
                costo_con_iva = producto.costo * (Decimal('1') + iva_actual / Decimal('100'))
                nuevo_precio = costo_con_iva * (Decimal('1') + valor_decimal / Decimal('100'))
                producto.precio = max(Decimal('0.00'), nuevo_precio).quantize(Decimal('0.01'))
                producto.save(update_fields=['precio'])
                actualizados += 1
        elif modo == 'ajuste_precio':
            for producto in productos:
                nuevo_precio = producto.precio * (Decimal('1') + valor_decimal / Decimal('100'))
                producto.precio = max(Decimal('0.00'), nuevo_precio).quantize(Decimal('0.01'))
                producto.save(update_fields=['precio'])
                actualizados += 1

        return Response({'actualizados': actualizados, 'omitidos': omitidos})

    @action(detail=False, methods=['get'], url_path='exportar')
    def exportar(self, request):
        """
        Devuelve todos los productos de la tienda en el mismo formato de columnas que
        la plantilla de carga masiva, para poder descargarlos y volver a importarlos
        (por ejemplo, en otra tienda). El armado del .xlsx se hace en el frontend con
        la librería xlsx, igual que la plantilla vacía.

        La plantilla de importación no soporta variantes (no tiene columna Talle), así
        que cada variante se exporta como fila propia con el talle agregado al nombre
        (ej. "Remera - M") para no perder datos ni chocar con la restricción de
        nombre+talle único; al reimportar quedan como productos sueltos, no agrupados
        bajo un padre.

        'Código Interno' solo se completa cuando el producto se creó (o se repuso) por
        carga masiva; los cargados a mano desde Gestión de Productos no tienen uno
        asignado. Como la importación exige ese campo, acá se genera uno automático
        para esos casos (a partir del id del producto, así queda estable si se vuelve a
        exportar) verificando que no choque con ningún código interno ya existente en
        la tienda ni con otro generado en esta misma exportación.
        """
        tienda_slug = request.query_params.get('tienda_slug')
        tienda = self._resolver_tienda(tienda_slug)
        if not tienda:
            return Response({"error": "Tienda no encontrada o no autorizada."}, status=status.HTTP_404_NOT_FOUND)

        productos = Producto.objects.filter(tienda=tienda).select_related('rubro').prefetch_related('variantes').order_by('nombre')

        codigos_existentes = set(
            Producto.objects.filter(tienda=tienda)
            .exclude(codigo_interno__isnull=True).exclude(codigo_interno='')
            .values_list('codigo_interno', flat=True)
        )
        codigos_generados = set()

        def _generar_codigo_interno_unico(producto):
            base = 'AUTO' + str(producto.id).replace('-', '')[:10].upper()
            candidato = base
            sufijo = 1
            while candidato in codigos_existentes or candidato in codigos_generados:
                sufijo += 1
                candidato = f"{base}-{sufijo}"
            codigos_generados.add(candidato)
            return candidato

        filas = []
        for producto in productos:
            # Los "padre" que solo agrupan variantes no son un producto vendible en sí:
            # no se exportan como fila propia, sus variantes ya se exportan por separado.
            if producto.producto_padre_id is None and producto.variantes.exists():
                continue

            nombre = producto.nombre
            if producto.producto_padre_id is not None and producto.talle:
                nombre = f"{nombre} - {producto.talle}"

            codigo_interno = producto.codigo_interno or _generar_codigo_interno_unico(producto)

            filas.append({
                'codigo_interno': codigo_interno,
                'nombre': nombre,
                'rubro': producto.rubro.nombre if producto.rubro_id else '',
                'iva_porcentaje': str(producto.iva_porcentaje) if producto.iva_porcentaje is not None else '',
                'costo': str(producto.costo) if producto.costo is not None else '',
                'precio_venta': str(producto.precio) if producto.precio is not None else '',
                'margen_porcentaje': '',
                'cantidad': producto.stock,
                'codigo_barras': producto.codigo_barras or '',
            })

        return Response({'productos': filas, 'count': len(filas)})

    @action(detail=False, methods=['post'], url_path='carga_masiva')
    def carga_masiva(self, request):
        """
        Carga masiva de productos desde Excel/CSV (el parseo del archivo ocurre en el
        frontend; acá se recibe la lista de filas ya estructurada).

        Body: {
            tienda_slug, modo: 'preview' | 'confirmar',
            filas: [{
                fila, codigo_interno, nombre, rubro, iva_porcentaje,
                costo, precio_venta, margen_porcentaje, cantidad, codigo_barras,
            }, ...]
        }

        Por fila: si 'codigo_interno' ya existe en la tienda -> reposición (suma stock,
        actualiza costo/precio/iva). Si no existe -> crea el producto. El precio de
        venta se prioriza si viene en la fila; si no, se calcula como
        costo * (1 + iva/100) * (1 + margen/100). Cada fila se procesa de forma
        independiente (un error en una fila no aborta el resto).
        """
        tienda_slug = request.data.get('tienda_slug')
        modo = request.data.get('modo', 'preview')
        filas = request.data.get('filas') or []
        # Permite re-subir el mismo archivo para corregir precio/IVA/rubro de
        # productos ya existentes sin volver a sumarles stock (por ejemplo si un
        # import anterior no guardó bien el rubro). Por default se comporta igual
        # que siempre: reposición suma la cantidad de la fila al stock.
        actualizar_stock = request.data.get('actualizar_stock', True)

        if modo not in ('preview', 'confirmar'):
            return Response({'error': "El modo debe ser 'preview' o 'confirmar'."}, status=status.HTTP_400_BAD_REQUEST)

        tienda = self._resolver_tienda(tienda_slug)
        if not tienda:
            return Response({'error': 'No se pudo determinar la tienda.'}, status=status.HTTP_400_BAD_REQUEST)

        if not filas:
            return Response({'error': 'No se recibieron filas para procesar.'}, status=status.HTTP_400_BAD_REQUEST)

        # Se resuelven de una sola vez (en vez de una consulta por fila) para evitar
        # timeouts del worker con archivos grandes: contra una base remota, N filas
        # con 1-2 queries cada una suman varios segundos de latencia de red y superan
        # el timeout de gunicorn mucho antes de llegar a procesar todo el archivo.
        productos_existentes_por_codigo = {
            p.codigo_interno: p
            for p in Producto.objects.filter(tienda=tienda)
            .exclude(codigo_interno__isnull=True).exclude(codigo_interno='')
        }
        rubros_por_nombre = {
            r.nombre.strip().lower(): r
            for r in Rubro.objects.filter(tienda=tienda)
        }
        # Si una fila trae un rubro que todavía no existe en la tienda pero también
        # trae el IVA explícito en su propia columna, se crea el rubro con ese IVA en
        # vez de dejarlo sin resolver: el frontend solo pide asignar IVA manualmente a
        # los rubros nuevos cuando el archivo NO trae IVA por fila (ver
        # resolverRubros() en CargaMasivaProductos.js), así que si ambas columnas
        # vienen completas (por ejemplo un archivo generado con "Exportar", que
        # siempre completa las dos) el rubro quedaba sin crear y sin guardar en el
        # producto, sin ningún error visible.
        if modo == 'confirmar':
            from decimal import InvalidOperation
            for fila in filas:
                rubro_nombre = str(fila.get('rubro') or '').strip()
                if not rubro_nombre or rubro_nombre.lower() in rubros_por_nombre:
                    continue
                iva_raw = fila.get('iva_porcentaje')
                if iva_raw is None or str(iva_raw).strip() == '':
                    continue
                try:
                    iva_valor = Decimal(str(iva_raw))
                except (InvalidOperation, ValueError):
                    continue
                rubro_obj, _ = Rubro.objects.get_or_create(
                    tienda=tienda, nombre=rubro_nombre, defaults={'iva_porcentaje': iva_valor}
                )
                rubros_por_nombre[rubro_nombre.lower()] = rubro_obj
        # Códigos de barras ya usados en la tienda, para generar los nuevos en memoria
        # (import por import) en vez de una query de verificación por producto nuevo.
        codigos_barras_vistos = set(
            Producto.objects.filter(tienda=tienda)
            .exclude(codigo_barras__isnull=True).exclude(codigo_barras='')
            .values_list('codigo_barras', flat=True)
        )

        def _generar_codigo_barras_en_memoria():
            import random
            import uuid as _uuid
            for _ in range(30):
                base = '779' + ''.join(str(random.randint(0, 9)) for _ in range(9))
                suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
                checksum = (10 - (suma % 10)) % 10
                codigo = base + str(checksum)
                if codigo not in codigos_barras_vistos:
                    codigos_barras_vistos.add(codigo)
                    return codigo
            codigo = '779' + str(_uuid.uuid4().int)[:10]
            codigos_barras_vistos.add(codigo)
            return codigo

        codigos_vistos = {}
        resultados = []
        # En modo 'confirmar' no se escribe a la DB fila por fila (eso es lo que
        # provocaba WORKER TIMEOUT con archivos de miles de filas: cada
        # Producto.objects.create()/save() es un round-trip aparte contra una DB
        # remota). Se acumulan acá y se escriben con bulk_create/bulk_update al
        # final, en lotes.
        productos_a_crear = []
        productos_a_actualizar = []

        for idx, fila in enumerate(filas, start=1):
            numero_fila = fila.get('fila', idx)
            try:
                codigo_interno = str(fila.get('codigo_interno') or '').strip()
                nombre = str(fila.get('nombre') or '').strip()
                costo_raw = fila.get('costo')
                precio_venta_raw = fila.get('precio_venta')
                margen_raw = fila.get('margen_porcentaje')
                cantidad_raw = fila.get('cantidad')
                rubro_nombre = str(fila.get('rubro') or '').strip()
                iva_raw = fila.get('iva_porcentaje')
                codigo_barras = str(fila.get('codigo_barras') or '').strip() or None

                if not codigo_interno:
                    raise ValueError("Falta 'Código Interno'.")
                if codigo_interno in codigos_vistos:
                    raise ValueError(f"Código interno duplicado en el archivo (fila {codigos_vistos[codigo_interno]}).")
                codigos_vistos[codigo_interno] = numero_fila

                if not nombre:
                    raise ValueError("Falta 'Nombre'.")

                if costo_raw is None or str(costo_raw).strip() == '':
                    raise ValueError("Falta 'Costo'.")
                costo = Decimal(str(costo_raw))
                if costo <= 0:
                    raise ValueError("El costo debe ser mayor a 0.")

                if cantidad_raw is None or str(cantidad_raw).strip() == '':
                    cantidad = 0
                else:
                    cantidad = int(float(cantidad_raw))
                if cantidad < 0:
                    raise ValueError("La cantidad no puede ser negativa.")

                # Se resuelve el rubro siempre que venga en la fila (para vincular
                # Producto.rubro), independientemente de si el IVA sale de él o vino
                # explícito en la fila.
                rubro = rubros_por_nombre.get(rubro_nombre.lower()) if rubro_nombre else None

                # Resolver IVA: si el rubro ya existe en la tienda (o se acaba de crear
                # más arriba a partir de esta misma planilla), su IVA configurado es la
                # fuente de verdad y se prioriza sobre el valor de la fila -- así una
                # planilla vieja con un % desactualizado no pisa el IVA ya cargado en
                # Rubros. Si el rubro no existe, se usa el IVA de la fila. Si no vino
                # ninguno de los dos, se asume 0% (no es un error).
                if rubro:
                    iva_porcentaje = rubro.iva_porcentaje
                elif iva_raw is not None and str(iva_raw).strip() != '':
                    iva_porcentaje = Decimal(str(iva_raw))
                elif rubro_nombre:
                    raise ValueError(f"El rubro '{rubro_nombre}' no tiene IVA asignado. Asignalo antes de importar.")
                else:
                    iva_porcentaje = Decimal('0')

                # Resolver precio de venta: el precio manual siempre prioriza sobre el margen.
                precio_venta_manual = precio_venta_raw is not None and str(precio_venta_raw).strip() != ''
                margen_presente = margen_raw is not None and str(margen_raw).strip() != ''
                if precio_venta_manual:
                    precio_venta = Decimal(str(precio_venta_raw))
                elif margen_presente:
                    margen = Decimal(str(margen_raw))
                    # El margen se aplica sobre el costo CON IVA, no sobre el costo puro.
                    costo_con_iva = costo * (Decimal('1') + iva_porcentaje / Decimal('100'))
                    precio_venta = costo_con_iva * (Decimal('1') + margen / Decimal('100'))
                else:
                    raise ValueError("Debe indicar 'Precio de Venta' o 'Margen %'.")
                precio_venta = precio_venta.quantize(Decimal('0.01'))

                producto_existente = productos_existentes_por_codigo.get(codigo_interno)
                estado = 'reposicion' if producto_existente else 'nuevo'

                resultado_fila = {
                    'fila': numero_fila,
                    'codigo_interno': codigo_interno,
                    'nombre': nombre,
                    'estado': estado,
                    'iva_porcentaje': str(iva_porcentaje),
                    'precio_venta': str(precio_venta),
                    'cantidad': cantidad,
                    'error': None,
                }

                if modo == 'confirmar':
                    if producto_existente:
                        producto_existente.costo = costo
                        producto_existente.precio = precio_venta
                        producto_existente.iva_porcentaje = iva_porcentaje
                        if rubro:
                            producto_existente.rubro = rubro
                        if codigo_barras:
                            producto_existente.codigo_barras = codigo_barras
                        producto_existente.fecha_actualizacion = timezone.now()
                        if actualizar_stock:
                            stock_anterior = producto_existente.stock or 0
                            nuevo_stock = stock_anterior + cantidad
                            producto_existente.stock = nuevo_stock
                            producto_existente.stock_ultimo_ingreso = nuevo_stock
                            producto_existente.fecha_ultimo_ingreso = timezone.now()
                        productos_a_actualizar.append(producto_existente)
                        # Se informa siempre el código de barras final (nuevo o ya
                        # existente) para que el frontend pueda imprimir etiquetas
                        # del lote recién importado sin otra consulta.
                        resultado_fila['codigo_barras'] = producto_existente.codigo_barras
                    else:
                        if codigo_barras:
                            if codigo_barras in codigos_barras_vistos:
                                raise ValueError(
                                    f"Código de barras '{codigo_barras}' duplicado "
                                    f"(ya usado en esta tienda o en otra fila del archivo)."
                                )
                            codigo_final = codigo_barras
                            codigos_barras_vistos.add(codigo_final)
                        else:
                            codigo_final = _generar_codigo_barras_en_memoria()
                        productos_a_crear.append(Producto(
                            tienda=tienda,
                            nombre=nombre,
                            codigo_interno=codigo_interno,
                            codigo_barras=codigo_final,
                            costo=costo,
                            precio=precio_venta,
                            iva_porcentaje=iva_porcentaje,
                            rubro=rubro,
                            stock=cantidad,
                            stock_ultimo_ingreso=cantidad,
                            fecha_ultimo_ingreso=timezone.now(),
                        ))
                        resultado_fila['codigo_barras'] = codigo_final

                resultados.append(resultado_fila)
            except Exception as e:
                resultados.append({
                    'fila': numero_fila,
                    'codigo_interno': fila.get('codigo_interno'),
                    'nombre': fila.get('nombre'),
                    'estado': None,
                    'error': str(e),
                })

        creados = 0
        actualizados = 0

        if modo == 'confirmar':
            if productos_a_crear:
                try:
                    Producto.objects.bulk_create(productos_a_crear, batch_size=500)
                    creados = len(productos_a_crear)
                except Exception as e:
                    logger.error(
                        "Carga masiva: bulk_create falló para %s producto(s) nuevo(s) en tienda %s: %s",
                        len(productos_a_crear), tienda.nombre, e,
                    )
                    codigos_fallidos = {p.codigo_interno for p in productos_a_crear}
                    for r in resultados:
                        if r.get('estado') == 'nuevo' and r.get('codigo_interno') in codigos_fallidos:
                            r['error'] = 'No se pudo guardar (error interno). Reintentá la importación.'
                            r['estado'] = None

            if productos_a_actualizar:
                try:
                    Producto.objects.bulk_update(
                        productos_a_actualizar,
                        ['stock', 'costo', 'precio', 'iva_porcentaje', 'rubro', 'codigo_barras',
                         'stock_ultimo_ingreso', 'fecha_ultimo_ingreso', 'fecha_actualizacion'],
                        batch_size=500,
                    )
                    actualizados = len(productos_a_actualizar)
                except Exception as e:
                    logger.error(
                        "Carga masiva: bulk_update falló para %s reposición(es) en tienda %s: %s",
                        len(productos_a_actualizar), tienda.nombre, e,
                    )
                    codigos_fallidos = {p.codigo_interno for p in productos_a_actualizar}
                    for r in resultados:
                        if r.get('estado') == 'reposicion' and r.get('codigo_interno') in codigos_fallidos:
                            r['error'] = 'No se pudo actualizar (error interno). Reintentá la importación.'
                            r['estado'] = None

        # Un único registro de historial para todo el archivo (no uno por fila): con
        # archivos de cientos/miles de filas, llamar _registrar_accion en el loop
        # multiplicaba la consulta de limpieza de historial (>90 días) por cada fila.
        if modo == 'confirmar' and (creados or actualizados):
            _registrar_accion(
                tienda=tienda, usuario=request.user, accion='ingreso_stock',
                detalle=f'Carga masiva: {creados} producto(s) nuevo(s), {actualizados} repuesto(s) (archivo de {len(filas)} fila(s)).',
            )

        return Response({
            'modo': modo,
            'total_filas': len(filas),
            'creados': creados,
            'actualizados': actualizados,
            'errores': len([r for r in resultados if r.get('error')]),
            'resultados': resultados,
        })

    @action(detail=False, methods=['post'], url_path='eliminar_todos')
    def eliminar_todos(self, request):
        """
        Borra TODOS los productos (y sus variantes) de una tienda de una sola vez.
        Pensado para resetear el catálogo antes de una reimportación completa (por
        ejemplo tras una duplicación masiva por reimportaciones repetidas de carga
        masiva). No afecta historial de ventas/presupuestos (Producto ahí usa
        SET_NULL), solo el catálogo de productos.

        Body: { tienda_slug, confirmar_nombre } -- 'confirmar_nombre' tiene que
        coincidir exactamente con el nombre de la tienda, como capa extra contra un
        borrado accidental por un tienda_slug incorrecto.
        """
        if self.request.user.is_supervisor and not self.request.user.is_superuser:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Los supervisores no pueden eliminar productos.")

        tienda_slug = request.data.get('tienda_slug')
        confirmar_nombre = str(request.data.get('confirmar_nombre') or '').strip()
        tienda = self._resolver_tienda(tienda_slug)
        if not tienda:
            return Response({'error': 'No se pudo determinar la tienda.'}, status=status.HTTP_400_BAD_REQUEST)
        if confirmar_nombre != tienda.nombre:
            return Response(
                {'error': "El nombre de confirmación no coincide con el de la tienda."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_antes = Producto.objects.filter(tienda=tienda).count()
        Producto.objects.filter(tienda=tienda).delete()

        _registrar_accion(
            tienda=tienda, usuario=request.user, accion='ajuste_stock',
            detalle=f'Eliminación masiva de catálogo: {total_antes} producto(s) eliminado(s) (reset previo a reimportación).',
        )
        return Response({'eliminados': total_antes})

    @action(detail=True, methods=['post'], url_path='agrupar-variantes')
    def agrupar_variantes(self, request, pk=None):
        """
        Agrupa una lista de productos como variantes de este producto (padre).
        Body: { "variante_ids": ["uuid1", "uuid2", ...] }
        """
        padre = self.get_object()
        variante_ids = request.data.get('variante_ids', [])

        if not variante_ids:
            return Response({'error': 'Debe proporcionar al menos un variante_id.'}, status=400)

        variantes = Producto.objects.filter(
            id__in=variante_ids,
            tienda=padre.tienda,
        ).exclude(id=padre.id)

        if variantes.count() != len(variante_ids):
            return Response({'error': 'Algunos productos no pertenecen a la tienda o no existen.'}, status=400)

        variantes.update(producto_padre=padre)
        return Response({
            'mensaje': f'{variantes.count()} producto(s) agrupados como variantes de "{padre.nombre}".',
            'padre_id': str(padre.id),
        })

    @action(detail=True, methods=['post'], url_path='desagrupar-variante')
    def desagrupar_variante(self, request, pk=None):
        """
        Desvincula este producto de su padre, convirtiéndolo en producto independiente.
        """
        producto = self.get_object()
        if not producto.producto_padre_id:
            return Response({'error': 'Este producto no es una variante.'}, status=400)
        producto.producto_padre = None
        producto.save(update_fields=['producto_padre'])
        return Response({'mensaje': f'"{producto.nombre}" ahora es un producto independiente.'})

    @action(detail=True, methods=['post'], url_path='vincular-tienda-nube')
    def vincular_tienda_nube(self, request, pk=None):
        """
        Vincula este producto a un producto YA EXISTENTE en Tienda Nube (creado ahí
        manualmente por el cliente), en vez de crearlo desde Total Stock. Pensado para
        clientes que prefieren armar la ficha del producto directamente en Tienda Nube
        (fotos, descripción, SEO) y solo necesitan que el stock se sincronice.

        Body: { "tn_product_id": "...", "tn_variant_id": "..." (opcional) }
        Si el producto de TN tiene una sola variante, se resuelve sola. Si tiene varias
        y no se especificó tn_variant_id, devuelve la lista para que el cliente elija.
        """
        from .services.tiendanube_service import TiendaNubeService, sincronizar_stock_producto

        producto = self.get_object()
        tienda = producto.tienda

        if not tienda.tn_access_token or not tienda.tn_store_id:
            return Response({'error': 'Esta tienda no tiene Tienda Nube conectado.'}, status=400)

        tn_product_id = str(request.data.get('tn_product_id') or '').strip()
        if not tn_product_id:
            return Response({'error': 'Falta el ID del producto de Tienda Nube.'}, status=400)
        tn_variant_id = str(request.data.get('tn_variant_id') or '').strip() or None

        tn = TiendaNubeService(tienda)
        try:
            tn_producto = tn.get_product(tn_product_id)
        except Exception as e:
            logger.warning("vincular_tienda_nube: no se pudo obtener producto TN %s: %s", tn_product_id, e)
            return Response(
                {'error': f'No se encontró el producto {tn_product_id} en Tienda Nube. Verificá el ID.'},
                status=400,
            )

        variantes = tn_producto.get('variants', [])
        if not variantes:
            return Response({'error': 'Ese producto de Tienda Nube no tiene variantes.'}, status=400)

        nombre_tn = (tn_producto.get('name') or {}).get('es', producto.nombre)
        es_parte_de_familia_local = bool(producto.producto_padre_id) or producto.variantes.exists()

        # Caso: el producto local es suelto (no tiene ni es parte de una familia de
        # variantes) y en Tienda Nube el producto SÍ tiene varias variantes → en vez de
        # forzar a elegir una sola, se convierte en padre y se crea acá una variante local
        # por cada variante de TN (con stock en 0: no hay forma de saber cómo se repartía
        # el número agregado que tenía el producto suelto entre los distintos talles).
        if len(variantes) > 1 and not tn_variant_id and not es_parte_de_familia_local:
            with transaction.atomic():
                producto.tn_product_id = tn_product_id
                producto.tn_variant_id = None
                producto.tn_sincronizado = False
                producto.stock = 0
                producto.talle = None
                producto.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado', 'stock', 'talle'])

                nuevas = []
                for v in variantes:
                    talle_variante = ', '.join(
                        (val.get('es') or '') for val in v.get('values', []) if val
                    ) or None
                    nuevas.append(Producto.objects.create(
                        tienda=tienda,
                        nombre=producto.nombre,
                        producto_padre=producto,
                        talle=talle_variante,
                        precio=producto.precio,
                        costo=producto.costo,
                        iva_porcentaje=producto.iva_porcentaje,
                        rubro=producto.rubro,
                        codigo_barras=_generar_codigo_barras_unico(tienda),
                        stock=0,
                        tn_product_id=tn_product_id,
                        tn_variant_id=str(v.get('id')),
                        tn_sincronizado=True,
                    ))

            return Response({
                'mensaje': (
                    f'"{producto.nombre}" se convirtió en una familia de {len(nuevas)} variante(s) '
                    f'vinculada(s) a "{nombre_tn}" en Tienda Nube. El stock de cada variante quedó '
                    f'en 0 — hace falta cargarlo a mano según lo que tengas físicamente de cada una.'
                ),
                'familia_creada': True,
                'padre_id': str(producto.id),
                'variantes_creadas': len(nuevas),
            })

        variante_elegida = None
        if tn_variant_id:
            variante_elegida = next((v for v in variantes if str(v.get('id')) == tn_variant_id), None)
            if not variante_elegida:
                return Response({'error': f'La variante {tn_variant_id} no pertenece a ese producto de Tienda Nube.'}, status=400)
        elif len(variantes) == 1:
            variante_elegida = variantes[0]
        else:
            return Response({
                'requiere_variante': True,
                'mensaje': 'Ese producto tiene varias variantes en Tienda Nube. Elegí cuál corresponde.',
                'variantes': [
                    {
                        'id': str(v.get('id')),
                        'sku': v.get('sku') or '',
                        'valores': ', '.join(
                            (val.get('es') or '') for val in v.get('values', []) if val
                        ),
                    }
                    for v in variantes
                ],
            }, status=409)

        producto.tn_product_id = tn_product_id
        producto.tn_variant_id = str(variante_elegida.get('id'))
        producto.tn_sincronizado = True
        producto.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado'])

        # Empuja el stock local a TN de una para que ambos lados arranquen alineados.
        sincronizar_stock_producto(producto)

        return Response({
            'mensaje': f'"{producto.nombre}" vinculado a "{nombre_tn}" en Tienda Nube.',
            'tn_product_id': producto.tn_product_id,
            'tn_variant_id': producto.tn_variant_id,
        })

    @action(detail=True, methods=['post'], url_path='desvincular-tienda-nube')
    def desvincular_tienda_nube(self, request, pk=None):
        """Quita la vinculación de este producto con Tienda Nube (no borra nada en TN)."""
        producto = self.get_object()
        producto.tn_product_id = None
        producto.tn_variant_id = None
        producto.tn_sincronizado = False
        producto.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado'])
        return Response({'mensaje': f'"{producto.nombre}" ya no está vinculado a Tienda Nube.'})

    @action(detail=True, methods=['post'], url_path='transferir-stock')
    def transferir_stock(self, request, pk=None):
        """Transfiere stock de este producto (o variante) hacia el mismo producto en otra
        tienda a la que el usuario tenga acceso, creándolo en destino si no existe."""
        user = request.user
        if not (user.is_superuser or user.is_supervisor):
            return Response({'error': 'No tenés permiso para transferir stock.'}, status=403)

        producto_origen = self.get_object()

        try:
            cantidad = int(request.data.get('cantidad'))
        except (TypeError, ValueError):
            return Response({'error': 'Cantidad inválida.'}, status=400)
        if cantidad <= 0:
            return Response({'error': 'La cantidad debe ser mayor a cero.'}, status=400)
        if cantidad > (producto_origen.stock or 0):
            return Response({'error': 'Stock insuficiente para transferir.'}, status=400)

        tienda_destino = self._resolver_tienda(request.data.get('tienda_destino'))
        if not tienda_destino:
            return Response({'error': 'Tienda destino inválida o no autorizada.'}, status=400)
        if tienda_destino.pk == producto_origen.tienda_id:
            return Response({'error': 'La tienda destino debe ser distinta de la tienda de origen.'}, status=400)

        with transaction.atomic():
            producto_destino, creado = _transferir_unidad(producto_origen, tienda_destino, cantidad)
            talle_str = f' (T: {producto_origen.talle})' if producto_origen.talle else ''
            _registrar_accion(
                tienda=producto_origen.tienda, usuario=user, accion='transferencia_stock',
                detalle=f'Transferencia -{cantidad} · {producto_origen.nombre}{talle_str} → {tienda_destino.nombre}',
                objeto_id=producto_origen.id,
            )
            _registrar_accion(
                tienda=tienda_destino, usuario=user, accion='transferencia_stock',
                detalle=f'Transferencia +{cantidad} · {producto_destino.nombre}{talle_str} · desde {producto_origen.tienda.nombre}',
                objeto_id=producto_destino.id,
            )

        serializer = self.get_serializer(producto_origen)
        data = dict(serializer.data)
        data['transferencia'] = {
            'tienda_destino': tienda_destino.nombre,
            'producto_destino_id': str(producto_destino.id),
            'creado': creado,
        }
        return Response(data)

    @action(detail=True, methods=['post'], url_path='transferir-stock-lote')
    def transferir_stock_lote(self, request, pk=None):
        """Transfiere de una sola vez el stock de varias variantes de esta familia
        (self es el producto padre) hacia la misma familia en otra tienda."""
        user = request.user
        if not (user.is_superuser or user.is_supervisor):
            return Response({'error': 'No tenés permiso para transferir stock.'}, status=403)

        padre = self.get_object()
        lineas = request.data.get('variantes', [])
        if not lineas:
            return Response({'error': 'Debe indicar al menos una variante con cantidad.'}, status=400)

        tienda_destino = self._resolver_tienda(request.data.get('tienda_destino'))
        if not tienda_destino:
            return Response({'error': 'Tienda destino inválida o no autorizada.'}, status=400)
        if tienda_destino.pk == padre.tienda_id:
            return Response({'error': 'La tienda destino debe ser distinta de la tienda de origen.'}, status=400)

        variante_ids = [str(linea.get('id')) for linea in lineas]
        variantes_por_id = {
            str(v.id): v for v in Producto.objects.filter(id__in=variante_ids, producto_padre=padre)
        }
        if len(variantes_por_id) != len(set(variante_ids)):
            return Response({'error': 'Alguna variante no pertenece a este producto.'}, status=400)

        cantidades = {}
        total = 0
        for linea in lineas:
            vid = str(linea.get('id'))
            try:
                cantidad = int(linea.get('cantidad'))
            except (TypeError, ValueError):
                return Response({'error': f'Cantidad inválida para la variante {vid}.'}, status=400)
            if cantidad <= 0:
                return Response({'error': f'La cantidad debe ser mayor a cero (variante {vid}).'}, status=400)
            variante = variantes_por_id[vid]
            if cantidad > (variante.stock or 0):
                return Response({'error': f'Stock insuficiente para "{variante.talle or variante.nombre}".'}, status=400)
            cantidades[vid] = cantidad
            total += cantidad

        with transaction.atomic():
            cache = {}
            for vid, cantidad in cantidades.items():
                _transferir_unidad(variantes_por_id[vid], tienda_destino, cantidad, padre_destino_cache=cache)

            _registrar_accion(
                tienda=padre.tienda, usuario=user, accion='transferencia_stock',
                detalle=f'Transferencia de lote -{total} · {len(cantidades)} variante(s) de "{padre.nombre}" → {tienda_destino.nombre}',
                objeto_id=padre.id,
            )
            _registrar_accion(
                tienda=tienda_destino, usuario=user, accion='transferencia_stock',
                detalle=f'Transferencia de lote +{total} · {len(cantidades)} variante(s) de "{padre.nombre}" · desde {padre.tienda.nombre}',
                objeto_id=padre.id,
            )

        serializer = self.get_serializer(padre)
        data = dict(serializer.data)
        data['transferencia'] = {
            'tienda_destino': tienda_destino.nombre,
            'total_transferido': total,
            'variantes': len(cantidades),
        }
        return Response(data)


class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

# Endpoints internos para Cloudflare Worker (proxy OAuth cuando Render da 403)
def _verify_ml_worker_secret(request):
    """Verifica el header X-ML-OAuth-Proxy-Key contra ML_OAUTH_WORKER_SECRET."""
    import os
    secret = os.environ.get('ML_OAUTH_WORKER_SECRET', '').strip()
    if not secret:
        return False
    provided = request.headers.get('X-ML-OAuth-Proxy-Key', '')
    return secrets.compare_digest(secret, provided)


def _resolve_tienda_id_from_state(state):
    """
    Devuelve el tienda_id validado desde el cache para el state dado.
    Si el state no existe en cache retorna None (puede ser inválido o expirado).
    """
    tienda_id = cache.get(f"ml_oauth_state_{state}")
    if tienda_id:
        return tienda_id
    # Fallback para states generados antes de implementar la validación por cache
    if ':' in state:
        return state.split(':')[0]
    if len(state) > 30:
        return state
    return None


def _check_rate_limit(key, max_requests=20, window=60):
    """Rate limiter simple usando Django cache. Retorna False si se excedió el límite."""
    cache_key = f"ratelimit_{key}"
    count = cache.get(cache_key, 0)
    if count >= max_requests:
        return False
    cache.set(cache_key, count + 1, timeout=window)
    return True


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def ml_oauth_worker_credentials(request):
    """
    Devuelve client_id y client_secret para el Worker.
    Solo si ML_OAUTH_WORKER_SECRET está configurado y el header coincide.
    """
    import os
    ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', 'unknown')
    if not _check_rate_limit(f"ml_creds_{ip}", max_requests=20, window=60):
        return Response({'error': 'Too many requests'}, status=429)
    if not _verify_ml_worker_secret(request):
        return Response({'error': 'Unauthorized'}, status=401)
    state = request.query_params.get('state')
    if not state:
        return Response({'error': 'state required'}, status=400)
    tienda_id = _resolve_tienda_id_from_state(state)
    if not tienda_id:
        return Response({'error': 'Invalid or expired state'}, status=400)
    try:
        tienda = Tienda.objects.get(id=tienda_id)
    except Tienda.DoesNotExist:
        return Response({'error': 'Tienda not found'}, status=404)
    if getattr(tienda, 'plataforma_ecommerce', '') != 'MERCADO_LIBRE':
        return Response({'error': 'Tienda not configured for ML'}, status=400)
    worker_url = os.environ.get('ML_OAUTH_WORKER_URL', '').strip()
    if not worker_url:
        return Response({'error': 'ML_OAUTH_WORKER_URL not configured'}, status=500)
    # worker_url = URL completa del callback del Worker (ej. https://xxx.workers.dev/callback)
    return Response({
        'client_id': tienda.ml_app_id,
        'client_secret': tienda.ml_client_secret,
        'redirect_uri': worker_url.rstrip('/'),
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def ml_oauth_worker_save_tokens(request):
    """
    Guarda los tokens que el Worker obtuvo de ML.
    """
    import os
    from django.utils import timezone
    if not _verify_ml_worker_secret(request):
        return Response({'error': 'Unauthorized'}, status=401)
    state = request.data.get('state')
    if not state:
        return Response({'error': 'state required'}, status=400)
    tienda_id = _resolve_tienda_id_from_state(state)
    if not tienda_id:
        return Response({'error': 'Invalid or expired state'}, status=400)
    try:
        tienda = Tienda.objects.get(id=tienda_id)
    except Tienda.DoesNotExist:
        return Response({'error': 'Tienda not found'}, status=404)
    tienda.ml_access_token = request.data.get('access_token')
    tienda.ml_refresh_token = request.data.get('refresh_token')
    tienda.ml_user_id = request.data.get('user_id')
    expires_in = request.data.get('expires_in', 21600)
    tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    tienda.save(update_fields=['ml_access_token', 'ml_refresh_token', 'ml_user_id', 'ml_token_expires_at'])
    # Invalidar el state para que no pueda reutilizarse
    cache.delete(f"ml_oauth_state_{state}")
    return Response({'ok': True, 'tienda_id': str(tienda.id), 'nombre': tienda.nombre})


# Vista independiente para el callback público de Mercado Libre (fuera del ViewSet)
@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
def ml_oauth_callback_public_view(request):
    """
    Vista independiente para recibir el callback de OAuth de Mercado Libre
    Este endpoint NO requiere {tienda_id} en la URL, permitiendo que Mercado Libre
    redirija a una URL fija como /api/tiendas/mercadolibre/callback/
    
    GET: Maneja la redirección desde Mercado Libre (obtiene el código)
    POST: Intercambia el código por tokens
    """
    from .models import Tienda
    from .services.mercadolibre_service import MercadoLibreService
    from django.conf import settings
    
    # Obtener tienda_id del request (puede venir en query params, body, o state)
    tienda_id = request.query_params.get('tienda_id') or (request.data.get('tienda_id') if hasattr(request, 'data') else None)
    tienda = None
    
    # Manejar GET (redirección desde Mercado Libre con code en query params)
    if request.method == 'GET':
        state = request.query_params.get('state')

        # PRIORIDAD 1: Resolver tienda_id desde state validado en cache
        if state:
            resolved = _resolve_tienda_id_from_state(state)
            if resolved:
                tienda_id = resolved
                try:
                    tienda = Tienda.objects.get(id=tienda_id)
                    logger.info(f"Tienda identificada desde state validado: {tienda_id}")
                    # Invalidar state después de usarlo (flujo directo sin Worker)
                    cache.delete(f"ml_oauth_state_{state}")
                except Tienda.DoesNotExist:
                    logger.warning(f"State válido pero tienda no encontrada: {tienda_id}")
            else:
                logger.warning(f"State inválido o expirado: '{state}'")

    # Si aún no tenemos tienda, intentar otras formas
    if not tienda:
        if tienda_id:
            try:
                tienda = Tienda.objects.get(id=tienda_id)
            except Tienda.DoesNotExist:
                return Response(
                    {'error': f'Tienda con ID {tienda_id} no encontrada'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Como último recurso, buscar tiendas configuradas con ML
            # Solo funciona si hay exactamente una tienda configurada
            tiendas_ml = Tienda.objects.filter(
                plataforma_ecommerce='MERCADO_LIBRE'
            ).exclude(ml_app_id__isnull=True).exclude(ml_app_id='')

            if tiendas_ml.count() == 1:
                tienda = tiendas_ml.first()
                logger.info(f"Tienda identificada automáticamente (única configurada): {tienda.id}")
            elif tiendas_ml.count() == 0:
                return Response(
                    {'error': 'No hay tiendas configuradas para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                return Response(
                    {'error': 'No se pudo determinar la tienda. Múltiples tiendas configuradas. Proporciona tienda_id en el request o usa el parámetro state.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

    # Si llegamos aquí sin tienda, es un error
    if not tienda:
        return Response(
            {'error': 'No se pudo determinar la tienda'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Verificar si ML está configurado
    if not hasattr(tienda, 'plataforma_ecommerce') or getattr(tienda, 'plataforma_ecommerce', 'NINGUNA') != 'MERCADO_LIBRE':
        return Response(
            {'error': 'La tienda no está configurada para Mercado Libre'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Manejar GET (redirección desde Mercado Libre con code en query params)
    if request.method == 'GET':
        code = request.query_params.get('code')
        
        if code:
            # Procesar el callback directamente
            ml_service = MercadoLibreService(tienda)
            
            if not settings.DEBUG:
                redirect_uri = 'https://bonito-amor-backend.onrender.com/api/tiendas/mercadolibre/callback/'
            else:
                scheme = request.scheme
                host = request.get_host()
                redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
            
            try:
                tokens = ml_service.exchange_code_for_token(code, redirect_uri)
                
                # Guardar tokens
                if hasattr(tienda, 'ml_access_token'):
                    tienda.ml_access_token = tokens['access_token']
                if hasattr(tienda, 'ml_refresh_token'):
                    tienda.ml_refresh_token = tokens.get('refresh_token')
                if hasattr(tienda, 'ml_user_id'):
                    tienda.ml_user_id = tokens.get('user_id')
                if hasattr(tienda, 'ml_token_expires_at'):
                    expires_in = tokens.get('expires_in', 21600)
                    tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                
                tienda.save()
                
                # Retornar HTML de éxito para el navegador con postMessage para comunicarse con la ventana padre
                return HttpResponse(
                    f'<html><head><title>Autenticación exitosa</title></head><body>'
                    f'<h1>✅ Autenticación exitosa</h1>'
                    f'<p>La integración con Mercado Libre se configuró correctamente para la tienda: {tienda.nombre}</p>'
                    f'<p>Puedes cerrar esta ventana.</p>'
                    f'<script>'
                    f'if (window.opener) {{'
                    f'  window.opener.postMessage({{'
                    f'    type: "ML_OAUTH_SUCCESS",'
                    f'    tienda_id: "{tienda.id}",'
                    f'    message: "Autenticación exitosa"'
                    f'  }}, "*");'
                    f'  setTimeout(function(){{window.close();}}, 2000);'
                    f'}} else {{'
                    f'  setTimeout(function(){{window.close();}}, 3000);'
                    f'}}'
                    f'</script></body></html>',
                    content_type='text/html'
                )
            except Exception as e:
                logger.error(f"Error procesando callback GET: {e}", exc_info=True)
                return HttpResponse(
                    f'<html><body><h1>❌ Error en autenticación</h1>'
                    f'<p>Error: {str(e)}</p></body></html>',
                    content_type='text/html',
                    status=400
                )
        else:
            return Response({
                'message': 'Endpoint de callback de Mercado Libre. Esperando código de autorización.'
            })
    
    # Manejar POST (intercambiar código por tokens)
    code = request.data.get('code') if hasattr(request, 'data') else None
    if not code:
        code = request.query_params.get('code')
    
    if not code:
        return Response(
            {'error': 'Código de autorización no proporcionado'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    ml_service = MercadoLibreService(tienda)
    
    # Usar la URL fija configurada en Mercado Libre
    if not settings.DEBUG:
        redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
    else:
        scheme = request.scheme
        host = request.get_host()
        redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
    
    try:
        tokens = ml_service.exchange_code_for_token(code, redirect_uri)
        
        # Guardar tokens en la tienda
        if hasattr(tienda, 'ml_access_token'):
            tienda.ml_access_token = tokens['access_token']
        if hasattr(tienda, 'ml_refresh_token'):
            tienda.ml_refresh_token = tokens.get('refresh_token')
        if hasattr(tienda, 'ml_user_id'):
            tienda.ml_user_id = tokens.get('user_id')
        
        # Calcular fecha de expiración
        if hasattr(tienda, 'ml_token_expires_at'):
            expires_in = tokens.get('expires_in', 21600)
            tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        
        tienda.save()
        
        return Response({
            'success': True,
            'message': 'Autenticación exitosa',
            'user_id': getattr(tienda, 'ml_user_id', None)
        })
    except Exception as e:
        logger.error(f"Error en callback OAuth público: {e}", exc_info=True)
        return Response(
            {'error': f'Error al procesar el callback: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [permissions.AllowAny]
        elif self.action in [
            'ml_webhook', 'tn_webhook',
            'tn_privacy_store_redact', 'tn_privacy_customers_redact', 'tn_privacy_customers_data_request',
        ]:
            # Los webhooks (incluidos los de privacidad de Tiendanube) deben ser accesibles sin autenticación
            permission_classes = [permissions.AllowAny]
        elif self.action in ['facturacion_test']:
            # Probar configuración de facturación: requiere usuario autenticado (staff/admin recomendado)
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Optimización: Filtrar por nombre si se proporciona en query params"""
        queryset = super().get_queryset()
        nombre = self.request.query_params.get('nombre', None)
        if nombre:
            # Filtrar por nombre (case-insensitive)
            queryset = queryset.filter(nombre__iexact=nombre)
        return queryset

    # FIX DE CONEXIÓN (Mantenido)
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)
    
    # ========== MÉTODOS DE MERCADO LIBRE ==========
    
    def _ml_fields_exist(self, tienda):
        """Verifica si los campos de ML existen en el modelo Tienda"""
        return hasattr(tienda, 'plataforma_ecommerce')
    
    def _ml_configured(self, tienda):
        """Verifica si ML está configurado para la tienda"""
        if not self._ml_fields_exist(tienda):
            return False
        return getattr(tienda, 'plataforma_ecommerce', 'NINGUNA') == 'MERCADO_LIBRE'

    # ========== FACTURACIÓN ELECTRÓNICA ==========

    @action(detail=True, methods=['post'], url_path='facturacion/generar-csr')
    def facturacion_generar_csr(self, request, pk=None):
        """
        Genera automáticamente la clave privada RSA y el CSR (Certificate Signing Request)
        para ARCA con los datos de la tienda. La clave privada se guarda en base64 en la tienda.
        El usuario debe subir el CSR a ARCA, obtener el .crt y cargar el certificado en base64.

        DN del certificado (por diseño ARCA): SERIALNUMBER=CUIT nnnnnnnnnnn, CN=alias
        Body opcional: { "alias": "MiAlias", "razon_social": "Mi Empresa S.A." }
        """
        tienda = self.get_object()

        if not tienda.cuit or not tienda.cuit.strip():
            return Response(
                {'success': False, 'message': 'La tienda debe tener CUIT configurado para generar el CSR.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cuit_limpio = re.sub(r'[^0-9]', '', tienda.cuit.strip())
        if len(cuit_limpio) != 11:
            return Response(
                {'success': False, 'message': 'El CUIT debe tener 11 dígitos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alias = (request.data.get('alias') or '').strip() or 'TotalStock'
        razon_social = (request.data.get('razon_social') or '').strip() or (tienda.nombre or 'Empresa')
        # Sanear para subject: evitar caracteres que rompan el DN
        for char in ['/', ',', '+', '=', '\n', '\r']:
            alias = alias.replace(char, ' ')
        alias = ' '.join(alias.split())[:64] or 'TotalStock'
        for char in ['/', ',', '+', '=', '\n', '\r']:
            razon_social = razon_social.replace(char, ' ')
        razon_social = ' '.join(razon_social.split())[:128] or 'Empresa'

        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.backends import default_backend
            from cryptography import x509
            from cryptography.x509.oid import NameOID
        except ImportError:
            return Response(
                {'success': False, 'message': 'El paquete cryptography no está instalado.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            # Generar clave privada RSA 2048 bits
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )

            # Subject: /C=AR/O=NombreEmpresa/CN=alias/serialNumber=CUITnnnnnnnnnnn
            name = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, 'AR'),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, razon_social),
                x509.NameAttribute(NameOID.COMMON_NAME, alias),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, f'CUIT {cuit_limpio}'),
            ])

            csr = x509.CertificateSigningRequestBuilder().subject_name(name).sign(
                private_key, hashes.SHA256(), default_backend()
            )

            # Serializar clave privada a PEM y luego a base64
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_b64 = base64.b64encode(key_pem).decode('ascii')

            # CSR en PEM (para que el usuario lo descargue y suba a ARCA)
            csr_pem = csr.public_bytes(serialization.Encoding.PEM)

            # Guardar clave privada en la tienda (solo si el modelo tiene el campo)
            if hasattr(tienda, 'clave_privada_afip'):
                tienda.clave_privada_afip = key_b64
                tienda.save(update_fields=['clave_privada_afip'])

            return Response(
                {
                    'success': True,
                    'message': 'Clave privada generada y guardada. Subí el CSR a ARCA y luego cargá el certificado (.crt) en base64.',
                    'csr_base64': base64.b64encode(csr_pem).decode('ascii'),
                    'csr_pem': csr_pem.decode('utf-8'),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception('Error al generar CSR para tienda %s: %s', tienda.id, e)
            return Response(
                {'success': False, 'message': f'Error al generar clave o CSR: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['post'], url_path='facturacion/test')
    def facturacion_test(self, request, pk=None):
        """
        Prueba la configuración de facturación electrónica de la tienda
        emitiendo una factura de prueba por $1.

        - Usa el tipo de facturación configurado en la tienda (ARCA).
        - Crea una venta de prueba de $1 y emite la factura.
        - Devuelve feedback claro: éxito (con datos de la factura) o mensaje de error.
        """
        tienda = self.get_object()

        if not tienda.tipo_facturacion or tienda.tipo_facturacion == 'NINGUNA':
            return Response(
                {
                    'success': False,
                    'message': 'La tienda no tiene configurado un tipo de facturación (ARCA).',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tienda.tipo_facturacion != 'AFIP':
            return Response(
                {
                    'success': False,
                    'message': 'Por el momento, la prueba automática de facturación está disponible solo para ARCA.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing_fields = []
        if not tienda.cuit:
            missing_fields.append('cuit')
        if not tienda.punto_venta:
            missing_fields.append('punto_venta')

        # Campos específicos ARCA
        if not getattr(tienda, 'certificado_afip', None):
            missing_fields.append('certificado_afip')
        if not getattr(tienda, 'clave_privada_afip', None):
            missing_fields.append('clave_privada_afip')

        if missing_fields:
            return Response(
                {
                    'success': False,
                    'message': 'Faltan datos obligatorios para configurar la facturación.',
                    'missing_fields': missing_fields,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Crear una venta de prueba por $1
        try:
            usuario = request.user if request.user.is_authenticated else None
            venta_prueba = Venta.objects.create(
                tienda=tienda,
                usuario=usuario,
                total=Decimal('1.00'),
                metodo_pago='PRUEBA FACTURADOR',
                cliente_nombre='Consumidor Final',
                cliente_tipo_documento='99',
                cliente_domicilio='Sin especificar',
            )

            # Crear un detalle mínimo para la venta (sin afectar stock de productos)
            DetalleVenta.objects.create(
                venta=venta_prueba,
                producto=None,
                cantidad=1,
                precio_unitario=Decimal('1.00'),
                costo_unitario=None,
                subtotal=Decimal('1.00'),
            )

            cliente_data = {
                'cliente_nombre': 'Consumidor Final',
                'cliente_cuit': '',
                'cliente_domicilio': 'Sin especificar',
                'cliente_tipo_documento': '99',
                'cliente_condicion_iva': 'CF',
            }

            facturacion_service = FacturacionService(tienda)
            exito, datos_factura, error = facturacion_service.emitir_factura(venta_prueba, cliente_data)

            if not exito:
                # Registrar factura con error para trazabilidad
                factura_error = Factura.objects.create(
                    venta=venta_prueba,
                    tienda=tienda,
                    punto_venta=tienda.punto_venta,
                    tipo_comprobante='B',
                    cliente_nombre=cliente_data['cliente_nombre'],
                    cliente_cuit=cliente_data.get('cliente_cuit', ''),
                    cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                    cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                    cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                    subtotal=venta_prueba.total,
                    impuesto_iva=Decimal('0.00'),
                    total=venta_prueba.total,
                    estado='ERROR',
                    sistema_facturacion=tienda.tipo_facturacion,
                    error_mensaje=error,
                )
                return Response(
                    {
                        'success': False,
                        'message': error or 'No se pudo emitir la factura de prueba.',
                        'factura_id': str(factura_error.id),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Registrar factura exitosa
            factura_ok = Factura.objects.create(
                venta=venta_prueba,
                tienda=tienda,
                numero_comprobante=datos_factura.get('numero_comprobante'),
                punto_venta=datos_factura.get('punto_venta', tienda.punto_venta),
                tipo_comprobante=datos_factura.get('tipo_comprobante', 'B'),
                cliente_nombre=cliente_data['cliente_nombre'],
                cliente_cuit=cliente_data.get('cliente_cuit', ''),
                cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                subtotal=datos_factura.get('subtotal', venta_prueba.total),
                impuesto_iva=datos_factura.get('impuesto_iva', Decimal('0.00')),
                total=datos_factura.get('total', venta_prueba.total),
                estado='EMITIDA',
                sistema_facturacion=tienda.tipo_facturacion,
                cae=datos_factura.get('cae'),
                fecha_vencimiento_cae=datos_factura.get('fecha_vencimiento_cae'),
                numero_comprobante_afip=datos_factura.get('numero_comprobante_afip'),
                respuesta_bruta=datos_factura.get('respuesta_bruta'),
            )
            venta_prueba.facturada = True
            venta_prueba.save()

            return Response(
                {
                    'success': True,
                    'message': 'Factura de prueba emitida correctamente.',
                    'factura_id': str(factura_ok.id),
                    'numero_comprobante': factura_ok.numero_comprobante,
                    'punto_venta': factura_ok.punto_venta,
                    'tipo_comprobante': factura_ok.tipo_comprobante,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception(f"Error al probar configuración de facturación para tienda {tienda.id}: {e}")
            return Response(
                {
                    'success': False,
                    'message': f'Error inesperado al emitir la factura de prueba: {e}',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    # ========== ARCA: ESTADO, CONFIGURAR, CARGAR CERTIFICADO ==========

    @action(detail=True, methods=['get'], url_path='facturacion/estado')
    def facturacion_estado(self, request, pk=None):
        """
        Devuelve el estado de cada paso del wizard de configuración ARCA.
        Usado por el frontend para mostrar qué pasos están completos.
        """
        tienda = self.get_object()
        tiene_cuit = bool(getattr(tienda, 'cuit', None) and str(tienda.cuit).strip())
        tiene_punto_venta = bool(getattr(tienda, 'punto_venta', None))
        tiene_tipo_facturacion = getattr(tienda, 'tipo_facturacion', 'NINGUNA') not in ('NINGUNA', '', None)
        tiene_clave_privada = bool(getattr(tienda, 'clave_privada_afip', None))
        tiene_certificado = bool(getattr(tienda, 'certificado_afip', None))
        return Response({
            'paso1_config': tiene_cuit and tiene_punto_venta and tiene_tipo_facturacion,
            'paso2_csr': tiene_clave_privada,
            'paso4_cert': tiene_certificado,
            'cuit': tienda.cuit if tiene_cuit else '',
            'punto_venta': tienda.punto_venta if tiene_punto_venta else 1,
            'tipo_facturacion': getattr(tienda, 'tipo_facturacion', 'NINGUNA'),
            'condicion_iva_emisor': getattr(tienda, 'condicion_iva_emisor', 'MT'),
            'modo_test_afip': getattr(tienda, 'modo_test_afip', True),
        })

    @action(detail=True, methods=['post'], url_path='facturacion/configurar')
    def facturacion_configurar(self, request, pk=None):
        """
        Guarda la configuración básica de ARCA: CUIT, punto de venta,
        tipo_facturacion, condicion_iva_emisor, modo_test_afip.
        """
        tienda = self.get_object()
        allowed = ['cuit', 'punto_venta', 'tipo_facturacion', 'condicion_iva_emisor', 'modo_test_afip']
        update_fields = []

        cuit = request.data.get('cuit', '').strip()
        if cuit:
            cuit_digits = re.sub(r'\D', '', cuit)
            if len(cuit_digits) != 11:
                return Response({'error': 'El CUIT debe tener exactamente 11 dígitos.'}, status=400)
            tienda.cuit = cuit
            update_fields.append('cuit')

        punto_venta = request.data.get('punto_venta')
        if punto_venta is not None:
            try:
                tienda.punto_venta = int(punto_venta)
                update_fields.append('punto_venta')
            except (ValueError, TypeError):
                return Response({'error': 'Punto de venta inválido.'}, status=400)

        tipo = request.data.get('tipo_facturacion')
        if tipo:
            opciones_validas = ['AFIP', 'ARCA', 'NINGUNA']
            if tipo not in opciones_validas:
                return Response({'error': f'tipo_facturacion debe ser uno de: {opciones_validas}'}, status=400)
            tienda.tipo_facturacion = tipo
            update_fields.append('tipo_facturacion')

        condicion = request.data.get('condicion_iva_emisor')
        if condicion:
            tienda.condicion_iva_emisor = condicion
            update_fields.append('condicion_iva_emisor')

        modo_test = request.data.get('modo_test_afip')
        if modo_test is not None:
            tienda.modo_test_afip = bool(modo_test)
            update_fields.append('modo_test_afip')

        if update_fields:
            tienda.save(update_fields=update_fields)
            logger.info(f"Configuración ARCA actualizada para tienda {tienda.id}: {update_fields}")

        return Response({
            'success': True,
            'message': 'Configuración guardada correctamente.',
            'campos_actualizados': update_fields,
        })

    @action(detail=True, methods=['post'], url_path='facturacion/cargar-certificado')
    def facturacion_cargar_certificado(self, request, pk=None):
        """
        Acepta el certificado ARCA en dos formatos:
        - Archivo .crt/.pem subido (multipart/form-data, campo 'certificado_file')
        - Texto base64 en el campo 'certificado_base64'
        Valida el formato y lo guarda en tienda.certificado_afip.
        """
        import base64 as b64lib
        tienda = self.get_object()

        certificado_b64 = None

        # Opción 1: archivo subido
        archivo = request.FILES.get('certificado_file')
        if archivo:
            contenido = archivo.read()
            # Si viene como PEM (texto), extraer el DER y re-encodear a base64 limpio
            try:
                texto = contenido.decode('utf-8', errors='replace').strip()
                if '-----BEGIN CERTIFICATE-----' in texto:
                    # Extraer el bloque base64 del PEM
                    lineas = texto.splitlines()
                    b64_lineas = [l for l in lineas if not l.startswith('-----')]
                    certificado_b64 = ''.join(b64_lineas).strip()
                else:
                    # Asumir que es DER binario → convertir a base64
                    certificado_b64 = b64lib.b64encode(contenido).decode('utf-8')
            except Exception as e:
                return Response({'error': f'No se pudo procesar el archivo: {e}'}, status=400)

        # Opción 2: base64 en el body
        if not certificado_b64:
            cert_raw = request.data.get('certificado_base64', '').strip()
            if not cert_raw:
                return Response({'error': 'Enviá el certificado como archivo (.crt/.pem) o en base64.'}, status=400)
            # Limpiar el PEM si lo pegaron completo
            if '-----BEGIN CERTIFICATE-----' in cert_raw:
                lineas = cert_raw.splitlines()
                b64_lineas = [l for l in lineas if not l.startswith('-----')]
                certificado_b64 = ''.join(b64_lineas).strip()
            else:
                certificado_b64 = cert_raw

        # Validar que sea base64 válido y decodificable
        certificado_b64_clean = re.sub(r'\s+', '', certificado_b64)
        if not re.match(r'^[A-Za-z0-9+/=]+$', certificado_b64_clean):
            return Response({'error': 'El certificado no parece ser base64 válido.'}, status=400)
        try:
            decoded = b64lib.b64decode(certificado_b64_clean)
            if len(decoded) < 100:
                return Response({'error': 'El certificado parece demasiado corto. Verificá que sea correcto.'}, status=400)
        except Exception:
            return Response({'error': 'No se pudo decodificar el base64 del certificado.'}, status=400)

        tienda.certificado_afip = certificado_b64_clean
        tienda.save(update_fields=['certificado_afip'])
        logger.info(f"Certificado ARCA cargado para tienda {tienda.id} ({len(decoded)} bytes)")

        return Response({'success': True, 'message': 'Certificado guardado correctamente.'})

    @action(detail=True, methods=['get'], url_path='mercadolibre/status')
    def ml_status(self, request, pk=None):
        """Verifica el estado de la conexión con Mercado Libre"""
        tienda = self.get_object()
        
        # Verificar si los campos de ML existen
        if not self._ml_fields_exist(tienda):
            return Response({
                'connected': False,
                'authenticated': False,
                'plataforma_ecommerce': 'NINGUNA',
                'message': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.',
                'migrations_required': True
            })
        
        if not self._ml_configured(tienda):
            return Response({
                'connected': False,
                'authenticated': False,
                'plataforma_ecommerce': getattr(tienda, 'plataforma_ecommerce', 'NINGUNA'),
                'message': 'La tienda no está configurada para Mercado Libre'
            })
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        has_token = bool(getattr(tienda, 'ml_access_token', None))
        has_app_id = bool(getattr(tienda, 'ml_app_id', None))
        has_client_secret = bool(getattr(tienda, 'ml_client_secret', None))
        
        return Response({
            'connected': has_token and has_app_id and has_client_secret,
            'authenticated': has_token and has_app_id and has_client_secret,
            'plataforma_ecommerce': getattr(tienda, 'plataforma_ecommerce', 'NINGUNA'),
            'has_token': has_token,
            'has_app_id': has_app_id,
            'has_client_secret': has_client_secret,
            'user_id': getattr(tienda, 'ml_user_id', None),
            'modo_test': getattr(tienda, 'ml_modo_test', True),
            'token_expires_at': getattr(tienda, 'ml_token_expires_at', None)
        })
    
    @action(detail=True, methods=['get'], url_path='mercadolibre/auth-url')
    def ml_auth_url(self, request, pk=None):
        """Genera la URL de autorización OAuth para Mercado Libre"""
        tienda = self.get_object()
        
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Obtener la URL de redirección desde el request o usar la configurada
        import os
        redirect_uri = request.query_params.get('redirect_uri')
        if not redirect_uri:
            worker_url = os.environ.get('ML_OAUTH_WORKER_URL', '').strip()
            if worker_url:
                # Usar Cloudflare Worker como proxy (evita 403 CloudFront desde Render)
                redirect_uri = worker_url.rstrip('/')
            else:
                from django.conf import settings
                if not settings.DEBUG:
                    redirect_uri = 'https://bonito-amor-backend.onrender.com/api/tiendas/mercadolibre/callback/'
                else:
                    scheme = request.scheme
                    host = request.get_host()
                    redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
        
        # Generar state aleatorio y asociarlo al tienda_id en cache (10 min)
        import uuid
        state = f"{pk}:{uuid.uuid4().hex}"
        cache.set(f"ml_oauth_state_{state}", str(pk), timeout=600)

        try:
            auth_url = ml_service.get_authorization_url(redirect_uri, state=state)
            return Response({'auth_url': auth_url})
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/callback')
    def ml_oauth_callback(self, request, pk=None):
        """Procesa el callback de OAuth de Mercado Libre"""
        tienda = self.get_object()
        
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        code = request.data.get('code')
        if not code:
            return Response(
                {'error': 'Código de autorización no proporcionado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Obtener redirect_uri del request o construirla dinámicamente
        redirect_uri = request.data.get('redirect_uri')
        if not redirect_uri:
            # Construir la URL dinámicamente basándose en el request
            scheme = request.scheme  # http o https
            host = request.get_host()  # dominio del servidor
            redirect_uri = f"{scheme}://{host}/api/tiendas/{pk}/mercadolibre/callback/"
        
        try:
            tokens = ml_service.exchange_code_for_token(code, redirect_uri)
            
            # Guardar tokens en la tienda (usando getattr/setattr para seguridad)
            if hasattr(tienda, 'ml_access_token'):
                tienda.ml_access_token = tokens['access_token']
            if hasattr(tienda, 'ml_refresh_token'):
                tienda.ml_refresh_token = tokens.get('refresh_token')
            if hasattr(tienda, 'ml_user_id'):
                tienda.ml_user_id = tokens.get('user_id')
            
            # Calcular fecha de expiración
            if hasattr(tienda, 'ml_token_expires_at'):
                expires_in = tokens.get('expires_in', 21600)  # 6 horas por defecto
                tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            tienda.save()
            
            return Response({
                'success': True,
                'message': 'Autenticación exitosa',
                'user_id': getattr(tienda, 'ml_user_id', None)
            })
        except Exception as e:
            logger.error(f"Error en callback OAuth: {e}", exc_info=True)
            return Response(
                {'error': f'Error al procesar el callback: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get', 'post'], url_path='mercadolibre/callback', permission_classes=[permissions.AllowAny])
    def ml_oauth_callback_public(self, request):
        """
        Endpoint público para recibir el callback de OAuth de Mercado Libre
        Este endpoint NO requiere {tienda_id} en la URL, permitiendo que Mercado Libre
        redirija a una URL fija como /api/tiendas/mercadolibre/callback/
        
        GET: Maneja la redirección desde Mercado Libre (obtiene el código)
        POST: Intercambia el código por tokens
        """
        # Obtener tienda_id del request (puede venir en query params, body, o state)
        tienda_id = request.query_params.get('tienda_id') or request.data.get('tienda_id')
        tienda = None
        
        # Manejar GET (redirección desde Mercado Libre con code en query params)
        if request.method == 'GET':
            state = request.query_params.get('state')

            # PRIORIDAD 1: Resolver tienda_id desde state validado en cache
            if state:
                resolved = _resolve_tienda_id_from_state(state)
                if resolved:
                    tienda_id = resolved
                    try:
                        tienda = Tienda.objects.get(id=tienda_id)
                        logger.info(f"Tienda identificada desde state validado: {tienda_id}")
                        cache.delete(f"ml_oauth_state_{state}")
                    except Tienda.DoesNotExist:
                        logger.warning(f"State válido pero tienda no encontrada: {tienda_id}")
                else:
                    logger.warning(f"State inválido o expirado: '{state}'")

        # Si aún no tenemos tienda, intentar otras formas
        if not tienda:
            if tienda_id:
                try:
                    tienda = Tienda.objects.get(id=tienda_id)
                except Tienda.DoesNotExist:
                    return Response(
                        {'error': f'Tienda con ID {tienda_id} no encontrada'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Como último recurso, buscar tiendas configuradas con ML
                # Solo funciona si hay exactamente una tienda configurada
                tiendas_ml = Tienda.objects.filter(
                    plataforma_ecommerce='MERCADO_LIBRE'
                ).exclude(ml_app_id__isnull=True).exclude(ml_app_id='')

                if tiendas_ml.count() == 1:
                    tienda = tiendas_ml.first()
                    logger.info(f"Tienda identificada automáticamente (única configurada): {tienda.id}")
                elif tiendas_ml.count() == 0:
                    return Response(
                        {'error': 'No hay tiendas configuradas para Mercado Libre'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': 'No se pudo determinar la tienda. Múltiples tiendas configuradas. Proporciona tienda_id en el request o usa el parámetro state.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # Si llegamos aquí sin tienda, es un error
        if not tienda:
            return Response(
                {'error': 'No se pudo determinar la tienda'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
            if code:
                # Si tenemos la tienda identificada, procesar directamente
                if tienda:
                    # Procesar el callback directamente
                    from .services.mercadolibre_service import MercadoLibreService
                    ml_service = MercadoLibreService(tienda)
                    
                    from django.conf import settings
                    if not settings.DEBUG:
                        redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
                    else:
                        scheme = request.scheme
                        host = request.get_host()
                        redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
                    
                    try:
                        tokens = ml_service.exchange_code_for_token(code, redirect_uri)
                        
                        # Guardar tokens
                        if hasattr(tienda, 'ml_access_token'):
                            tienda.ml_access_token = tokens['access_token']
                        if hasattr(tienda, 'ml_refresh_token'):
                            tienda.ml_refresh_token = tokens.get('refresh_token')
                        if hasattr(tienda, 'ml_user_id'):
                            tienda.ml_user_id = tokens.get('user_id')
                        if hasattr(tienda, 'ml_token_expires_at'):
                            expires_in = tokens.get('expires_in', 21600)
                            tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                        
                        tienda.save()
                        
                        # Retornar HTML de éxito para el navegador
                        return HttpResponse(
                            f'<html><body><h1>✅ Autenticación exitosa</h1>'
                            f'<p>La integración con Mercado Libre se configuró correctamente para la tienda: {tienda.nombre}</p>'
                            f'<p>Puedes cerrar esta ventana.</p>'
                            f'<script>setTimeout(function(){{window.close();}}, 3000);</script></body></html>',
                            content_type='text/html'
                        )
                    except Exception as e:
                        logger.error(f"Error procesando callback GET: {e}", exc_info=True)
                        return HttpResponse(
                            f'<html><body><h1>❌ Error en autenticación</h1>'
                            f'<p>Error: {str(e)}</p></body></html>',
                            content_type='text/html',
                            status=400
                        )
                else:
                    # No se pudo identificar la tienda, retornar info para POST manual
                    return Response({
                        'success': False,
                        'message': 'Código recibido pero no se pudo identificar la tienda. Usa POST con tienda_id.',
                        'code': code
                    })
            else:
                return Response({
                    'message': 'Endpoint de callback de Mercado Libre. Esperando código de autorización.'
                })
        
        # Manejar POST (intercambiar código por tokens)
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        code = request.data.get('code') or request.query_params.get('code')
        if not code:
            return Response(
                {'error': 'Código de autorización no proporcionado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Usar la URL fija configurada en Mercado Libre
        from django.conf import settings
        if not settings.DEBUG:
            redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
        else:
            scheme = request.scheme
            host = request.get_host()
            redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
        
        try:
            tokens = ml_service.exchange_code_for_token(code, redirect_uri)
            
            # Guardar tokens en la tienda
            if hasattr(tienda, 'ml_access_token'):
                tienda.ml_access_token = tokens['access_token']
            if hasattr(tienda, 'ml_refresh_token'):
                tienda.ml_refresh_token = tokens.get('refresh_token')
            if hasattr(tienda, 'ml_user_id'):
                tienda.ml_user_id = tokens.get('user_id')
            
            # Calcular fecha de expiración
            if hasattr(tienda, 'ml_token_expires_at'):
                expires_in = tokens.get('expires_in', 21600)
                tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            tienda.save()
            
            return Response({
                'success': True,
                'message': 'Autenticación exitosa',
                'user_id': getattr(tienda, 'ml_user_id', None)
            })
        except Exception as e:
            logger.error(f"Error en callback OAuth público: {e}", exc_info=True)
            return Response(
                {'error': f'Error al procesar el callback: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='mercadolibre/items')
    def ml_list_items(self, request, pk=None):
        """
        Lista los productos/publicaciones del vendedor en Mercado Libre para selección.
        GET /api/tiendas/{id}/mercadolibre/items/?limit=100&offset=0
        """
        try:
            tienda = self.get_object()
            if not self._ml_fields_exist(tienda) or not self._ml_configured(tienda):
                return Response({'error': 'Integración ML no configurada'}, status=status.HTTP_400_BAD_REQUEST)
            if not getattr(tienda, 'ml_access_token', None):
                return Response({'error': 'Complete el flujo OAuth primero.'}, status=status.HTTP_400_BAD_REQUEST)
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            limit = min(int(request.query_params.get('limit', 100)), 200)
            offset = int(request.query_params.get('offset', 0))
            data = ml_service.get_items_with_details(limit=limit, offset=offset)
            return Response(data, status=status.HTTP_200_OK)
        except MercadoLibreReconnectRequired as e:
            return Response({'error': str(e), 'reconnect_required': True}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error listando items ML: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/import-products')
    def ml_import_products(self, request, pk=None):
        """
        Importa productos desde Mercado Libre hacia Total Stock (sincronización inversa).
        POST /api/tiendas/{id}/mercadolibre/import-products/
        Body: {"solo_nuevos": true} - si true, solo importa no vinculados
              {"ml_item_ids": ["MLA123", ...]} - importar solo los items seleccionados
        """
        try:
            tienda = self.get_object()
            
            if not self._ml_fields_exist(tienda):
                return Response(
                    {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not self._ml_configured(tienda):
                return Response(
                    {'error': 'La tienda no está configurada para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not getattr(tienda, 'ml_access_token', None):
                return Response(
                    {'error': 'No hay token de acceso configurado. Complete el flujo OAuth primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            
            solo_nuevos = request.data.get('solo_nuevos', True)
            ml_item_ids = request.data.get('ml_item_ids', None)
            
            if ml_item_ids:
                all_item_ids = list(ml_item_ids)
            else:
                all_item_ids = []
                offset = 0
                limit = 50
                while True:
                    items_data = ml_service.get_items(limit=limit, offset=offset)
                    results = items_data.get('results', [])
                    if not results:
                        break
                    all_item_ids.extend(results)
                    offset += limit
                    if offset >= items_data.get('paging', {}).get('total', 0):
                        break
            
            import_results = {'success': 0, 'errors': 0, 'details': [], 'actualizados': 0}
            
            for ml_item_id in all_item_ids:
                try:
                    # Si solo_nuevos (y no es importación por selección) y ya existe vinculado, omitir
                    if not ml_item_ids and solo_nuevos and Producto.objects.filter(tienda=tienda, ml_item_id=ml_item_id).exists():
                        continue
                    
                    # Obtener datos completos del item
                    item_data = ml_service.get_item(ml_item_id)
                    if not item_data:
                        import_results['errors'] += 1
                        import_results['details'].append({
                            'ml_item_id': ml_item_id,
                            'nombre': ml_item_id,
                            'status': 'error',
                            'message': 'No se pudo obtener información del item'
                        })
                        continue
                    
                    producto_existia = Producto.objects.filter(tienda=tienda, ml_item_id=ml_item_id).exists()
                    producto = ml_service.create_producto_from_ml_item(tienda, item_data)
                    
                    if producto:
                        if producto_existia:
                            import_results['actualizados'] += 1
                            import_results['details'].append({
                                'producto_id': str(producto.id),
                                'ml_item_id': ml_item_id,
                                'nombre': producto.nombre,
                                'status': 'success',
                                'message': 'Producto actualizado'
                            })
                        else:
                            import_results['success'] += 1
                            import_results['details'].append({
                                'producto_id': str(producto.id),
                                'ml_item_id': ml_item_id,
                                'nombre': producto.nombre,
                                'status': 'success',
                                'message': 'Producto importado'
                            })
                    else:
                        import_results['errors'] += 1
                        import_results['details'].append({
                            'ml_item_id': ml_item_id,
                            'nombre': item_data.get('title', ml_item_id),
                            'status': 'error',
                            'message': 'No se pudo crear el producto'
                        })
                        
                except Exception as e:
                    import_results['errors'] += 1
                    import_results['details'].append({
                        'ml_item_id': ml_item_id,
                        'nombre': ml_item_id,
                        'status': 'error',
                        'message': str(e)[:200]
                    })
                    logger.error(f"Error importando item {ml_item_id}: {e}", exc_info=True)
            
            total = import_results['success'] + import_results['errors'] + import_results['actualizados']
            return Response({
                'message': f'Importación completada: {import_results["success"]} nuevos, {import_results["actualizados"]} actualizados, {import_results["errors"]} errores',
                'results': import_results,
                'total': total,
                'success': import_results['success'],
                'actualizados': import_results['actualizados'],
                'errors': import_results['errors']
            })
            
        except MercadoLibreReconnectRequired as e:
            return Response(
                {'error': str(e), 'reconnect_required': True},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al importar productos desde ML: {e}", exc_info=True)
            return Response(
                {'error': f'Error al importar productos: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/update-existing-products')
    def ml_update_existing_products(self, request, pk=None):
        """
        Actualiza precio y stock de productos que ya están vinculados con ML (desde ML hacia Total Stock).
        POST /api/tiendas/{id}/mercadolibre/update-existing-products/
        """
        try:
            tienda = self.get_object()
            if not self._ml_fields_exist(tienda) or not self._ml_configured(tienda):
                return Response({'error': 'Integración ML no configurada'}, status=status.HTTP_400_BAD_REQUEST)
            if not getattr(tienda, 'ml_access_token', None):
                return Response({'error': 'Complete el flujo OAuth primero.'}, status=status.HTTP_400_BAD_REQUEST)
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            
            productos = Producto.objects.filter(tienda=tienda, ml_item_id__isnull=False).exclude(ml_item_id='')
            results = {'success': 0, 'errors': 0, 'details': []}
            
            for producto in productos[:50]:
                try:
                    item_data = ml_service.get_item(producto.ml_item_id)
                    if not item_data:
                        results['errors'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': 'No se pudo obtener item'})
                        continue
                    out = ml_service.create_producto_from_ml_item(tienda, item_data)
                    if out:
                        results['success'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'success', 'message': 'Actualizado'})
                    else:
                        results['errors'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': 'Falló'})
                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': str(e)[:150]})
            
            return Response({
                'success': results['success'],
                'errors': results['errors'],
                'details': results['details']
            }, status=status.HTTP_200_OK)
        except MercadoLibreReconnectRequired as e:
            return Response({'error': str(e), 'reconnect_required': True}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error actualizando productos existentes: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/disconnect')
    def ml_disconnect(self, request, pk=None):
        """
        Desconecta la integración de Mercado Libre (borra tokens).
        Después el usuario puede volver a autorizar con la misma o otra cuenta/App.
        """
        tienda = self.get_object()
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        tienda.ml_access_token = None
        tienda.ml_refresh_token = None
        if hasattr(tienda, 'ml_token_expires_at'):
            tienda.ml_token_expires_at = None
        tienda.save()
        return Response({
            'success': True,
            'message': 'Integración de Mercado Libre desconectada. Podés volver a conectar desde Configuración > Mercado Libre.'
        })

    @action(detail=True, methods=['post'], url_path='mercadolibre/sync-stock')
    def ml_sync_stock(self, request, pk=None):
        """
        Actualiza solo el stock de productos ya sincronizados con Mercado Libre
        POST /api/tiendas/{id}/mercadolibre/sync-stock/
        Body opcional: {"producto_ids": ["uuid1", "uuid2"]} - Si no se especifica, actualiza todos
        """
        try:
            tienda = self.get_object()
            
            if not self._ml_fields_exist(tienda):
                return Response(
                    {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not self._ml_configured(tienda):
                return Response(
                    {'error': 'La tienda no está configurada para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not getattr(tienda, 'ml_access_token', None):
                return Response(
                    {'error': 'No hay token de acceso configurado. Complete el flujo OAuth primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            
            ml_service = MercadoLibreService(tienda)
            
            # Obtener parámetros opcionales del request
            producto_ids = request.data.get('producto_ids', None)
            
            # Obtener productos que ya están sincronizados
            # Primero intentar con productos que tienen ml_item_id
            if producto_ids:
                productos = Producto.objects.filter(
                    tienda=tienda, 
                    id__in=producto_ids,
                    ml_item_id__isnull=False
                ).exclude(ml_item_id='')
            else:
                # Actualizar todos los productos sincronizados (que tengan ml_item_id)
                productos = Producto.objects.filter(
                    tienda=tienda,
                    ml_item_id__isnull=False
                ).exclude(ml_item_id='')
            
            # Inicializar sync_results primero
            sync_results = {
                'success': 0,
                'errors': 0,
                'details': [],
                'total_encontrados': 0
            }
            
            # Log para debugging
            total_productos = productos.count()
            logger.info(f"Productos encontrados para actualizar stock: {total_productos}")
            sync_results['total_encontrados'] = total_productos
            
            # Si no hay productos con ml_item_id, buscar productos sincronizados sin ml_item_id
            if total_productos == 0:
                productos_sin_item_id = Producto.objects.filter(
                    tienda=tienda,
                    ml_sincronizado=True
                ).filter(
                    Q(ml_item_id__isnull=True) | Q(ml_item_id='')
                )
                
                count_sin_item_id = productos_sin_item_id.count()
                logger.warning(f"No se encontraron productos con ml_item_id. "
                             f"Productos con ml_sincronizado=True pero sin ml_item_id: {count_sin_item_id}")
                
                # Intentar buscar el ml_item_id en Mercado Libre para estos productos
                if count_sin_item_id > 0:
                    logger.info(f"Intentando recuperar ml_item_id desde Mercado Libre para {count_sin_item_id} productos...")
                    productos_recuperados = 0
                    for prod in productos_sin_item_id[:10]:  # Limitar a 10 para no sobrecargar
                        try:
                            # Buscar el producto en ML por título (esto es aproximado)
                            # Nota: ML no tiene un endpoint directo de búsqueda por seller y título,
                            # así que esto es una aproximación. Mejor sería guardar el ml_item_id correctamente.
                            logger.warning(f"Producto {prod.nombre} (ID: {prod.id}) tiene ml_sincronizado=True pero no tiene ml_item_id. "
                                        f"Por favor, vuelve a sincronizar este producto para obtener el ml_item_id.")
                        except Exception as e:
                            logger.error(f"Error al intentar recuperar ml_item_id para {prod.nombre}: {e}")
                    
                    # Agregar estos productos a la lista pero con un mensaje de advertencia
                    sync_results['details'].append({
                        'status': 'warning',
                        'message': f'{count_sin_item_id} producto(s) tienen ml_sincronizado=True pero no tienen ml_item_id. '
                                 f'Por favor, vuelve a sincronizar estos productos para actualizar su stock.'
                    })
            
            # Actualizar cada producto (limitar a 20 productos por vez)
            productos_list = list(productos[:20])
            if total_productos > 20:
                logger.warning(f"Se actualizarán solo los primeros 20 de {total_productos} productos")
            
            for producto in productos_list:
                try:
                    logger.info(f"Actualizando stock de {producto.nombre} (ML Item: {producto.ml_item_id}): {producto.stock}")
                    updated_item = ml_service.sync_stock(producto)
                    
                    sync_results['success'] += 1
                    sync_results['details'].append({
                        'producto_id': str(producto.id),
                        'nombre': producto.nombre,
                        'ml_item_id': producto.ml_item_id,
                        'stock_actualizado': producto.stock,
                        'status': 'success',
                        'message': f'Stock actualizado a {producto.stock}'
                    })
                    
                except Exception as e:
                    sync_results['errors'] += 1
                    error_msg = str(e)
                    
                    # Extraer detalles del error
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = f"{e.response.status_code}: {error_data.get('message', str(error_data))}"
                        except:
                            error_msg = f"{e.response.status_code}: {e.response.text[:200]}"
                    
                    logger.error(f"Error al actualizar stock de {producto.nombre}: {error_msg}")
                    sync_results['details'].append({
                        'producto_id': str(producto.id),
                        'nombre': producto.nombre,
                        'ml_item_id': producto.ml_item_id,
                        'status': 'error',
                        'error': error_msg
                    })
            
            return Response(sync_results, status=status.HTTP_200_OK)
            
        except MercadoLibreReconnectRequired as e:
            return Response(
                {'error': str(e), 'reconnect_required': True},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al sincronizar stock: {e}", exc_info=True)
            return Response(
                {'error': f'Error al sincronizar stock: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get', 'post'], url_path='mercadolibre/webhook')
    def ml_webhook(self, request, pk=None):
        """
        Endpoint para recibir notificaciones de Mercado Libre cuando se vende un producto
        GET/POST /api/tiendas/{id}/mercadolibre/webhook/
        
        GET: Validación inicial de Mercado Libre (verifica que el endpoint existe)
        POST: Notificaciones reales de Mercado Libre
        
        Mercado Libre enviará notificaciones cuando:
        - Se crea una orden/pedido
        - Se confirma un pago
        - Se cancela una orden
        """
        try:
            # Intentar obtener la tienda usando pk del kwargs o del request
            tienda_id = pk or self.kwargs.get('pk')
            
            if not tienda_id:
                logger.warning("Webhook llamado sin ID de tienda")
                return Response({
                    'status': 'error',
                    'message': 'ID de tienda no proporcionado'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            try:
                tienda = Tienda.objects.get(pk=tienda_id)
            except Tienda.DoesNotExist:
                # Si no se encuentra la tienda, loguear y retornar 200 OK para que ML no reenvíe
                logger.warning(f"Tienda no encontrada para webhook: {tienda_id}")
                return Response({
                    'status': 'error',
                    'message': f'Tienda con ID {tienda_id} no encontrada en la base de datos'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            except Exception as e:
                logger.error(f"Error al obtener tienda {tienda_id}: {str(e)}")
                return Response({
                    'status': 'error',
                    'message': f'Error al obtener tienda: {str(e)}'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            # Verificar si los campos de ML existen
            if not self._ml_fields_exist(tienda):
                logger.warning(f"Campos de ML no disponibles para tienda {tienda.id}")
                return Response({
                    'status': 'error',
                    'message': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            if not self._ml_configured(tienda):
                logger.warning(f"Tienda {tienda.id} no está configurada para Mercado Libre")
                return Response({
                    'status': 'error',
                    'message': 'La tienda no está configurada para Mercado Libre'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            # Manejar petición GET (validación de Mercado Libre)
            if request.method == 'GET':
                # Mercado Libre hace una petición GET para validar que el endpoint existe
                # Debe responder con 200 OK
                logger.info(f"Validación de webhook desde Mercado Libre para tienda {tienda.id}")
                return Response({
                    'status': 'ok',
                    'message': 'Webhook configurado correctamente',
                    'tienda_id': str(tienda.id)
                }, status=status.HTTP_200_OK)
            
            # Mercado Libre envía notificaciones en formato JSON
            # Topic "orders" (legacy) o "orders_v2" (recomendado desde 2019+)
            # Estructura: {"resource": "/orders/123456", "topic": "orders_v2"}
            resource = request.data.get('resource', '')
            topic = request.data.get('topic', '')
            
            # Aceptar ambos topics: orders (legacy) y orders_v2 (recomendado por ML)
            topic_orders = topic in ('orders', 'orders_v2')
            
            logger.info(f"Notificación recibida de ML: topic={topic}, resource={resource}")
            
            if topic_orders and resource and '/orders/' in resource:
                # Extraer solo el ID numérico de la orden: /orders/123 y /orders/123/shipments → "123"
                # Así evitamos procesar dos veces la misma orden cuando ML notifica retiro/entrega (resource con /shipments)
                raw_suffix = resource.split('/orders/')[-1].split('?')[0].strip()
                order_id = raw_suffix.split('/')[0].strip() if raw_suffix else ''
                is_shipment_update = '/shipments' in resource or raw_suffix.startswith('shipments')
                
                if not order_id:
                    logger.warning(f"Webhook ML: no se pudo extraer order_id de resource={resource}")
                    return Response({'status': 'ok', 'message': 'Resource sin order_id'}, status=status.HTTP_200_OK)
                
                try:
                    from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
                    
                    # Notificaciones de envío/retiro: no crear nueva venta ni facturar; la venta ya existe
                    if is_shipment_update:
                        logger.info(f"Webhook ML: actualización de envío para orden {order_id}, no se crea nueva venta")
                        return Response({
                            'status': 'success',
                            'message': 'Actualización de envío, orden ya procesada',
                            'order_id': order_id
                        }, status=status.HTTP_200_OK)
                    
                    ml_service = MercadoLibreService(tienda)

                    # Evitar procesar la misma orden dos veces (p. ej. doble notificación por pago + entrega)
                    venta_existente_ml = Venta.objects.filter(tienda=tienda, origen_mercadolibre=True, ml_order_id=order_id).first()
                    if venta_existente_ml:
                        # Siempre se pide la orden acá (antes solo se pedía si faltaban fees), porque
                        # es la única forma de enterarnos de que ML canceló una orden ya procesada --
                        # sin esto, la notificación de cancelación se ignoraba por completo.
                        order_para_fees = None
                        try:
                            order_para_fees = ml_service.get_order(order_id)
                        except Exception as order_err:
                            logger.warning(f"No se pudo obtener orden {order_id} de ML para revisar estado/fees: {order_err}")

                        order_status_actual = (order_para_fees or {}).get('status', '')

                        if order_status_actual == 'cancelled' and not venta_existente_ml.anulada:
                            try:
                                _procesar_cancelacion_orden_ml(venta_existente_ml, order_id)
                            except Exception as cancel_err:
                                logger.error(f"Error al procesar cancelación de orden ML {order_id}: {cancel_err}", exc_info=True)
                            return Response({
                                'status': 'success',
                                'message': 'Orden cancelada: venta anulada y stock repuesto',
                                'order_id': order_id
                            }, status=status.HTTP_200_OK)

                        # Intentar actualizar fees que aún están en cero (ML los calcula con demora)
                        fees_incompletos = (
                            (venta_existente_ml.ml_sale_fee or Decimal('0.00')) == Decimal('0.00') or
                            (venta_existente_ml.ml_shipping_cost or Decimal('0.00')) == Decimal('0.00') or
                            (venta_existente_ml.ml_tax_fee or Decimal('0.00')) == Decimal('0.00')
                        )
                        if fees_incompletos:
                            try:
                                if order_para_fees:
                                    _sale_fee = Decimal('0.00')
                                    _ship = Decimal('0.00')
                                    _tax = Decimal('0.00')
                                    # Comisión desde order_items[].sale_fee
                                    for oi in (order_para_fees.get('order_items') or []):
                                        _sale_fee += abs(Decimal(str(oi.get('sale_fee') or 0)))
                                    # Envío e impuestos desde payments[]
                                    for pay in (order_para_fees.get('payments') or []):
                                        _ship += abs(Decimal(str(pay.get('shipping_cost') or 0)))
                                        _tax  += abs(Decimal(str(pay.get('taxes_amount') or 0)))
                                        _mp = abs(Decimal(str(pay.get('marketplace_fee') or 0)))
                                        if _mp > 0 and _sale_fee == Decimal('0.00'):
                                            _sale_fee = _mp
                                    # Solo actualizar campos que aún están en cero
                                    update_fields = []
                                    if _sale_fee and (venta_existente_ml.ml_sale_fee or Decimal('0.00')) == Decimal('0.00'):
                                        venta_existente_ml.ml_sale_fee = _sale_fee
                                        update_fields.append('ml_sale_fee')
                                    if _ship and (venta_existente_ml.ml_shipping_cost or Decimal('0.00')) == Decimal('0.00'):
                                        venta_existente_ml.ml_shipping_cost = _ship
                                        update_fields.append('ml_shipping_cost')
                                    if _tax and (venta_existente_ml.ml_tax_fee or Decimal('0.00')) == Decimal('0.00'):
                                        venta_existente_ml.ml_tax_fee = _tax
                                        update_fields.append('ml_tax_fee')
                                    if update_fields:
                                        venta_existente_ml.save(update_fields=update_fields)
                                        logger.info(f"Orden {order_id}: fees actualizados {update_fields} (sale={_sale_fee}, shipping={_ship}, tax={_tax})")
                                    else:
                                        logger.info(f"Orden {order_id}: fees incompletos pero ML aún no los calculó")
                            except Exception as fee_err:
                                logger.warning(f"Error al actualizar fees de orden {order_id}: {fee_err}")
                        else:
                            logger.info(f"Orden {order_id} ya procesada anteriormente, omitiendo")
                        return Response({
                            'status': 'success',
                            'message': 'Orden ya procesada',
                            'order_id': order_id
                        }, status=status.HTTP_200_OK)

                    order = ml_service.get_order(order_id)
                    
                    if order:
                        order_status = order.get('status', '')
                        order_total = Decimal(str(order.get('total_amount', 0)))
                        order_date_str = order.get('date_created') or order.get('date_closed') or ''
                        order_date = None
                        if order_date_str:
                            try:
                                order_date = timezone.datetime.fromisoformat(
                                    str(order_date_str).replace('Z', '+00:00')
                                )
                            except (ValueError, TypeError):
                                pass
                        
                        # Ventas antiguas sin ml_order_id: detectar por total + fecha para evitar refacturar
                        venta_existente = None
                        if order_total and order_status in ('paid', 'confirmed', 'delivered'):
                            ventas_ml_sin_order = Venta.objects.filter(
                                tienda=tienda,
                                origen_mercadolibre=True,
                                ml_order_id__isnull=True
                            ).filter(
                                total=order_total
                            )
                            if order_date:
                                desde = order_date - timedelta(days=30)
                                hasta = order_date + timedelta(days=2)
                                ventas_ml_sin_order = ventas_ml_sin_order.filter(
                                    fecha_venta__date__gte=desde.date(),
                                    fecha_venta__date__lte=hasta.date()
                                )
                            venta_existente = ventas_ml_sin_order.first()
                        
                        if venta_existente:
                            venta_existente.ml_order_id = order_id
                            venta_existente.save()
                            logger.info(f"Orden {order_id} ya procesada (venta antigua sin ml_order_id), backfill y omitiendo")
                            return Response({
                                'status': 'success',
                                'message': 'Orden ya procesada',
                                'order_id': order_id
                            }, status=status.HTTP_200_OK)
                        
                        # Procesar la orden y actualizar stock
                        
                        # Solo procesar órdenes confirmadas o pagadas
                        # paid = venta confirmada y cobrada (estado típico tras cobro)
                        if order_status in ['confirmed', 'payment_required', 'payment_in_process', 'paid']:
                            order_items = order.get('order_items') or order.get('items') or []
                            
                            # Obtener el método de pago "Mercado Libre"
                            try:
                                metodo_pago_ml = MetodoPago.objects.get(nombre='Mercado Libre', activo=True)
                            except MetodoPago.DoesNotExist:
                                logger.error(f"Método de pago 'Mercado Libre' no encontrado. Creando automáticamente...")
                                metodo_pago_ml = MetodoPago.objects.create(
                                    nombre='Mercado Libre',
                                    descripcion='Ventas realizadas a través de Mercado Libre',
                                    activo=True,
                                    es_financiero=True
                                )
                            
                            # Leer fees reales de ML desde los campos documentados:
                            # - order_items[].sale_fee → comisión por ítem
                            # - payments[].marketplace_fee → comisión total (disponible post-acreditación)
                            # - payments[].shipping_cost → costo de envío al vendedor
                            # - payments[].taxes_amount → impuestos
                            ml_sale_fee = Decimal('0.00')
                            ml_shipping_cost = Decimal('0.00')
                            ml_tax_fee = Decimal('0.00')

                            # Comisión: sumar sale_fee de cada order_item
                            for oi in (order.get('order_items') or []):
                                ml_sale_fee += abs(Decimal(str(oi.get('sale_fee') or 0)))

                            # Envío e impuestos desde payments[]
                            for pay in (order.get('payments') or []):
                                ml_shipping_cost += abs(Decimal(str(pay.get('shipping_cost') or 0)))
                                ml_tax_fee += abs(Decimal(str(pay.get('taxes_amount') or 0)))
                                # marketplace_fee es la comisión total; usarlo si sale_fee vino en 0
                                _mp = abs(Decimal(str(pay.get('marketplace_fee') or 0)))
                                if _mp > 0 and ml_sale_fee == Decimal('0.00'):
                                    ml_sale_fee = _mp

                            logger.info(f"ML fees para orden {order_id}: sale={ml_sale_fee}, shipping={ml_shipping_cost}, tax={ml_tax_fee}")

                            # Preparar detalles de venta y calcular totales (arancel + costo envío por producto)
                            detalles_venta = []
                            total_venta = Decimal('0.00')
                            total_arancel = Decimal('0.00')
                            total_costo_envio = Decimal('0.00')
                            
                            for item in order_items:
                                ml_item_id = item.get('item', {}).get('id')
                                quantity = item.get('quantity', 0)
                                
                                # Precio real de venta: unit_price es "después de descuentos" (ML)
                                # NO usar full_unit_price ni item.price como prioritario (son precio original)
                                unit_price = Decimal(str(item.get('unit_price', 0)))
                                if unit_price <= 0:
                                    # Fallback: total pagado por este ítem / cantidad
                                    item_total = Decimal(str(item.get('total_amount', 0)))
                                    if item_total > 0 and quantity > 0:
                                        unit_price = item_total / quantity
                                if unit_price <= 0:
                                    item_data = item.get('item', {})
                                    unit_price = Decimal(str(item_data.get('price', 0)))
                                if unit_price <= 0:
                                    try:
                                        producto_temp = Producto.objects.get(tienda=tienda, ml_item_id=ml_item_id)
                                        unit_price = producto_temp.precio
                                        logger.warning(f"Precio no en orden ML, usando sistema: ${unit_price} para {producto_temp.nombre}")
                                    except Producto.DoesNotExist:
                                        unit_price = Decimal('0.00')
                                        logger.error(f"No se pudo obtener precio para item {ml_item_id}")
                                
                                if ml_item_id and unit_price > 0:
                                    # Buscar el producto en nuestro sistema por ml_item_id
                                    # Si no existe, crearlo automáticamente desde los datos de ML (sincronización inversa)
                                    producto = None
                                    try:
                                        producto = Producto.objects.get(
                                            tienda=tienda,
                                            ml_item_id=ml_item_id
                                        )
                                    except Producto.DoesNotExist:
                                        # Producto no vinculado: importarlo desde ML para poder registrar la venta
                                        try:
                                            item_full = ml_service.get_item(ml_item_id)
                                            if item_full:
                                                producto = ml_service.create_producto_from_ml_item(tienda, item_full)
                                                if producto:
                                                    logger.info(f"Producto creado automáticamente desde orden ML: {producto.nombre} (ml_item_id: {ml_item_id})")
                                        except Exception as import_err:
                                            logger.error(f"No se pudo importar producto {ml_item_id} desde ML: {import_err}", exc_info=True)
                                    
                                    if producto:
                                        
                                        # Calcular subtotal del item
                                        subtotal_item = unit_price * quantity
                                        total_venta += subtotal_item
                                        
                                        # Calcular arancel y costo envío según ArancelMercadoLibreProducto
                                        arancel_item = Decimal('0.00')
                                        costo_envio_item = Decimal('0.00')
                                        if ArancelMercadoLibreProducto is not None:
                                            try:
                                                arancel_ml = ArancelMercadoLibreProducto.objects.filter(
                                                    tienda=tienda,
                                                    producto=producto
                                                ).first()
                                                if arancel_ml:
                                                    arancel_porcentaje = arancel_ml.arancel_porcentaje
                                                    arancel_item = subtotal_item * (arancel_porcentaje / Decimal('100'))
                                                    total_arancel += arancel_item
                                                    costo_envio_item = (arancel_ml.costo_envio or Decimal('0')) * quantity
                                                    total_costo_envio += costo_envio_item
                                                    logger.info(f"Arancel {arancel_porcentaje}% + envío ${costo_envio_item} para {producto.nombre}")
                                            except Exception as e:
                                                logger.error(f"Error al calcular arancel/envío para producto {producto.nombre}: {e}")
                                        
                                        # Agregar detalle de venta
                                        detalles_venta.append({
                                            'producto': producto.id,
                                            'cantidad': quantity,
                                            'precio_unitario': float(unit_price),
                                            'costo_unitario': float(producto.costo) if producto.costo else None,
                                            'subtotal': float(subtotal_item),
                                            'arancel_item': float(arancel_item)
                                        })
                                        
                                        # Actualizar stock: restar la cantidad vendida
                                        producto.stock = max(0, producto.stock - quantity)
                                        producto.save()
                                        
                                        logger.info(f"Stock actualizado para {producto.nombre}: -{quantity} unidades (nuevo stock: {producto.stock})")
                                    else:
                                        logger.warning(f"Producto con ml_item_id {ml_item_id} no encontrado y no se pudo importar desde ML")
                            
                            # Crear la venta en el sistema si hay detalles
                            if detalles_venta:
                                try:
                                    usuario_ml, created = User.objects.get_or_create(
                                        username='mercadolibre',
                                        defaults={
                                            'first_name': 'Mercado Libre',
                                            'is_staff': False,
                                            'is_active': True,
                                        }
                                    )
                                    if created:
                                        usuario_ml.set_unusable_password()
                                        usuario_ml.save()
                                    try:
                                        venta = Venta.objects.create(
                                            tienda=tienda,
                                            metodo_pago=metodo_pago_ml.nombre,
                                            total=total_venta,
                                            arancel_total=total_arancel,
                                            costo_envio_ml=total_costo_envio,
                                            ml_sale_fee=ml_sale_fee,
                                            ml_shipping_cost=ml_shipping_cost,
                                            ml_tax_fee=ml_tax_fee,
                                            origen_mercadolibre=True,
                                            ml_order_id=order_id,
                                            usuario=usuario_ml,
                                            fecha_venta=timezone.now()
                                        )
                                    except Exception as create_err:
                                        from django.db import IntegrityError
                                        err_str = str(create_err).lower()
                                        if isinstance(create_err, IntegrityError) and (
                                            'unique_ml_order_per_tienda' in err_str or
                                            'duplicate key' in err_str or
                                            'unique constraint' in err_str
                                        ):
                                            logger.info(f"Orden {order_id} ya creada por otro request (race), omitiendo")
                                            return Response({
                                                'status': 'success',
                                                'message': 'Orden ya procesada',
                                                'order_id': order_id
                                            }, status=status.HTTP_200_OK)
                                        raise
                                    
                                    # Crear los detalles de venta
                                    for detalle_data in detalles_venta:
                                        producto_obj = Producto.objects.get(id=detalle_data['producto'])
                                        DetalleVenta.objects.create(
                                            venta=venta,
                                            producto=producto_obj,
                                            cantidad=detalle_data['cantidad'],
                                            precio_unitario=Decimal(str(detalle_data['precio_unitario'])),
                                            costo_unitario=Decimal(str(detalle_data['costo_unitario'])) if detalle_data['costo_unitario'] else None,
                                            subtotal=Decimal(str(detalle_data['subtotal']))
                                        )
                                    
                                    logger.info(f"Venta de Mercado Libre registrada: ID {venta.id}, Total: ${total_venta}, Arancel: ${total_arancel}, Envío: ${total_costo_envio}")
                                    
                                    # Enviar notificación push (igual que en ventas manuales)
                                    try:
                                        from .services.notificaciones_service import NotificacionesService
                                        NotificacionesService.enviar_notificacion_venta(venta)
                                    except Exception as notif_err:
                                        logger.warning(f"Error al enviar notificación push por venta ML {venta.id}: {notif_err}")
                                    
                                    # Facturación automática: solo si está habilitado para ML (sino solo recibo)
                                    if getattr(venta.tienda, 'ml_facturar_ventas', True) and venta.tienda.tipo_facturacion and venta.tienda.tipo_facturacion != 'NINGUNA':
                                        try:
                                            # Preferir datos de facturación de ML (nombre, DNI, dirección) si existe el endpoint
                                            cliente_nombre = 'Consumidor Final'
                                            cliente_domicilio = ''
                                            cliente_cuit_dni = ''
                                            billing = ml_service.get_order_billing_info(order_id)
                                            # API ML v2: datos están en buyer.billing_info (name, last_name, identification, address)
                                            bi = {}
                                            if billing and isinstance(billing, dict):
                                                bi = billing.get('buyer', {}) or {}
                                                if isinstance(bi, dict):
                                                    bi = bi.get('billing_info', {}) or {}
                                            if not isinstance(bi, dict):
                                                bi = {}
                                            if bi:
                                                first = (bi.get('name') or bi.get('first_name') or '').strip()
                                                last = (bi.get('last_name') or '').strip()
                                                if first or last:
                                                    cliente_nombre = f"{first} {last}".strip()[:255] or cliente_nombre
                                                ident = bi.get('identification', {})
                                                if isinstance(ident, dict):
                                                    cliente_cuit_dni = (ident.get('number') or '').strip()
                                                elif isinstance(ident, str):
                                                    cliente_cuit_dni = ident.strip()
                                                addr = bi.get('address', {})
                                                if isinstance(addr, dict):
                                                    street = (addr.get('street_name') or addr.get('address_line') or '')
                                                    number = (addr.get('street_number') or '')
                                                    city = (addr.get('city_name') or (addr.get('city', {}).get('name') if isinstance(addr.get('city'), dict) else ''))
                                                    state = (addr.get('state', {}).get('name') if isinstance(addr.get('state'), dict) else '') or addr.get('state_name', '')
                                                    zipcode = addr.get('zip_code', '')
                                                    parts = [p for p in [street, number, city, state, zipcode] if p]
                                                    if parts:
                                                        cliente_domicilio = ' '.join(parts)[:255]
                                            # Fallback: datos desde la orden (buyer, shipment)
                                            if cliente_nombre == 'Consumidor Final' or not cliente_domicilio:
                                                buyer = order.get('buyer', {})
                                                if buyer and cliente_nombre == 'Consumidor Final':
                                                    nickname = buyer.get('nickname', '')
                                                    if nickname:
                                                        cliente_nombre = f"Comprador ML {nickname}"[:255]
                                                if not cliente_domicilio:
                                                    shipment = order.get('shipment', {}) or order.get('shipping', {})
                                                    if isinstance(shipment, dict):
                                                        receiver_addr = shipment.get('receiver_address', {}) or shipment.get('address', {})
                                                        if isinstance(receiver_addr, dict):
                                                            address_line = receiver_addr.get('address_line', '') or receiver_addr.get('street_name', '')
                                                            city = receiver_addr.get('city', {}).get('name', '') if isinstance(receiver_addr.get('city'), dict) else ''
                                                            if address_line or city:
                                                                cliente_domicilio = f"{address_line} {city}".strip()[:255]
                                            
                                            cliente_data = {
                                                'cliente_nombre': cliente_nombre,
                                                'cliente_cuit': cliente_cuit_dni,
                                                'cliente_domicilio': cliente_domicilio or 'Sin especificar',
                                                'cliente_tipo_documento': '99',
                                                'cliente_condicion_iva': 'CF'
                                            }
                                            exito, datos_factura, error = FacturacionService(venta.tienda).emitir_factura(venta, cliente_data)
                                            if exito:
                                                Factura.objects.create(
                                                    venta=venta,
                                                    tienda=venta.tienda,
                                                    numero_comprobante=datos_factura.get('numero_comprobante'),
                                                    punto_venta=datos_factura.get('punto_venta', venta.tienda.punto_venta),
                                                    tipo_comprobante=datos_factura.get('tipo_comprobante', 'B'),
                                                    cliente_nombre=cliente_data['cliente_nombre'],
                                                    cliente_cuit=cliente_data.get('cliente_cuit', ''),
                                                    cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                                                    cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                                                    cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                                                    subtotal=datos_factura.get('subtotal', venta.total),
                                                    impuesto_iva=datos_factura.get('impuesto_iva', Decimal('0.00')),
                                                    total=datos_factura.get('total', venta.total),
                                                    estado='EMITIDA',
                                                    sistema_facturacion=venta.tienda.tipo_facturacion,
                                                    cae=datos_factura.get('cae'),
                                                    fecha_vencimiento_cae=datos_factura.get('fecha_vencimiento_cae'),
                                                    numero_comprobante_afip=datos_factura.get('numero_comprobante_afip'),
                                                    respuesta_bruta=datos_factura.get('respuesta_bruta'),
                                                )
                                                venta.facturada = True
                                                venta.cliente_nombre = cliente_data['cliente_nombre']
                                                venta.cliente_cuit = cliente_data.get('cliente_cuit', '') or None
                                                venta.cliente_domicilio = cliente_data.get('cliente_domicilio', '')
                                                venta.save()
                                                logger.info(f"Factura emitida automáticamente para venta ML {venta.id}")
                                            else:
                                                Factura.objects.create(
                                                    venta=venta,
                                                    tienda=venta.tienda,
                                                    punto_venta=venta.tienda.punto_venta,
                                                    tipo_comprobante='B',
                                                    cliente_nombre=cliente_data['cliente_nombre'],
                                                    cliente_cuit='', cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                                                    cliente_tipo_documento='99', cliente_condicion_iva='CF',
                                                    subtotal=venta.total, impuesto_iva=Decimal('0.00'), total=venta.total,
                                                    estado='ERROR',
                                                    sistema_facturacion=venta.tienda.tipo_facturacion,
                                                    error_mensaje=error,
                                                )
                                                logger.warning(f"No se pudo facturar automáticamente venta ML {venta.id}: {error}")
                                        except Exception as fact_err:
                                            logger.warning(f"Error al facturar automáticamente venta ML {venta.id}: {fact_err}", exc_info=True)
                                    
                                except Exception as e:
                                    logger.error(f"Error al crear venta desde orden ML {order_id}: {e}", exc_info=True)
                        else:
                            logger.info(f"Orden {order_id} con estado '{order_status}' no procesada (solo: confirmed, payment_required, payment_in_process, paid)")
                        
                        return Response({
                            'status': 'success',
                            'message': 'Orden procesada correctamente',
                            'order_id': order_id
                        })
                    else:
                        logger.warning(f"No se pudo obtener información de la orden {order_id}")
                        return Response({
                            'status': 'warning',
                            'message': 'Orden no encontrada o no se pudo obtener información'
                        }, status=status.HTTP_200_OK)
                        
                except MercadoLibreReconnectRequired as e:
                    logger.warning(f"Webhook ML: integración requiere reconexión (orden {order_id}): {e}")
                    return Response({
                        'status': 'error',
                        'message': 'Integración de Mercado Libre desconectada. Reconectá desde Configuración.'
                    }, status=status.HTTP_200_OK)
                except Exception as e:
                    logger.error(f"Error al procesar orden de ML: {e}", exc_info=True)
                    # Retornar 200 para que ML no reenvíe la notificación
                    return Response({
                        'status': 'error',
                        'message': f'Error al procesar orden: {str(e)}'
                    }, status=status.HTTP_200_OK)
            
            # ── Topic: shipments ─────────────────────────────────────────────
            # ML notifica cambios de estado del envío. Cuando status=delivered
            # guardamos la fecha de entrega real en la venta.
            if topic == 'shipments' and resource and '/shipments/' in resource:
                shipment_id = resource.split('/shipments/')[-1].split('?')[0].strip().split('/')[0]
                if shipment_id:
                    try:
                        from .services.mercadolibre_service import MercadoLibreService
                        ml_service_ship = MercadoLibreService(tienda)
                        shipment = ml_service_ship.get_shipment(shipment_id)
                        if shipment and shipment.get('status') == 'delivered':
                            # Buscar la venta por el shipment_id o por order_id del shipment
                            order_id_from_ship = str(shipment.get('order_id') or '')
                            venta_ship = None
                            if order_id_from_ship:
                                venta_ship = Venta.objects.filter(
                                    tienda=tienda,
                                    origen_mercadolibre=True,
                                    ml_order_id=order_id_from_ship
                                ).first()
                            if venta_ship and not venta_ship.ml_fecha_entrega:
                                # date_delivered o date_first_printed como fallback
                                fecha_str = (
                                    shipment.get('date_delivered') or
                                    shipment.get('status_history', {}).get('date_delivered') or
                                    shipment.get('date_last_modified')
                                )
                                if fecha_str:
                                    try:
                                        fecha_entrega = timezone.datetime.fromisoformat(
                                            str(fecha_str).replace('Z', '+00:00')
                                        )
                                        venta_ship.ml_fecha_entrega = fecha_entrega
                                        venta_ship.save(update_fields=['ml_fecha_entrega'])
                                        logger.info(f"Shipment {shipment_id}: entrega registrada el {fecha_entrega} para orden {order_id_from_ship}")
                                    except (ValueError, TypeError) as fe:
                                        logger.warning(f"Shipment {shipment_id}: no se pudo parsear fecha '{fecha_str}': {fe}")
                            elif venta_ship and venta_ship.ml_fecha_entrega:
                                logger.info(f"Shipment {shipment_id}: fecha de entrega ya registrada, omitiendo")
                    except Exception as ship_err:
                        logger.warning(f"Error procesando shipments topic (shipment {shipment_id}): {ship_err}")

            # ── Topic: payments ──────────────────────────────────────────────
            # ML notifica el pago con resource=/collections/{payment_id}
            # El endpoint /collections/{id} devuelve marketplace_fee, shipping_cost
            # y taxes_amount — datos que NO están disponibles en el order al momento
            # de la primera notificación (fee_details siempre llega vacío).
            if topic == 'payments' and resource and '/collections/' in resource:
                payment_id = resource.split('/collections/')[-1].split('?')[0].strip().split('/')[0]
                if payment_id:
                    try:
                        from .services.mercadolibre_service import MercadoLibreService
                        ml_service_pay = MercadoLibreService(tienda)
                        payment = ml_service_pay.get_payment(payment_id)
                        if payment:
                            order_id_from_pay = str(payment.get('order_id') or '')
                            if order_id_from_pay:
                                venta_pay = Venta.objects.filter(
                                    tienda=tienda,
                                    origen_mercadolibre=True,
                                    ml_order_id=order_id_from_pay
                                ).first()
                                if venta_pay:
                                    # /collections es la fuente autoritativa para shipping_cost y taxes_amount
                                    # (el order tiene shipping_cost sin impuestos sobre el envío).
                                    # Siempre actualizar shipping y tax desde collections.
                                    # Solo actualizar sale_fee si todavía está en cero.
                                    _sale_fee  = abs(Decimal(str(payment.get('marketplace_fee') or 0)))
                                    _ship_cost = abs(Decimal(str(payment.get('shipping_cost') or 0)))
                                    _tax_fee   = abs(Decimal(str(payment.get('taxes_amount') or 0)))
                                    logger.info(f"Payment {payment_id}: marketplace_fee={_sale_fee}, shipping_cost={_ship_cost}, taxes_amount={_tax_fee}")
                                    if _sale_fee or _ship_cost or _tax_fee:
                                        update_fields = []
                                        if _ship_cost and _ship_cost != (venta_pay.ml_shipping_cost or Decimal('0.00')):
                                            venta_pay.ml_shipping_cost = _ship_cost
                                            update_fields.append('ml_shipping_cost')
                                        if _tax_fee and _tax_fee != (venta_pay.ml_tax_fee or Decimal('0.00')):
                                            venta_pay.ml_tax_fee = _tax_fee
                                            update_fields.append('ml_tax_fee')
                                        if _sale_fee and (venta_pay.ml_sale_fee or Decimal('0.00')) == Decimal('0.00'):
                                            venta_pay.ml_sale_fee = _sale_fee
                                            update_fields.append('ml_sale_fee')
                                        if not venta_pay.ml_fecha_entrega and (_sale_fee or _ship_cost or _tax_fee):
                                            venta_pay.ml_fecha_entrega = timezone.now()
                                            update_fields.append('ml_fecha_entrega')
                                        if update_fields:
                                            venta_pay.save(update_fields=update_fields)
                                            logger.info(f"Payment {payment_id}: actualizado {update_fields} para orden {order_id_from_pay}")
                                        else:
                                            logger.info(f"Payment {payment_id}: sin cambios nuevos")
                                    else:
                                        logger.info(f"Payment {payment_id}: marketplace_fee=0, sin fees disponibles aún")
                    except Exception as pay_err:
                        logger.warning(f"Error procesando payments topic (payment {payment_id}): {pay_err}")

            # Si no es una notificación de orden, solo confirmar recepción
            return Response({
                'status': 'received',
                'message': 'Notificación recibida'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error en webhook de ML: {e}", exc_info=True)
            # Siempre retornar 200 para que ML no reenvíe la notificación
            return Response({
                'status': 'error',
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_200_OK)

    # ══════════════════════════════════════════════════════════════════════════
    # Tienda Nube — OAuth, Webhook, Configuración
    # ══════════════════════════════════════════════════════════════════════════

    def _tn_configured(self, tienda=None):
        """
        True si la app de Tienda Nube está configurada. App ID y Client Secret
        son globales (una sola app "Total Stock" registrada en el Panel de
        Partners), no algo que cada tienda cargue por su cuenta.
        """
        return bool(settings.TIENDANUBE_APP_ID and settings.TIENDANUBE_CLIENT_SECRET)

    # ── Privacy webhooks (obligatorios para el panel de Partners de TN) ────────
    # TN llama a estas URLs cuando: se desinstala la app, un cliente pide borrar datos,
    # o pide una copia de sus datos. Deben devolver 200 OK.

    @action(detail=False, methods=['post'],
            url_path='tiendanube/privacy/store-redact',
            url_name='tn-privacy-store-redact',
            permission_classes=[permissions.AllowAny])
    def tn_privacy_store_redact(self, request):
        """
        Tienda Nube llama aquí cuando una tienda desinstala la app (GDPR store
        redact). Limpiamos la conexión para que, si el comerciante vuelve a
        instalar más adelante, no quede un token viejo/inválido en el medio.
        """
        store_id = request.data.get('store_id') or request.data.get('user_id')
        logger.info("TN privacy store_redact — store_id=%s", store_id)
        if store_id:
            actualizados = Tienda.objects.filter(tn_store_id=str(store_id)).update(
                tn_access_token=None, tn_store_id=None, tn_webhook_id=None, tn_sync_habilitado=False,
            )
            if actualizados:
                logger.info("Tienda desconectada de TN por desinstalación — store_id=%s", store_id)
        return Response({'status': 'ok'}, status=200)

    @action(detail=False, methods=['post'],
            url_path='tiendanube/privacy/customers-redact',
            url_name='tn-privacy-customers-redact',
            permission_classes=[permissions.AllowAny])
    def tn_privacy_customers_redact(self, request):
        """Tienda Nube llama aquí cuando un cliente pide borrar sus datos."""
        store_id   = request.data.get('store_id') or request.data.get('user_id')
        customer   = request.data.get('customer', {})
        logger.info("TN privacy customers_redact — store_id=%s customer=%s", store_id, customer.get('id'))
        return Response({'status': 'ok'}, status=200)

    @action(detail=False, methods=['post'],
            url_path='tiendanube/privacy/customers-data-request',
            url_name='tn-privacy-customers-data-request',
            permission_classes=[permissions.AllowAny])
    def tn_privacy_customers_data_request(self, request):
        """Tienda Nube llama aquí cuando un cliente pide una copia de sus datos."""
        store_id   = request.data.get('store_id') or request.data.get('user_id')
        customer   = request.data.get('customer', {})
        logger.info("TN privacy customers_data_request — store_id=%s customer=%s", store_id, customer.get('id'))
        return Response({'status': 'ok'}, status=200)

    @action(detail=True, methods=['get'], url_path='tiendanube/status', url_name='tn-status')
    def tn_status(self, request, pk=None):
        """Estado de la integración con Tienda Nube."""
        tienda = self.get_object()
        conectado = bool(getattr(tienda, 'tn_access_token', None) and getattr(tienda, 'tn_store_id', None))
        return Response({
            'connected':         conectado,
            'app_configurada':   self._tn_configured(),
            'store_id':          getattr(tienda, 'tn_store_id', None),
            'sync_habilitado':   getattr(tienda, 'tn_sync_habilitado', False),
            'facturar_ventas':   getattr(tienda, 'tn_facturar_ventas', True),
            'webhook_id':        getattr(tienda, 'tn_webhook_id', None),
        })

    @action(detail=True, methods=['get'], url_path='tiendanube/auth-url', url_name='tn-auth-url')
    def tn_auth_url(self, request, pk=None):
        """Devuelve la URL de autorización OAuth de Tienda Nube."""
        tienda = self.get_object()
        if not self._tn_configured():
            return Response({'error': 'La app de Tienda Nube no está configurada en el servidor.'}, status=400)
        from .services.tiendanube_service import TiendaNubeService
        url = TiendaNubeService.get_authorization_url(settings.TIENDANUBE_APP_ID)
        return Response({'auth_url': url})

    @action(detail=True, methods=['post'], url_path='tiendanube/callback', url_name='tn-callback')
    def tn_callback(self, request, pk=None):
        """
        Recibe el código OAuth y lo intercambia por access_token + store_id.
        El frontend (popup) llama a este endpoint con el code recibido de TN.
        """
        tienda = self.get_object()
        if not self._tn_configured():
            return Response({'error': 'La app de Tienda Nube no está configurada en el servidor.'}, status=400)

        code = request.data.get('code')
        if not code:
            return Response({'error': 'Falta el código de autorización.'}, status=400)

        from .services.tiendanube_service import TiendaNubeService
        try:
            access_token, store_id = TiendaNubeService.exchange_code_for_token(
                settings.TIENDANUBE_APP_ID, settings.TIENDANUBE_CLIENT_SECRET, code
            )
        except Exception as e:
            logger.error("Error intercambiando código TN: %s", e)
            return Response({'error': f'Error al obtener token: {e}'}, status=400)

        tienda.tn_access_token  = access_token
        tienda.tn_store_id      = store_id
        tienda.tn_sync_habilitado = True
        tienda.save(update_fields=['tn_access_token', 'tn_store_id', 'tn_sync_habilitado'])
        logger.info("Tienda Nube conectada — tienda=%s store_id=%s", tienda.nombre, store_id)
        return Response({'success': True, 'store_id': store_id})

    @action(detail=True, methods=['post'], url_path='tiendanube/set-token', url_name='tn-set-token')
    def tn_set_token(self, request, pk=None):
        """
        Conecta la tienda usando un access_token y store_id ingresados manualmente.
        Útil cuando la app está en modo desarrollo y TN no permite OAuth con tiendas reales.
        """
        tienda = self.get_object()
        access_token = request.data.get('access_token', '').strip()
        store_id     = request.data.get('store_id', '').strip()

        if not access_token or not store_id:
            return Response({'error': 'access_token y store_id son obligatorios.'}, status=400)

        tienda.tn_access_token    = access_token
        tienda.tn_store_id        = store_id
        tienda.tn_sync_habilitado = True
        tienda.save(update_fields=['tn_access_token', 'tn_store_id', 'tn_sync_habilitado'])
        logger.info("Tienda Nube conectada manualmente — tienda=%s store_id=%s", tienda.nombre, store_id)
        return Response({'success': True, 'store_id': store_id})

    @action(detail=True, methods=['post'], url_path='tiendanube/register-webhook', url_name='tn-register-webhook')
    def tn_register_webhook(self, request, pk=None):
        """
        Registra el webhook order/paid en Tienda Nube.
        La URL del webhook es /api/tiendas/{id}/tiendanube/webhook/
        """
        tienda = self.get_object()
        if not tienda.tn_access_token:
            return Response({'error': 'La tienda no está conectada a Tienda Nube.'}, status=400)

        from .services.tiendanube_service import TiendaNubeService
        tn = TiendaNubeService(tienda)

        # Construir URL del webhook
        base = request.build_absolute_uri('/').rstrip('/')
        webhook_url = f"{base}/api/tiendas/{tienda.id}/tiendanube/webhook/"

        try:
            # Si ya hay un webhook registrado, borrarlo primero
            if tienda.tn_webhook_id:
                tn.delete_webhook(tienda.tn_webhook_id)

            webhook_id = tn.register_webhook('order/paid', webhook_url)
            tienda.tn_webhook_id = webhook_id
            tienda.save(update_fields=['tn_webhook_id'])
            logger.info("Webhook TN registrado — id=%s url=%s", webhook_id, webhook_url)
            return Response({'success': True, 'webhook_id': webhook_id, 'url': webhook_url})
        except Exception as e:
            logger.error("Error registrando webhook TN: %s", e)
            return Response({'error': f'Error al registrar webhook: {e}'}, status=400)

    @action(detail=True, methods=['post'], url_path='tiendanube/disconnect', url_name='tn-disconnect')
    def tn_disconnect(self, request, pk=None):
        """Desconecta la integración con Tienda Nube."""
        tienda = self.get_object()
        if tienda.tn_access_token and tienda.tn_webhook_id:
            from .services.tiendanube_service import TiendaNubeService
            TiendaNubeService(tienda).delete_webhook(tienda.tn_webhook_id)

        tienda.tn_access_token    = None
        tienda.tn_store_id        = None
        tienda.tn_webhook_id      = None
        tienda.tn_sync_habilitado = False
        tienda.save(update_fields=['tn_access_token', 'tn_store_id', 'tn_webhook_id', 'tn_sync_habilitado'])
        return Response({'success': True})

    @action(
        detail=True, methods=['get', 'post'],
        url_path='tiendanube/webhook', url_name='tn-webhook',
        permission_classes=[permissions.AllowAny],
    )
    def tn_webhook(self, request, pk=None):
        """
        Endpoint público que recibe notificaciones de Tienda Nube.
        GET  → validación de existencia (devuelve 200).
        POST → procesa el evento order/paid.
        """
        if request.method == 'GET':
            return Response({'status': 'ok'})

        try:
            tienda = Tienda.objects.get(pk=pk)
        except Tienda.DoesNotExist:
            return Response({'error': 'Tienda no encontrada'}, status=200)

        # ── Verificar firma HMAC ──────────────────────────────────────────
        from .services.tiendanube_service import TiendaNubeService
        sig = request.META.get('HTTP_X_LINKEDSTORE_HMAC_SHA256', '')
        if settings.TIENDANUBE_CLIENT_SECRET and sig:
            raw = request.body
            if not TiendaNubeService.verify_signature(settings.TIENDANUBE_CLIENT_SECRET, raw, sig):
                logger.warning("Firma inválida en webhook TN para tienda %s", tienda.nombre)
                return Response({'error': 'Firma inválida'}, status=200)

        payload = request.data
        event    = payload.get('event', '')
        store_id = str(payload.get('store_id', ''))
        order_id = str(payload.get('id', ''))

        logger.info("Webhook TN recibido — event=%s store_id=%s order_id=%s tienda=%s",
                    event, store_id, order_id, tienda.nombre)

        if event != 'order/paid' or not order_id:
            return Response({'status': 'ignored'}, status=200)

        if not tienda.tn_sync_habilitado:
            return Response({'status': 'sync_disabled'}, status=200)

        # ── Deduplicación ─────────────────────────────────────────────────
        if Venta.objects.filter(tienda=tienda, tn_order_id=order_id).exists():
            logger.info("Orden TN %s ya procesada para tienda %s", order_id, tienda.nombre)
            return Response({'status': 'already_processed'}, status=200)

        try:
            tn = TiendaNubeService(tienda)
            order = tn.get_order(order_id)
        except Exception as e:
            logger.error("Error obteniendo orden TN %s: %s", order_id, e)
            return Response({'status': 'error', 'detail': str(e)}, status=200)

        try:
            venta = _procesar_orden_tiendanube(tienda, order, order_id)
        except Exception as e:
            logger.error("Error procesando orden TN %s: %s", order_id, e, exc_info=True)
            return Response({'status': 'error', 'detail': str(e)}, status=200)

        # ── Facturación automática ────────────────────────────────────────
        if tienda.tn_facturar_ventas:
            try:
                from .services.facturacion_service import FacturacionService
                fs = FacturacionService(tienda)
                cliente_data = _cliente_data_desde_orden_tn(order, venta)
                fs.emitir_factura(venta, cliente_data)
            except Exception as e:
                logger.warning("Error al facturar venta TN %s: %s", venta.id, e)

        # ── Notificación push ─────────────────────────────────────────────
        try:
            from .services.notificaciones_service import NotificacionesService
            NotificacionesService.enviar_notificacion_venta(venta)
        except Exception as e:
            logger.warning("Error enviando notificación push venta TN: %s", e)

        return Response({'status': 'ok', 'venta_id': str(venta.id)}, status=200)

    # ── Exportar (publicar) productos de Total Stock → Tienda Nube ───────────

    @action(detail=True, methods=['post'], url_path='tiendanube/export-products', url_name='tn-export-products')
    def tn_export_products(self, request, pk=None):
        """
        Publica en Tienda Nube los productos de Total Stock que aún no tienen
        tn_variant_id. Agrupa variantes bajo un mismo producto TN.
        Corre en background para evitar timeout en Render.

        Body opcional: { "producto_ids": ["...", ...] } — si viene, solo publica esos
        productos puntuales (más los productos padre de cualquier variante seleccionada,
        junto con el resto de las variantes pendientes de esa misma familia, ya que TN
        no permite publicar una familia de variantes de forma parcial). Sin este campo,
        se comporta como siempre: publica todos los pendientes de la tienda.
        """
        tienda = self.get_object()
        if not tienda.tn_access_token or not tienda.tn_store_id:
            return Response({'error': 'Tienda Nube no conectada.'}, status=400)

        producto_ids = request.data.get('producto_ids') or None
        if producto_ids:
            producto_ids = [str(pid) for pid in producto_ids]

        # Contar pendientes: variantes sin tn_variant_id + standalone sin tn_variant_id
        base_pendientes = Producto.objects.filter(tienda=tienda).filter(
            Q(tn_variant_id__isnull=True) | Q(tn_variant_id='')
        )
        if producto_ids:
            padre_ids = set(
                Producto.objects.filter(id__in=producto_ids).exclude(producto_padre_id__isnull=True)
                .values_list('producto_padre_id', flat=True)
            )
            ids_incluir = set(producto_ids) | padre_ids
            base_pendientes = base_pendientes.filter(Q(id__in=ids_incluir) | Q(producto_padre_id__in=padre_ids))
        total_pendientes = base_pendientes.count()

        if total_pendientes == 0:
            mensaje = ('No hay nada pendiente entre los productos seleccionados.' if producto_ids
                       else 'Todos los productos ya están publicados en Tienda Nube.')
            return Response({'mensaje': mensaje}, status=200)

        tienda_id = tienda.id

        def _exportar():
            from django.db import connection as db_conn
            from .services.tiendanube_service import TiendaNubeService
            try:
                t = Tienda.objects.get(id=tienda_id)
                tn = TiendaNubeService(t)
                pendientes = Producto.objects.filter(tienda=t).filter(
                    Q(tn_variant_id__isnull=True) | Q(tn_variant_id='')
                )
                if producto_ids:
                    padre_ids = set(
                        Producto.objects.filter(id__in=producto_ids).exclude(producto_padre_id__isnull=True)
                        .values_list('producto_padre_id', flat=True)
                    )
                    ids_incluir = set(producto_ids) | padre_ids
                    pendientes = pendientes.filter(Q(id__in=ids_incluir) | Q(producto_padre_id__in=padre_ids))
                pendientes = pendientes.select_related('producto_padre').prefetch_related('variantes')
                publicados = 0
                errores = 0

                # Procesar padres con variantes pendientes
                padres_vistos = set()
                for prod in pendientes:
                    try:
                        if prod.producto_padre_id:
                            # Es una variante — se procesa al procesar su padre
                            continue

                        variantes_pendientes = [
                            v for v in prod.variantes.all()
                            if not v.tn_variant_id
                        ]

                        if variantes_pendientes:
                            # Producto con variantes: crear un solo TN product con todas las variantes
                            variantes_data = [
                                {
                                    'precio': v.precio,
                                    'stock': v.stock,
                                    'sku': v.codigo_barras or None,
                                    'talle': v.talle or None,
                                }
                                for v in variantes_pendientes
                            ]
                            tn_product_id, tn_variants = tn.create_product_with_variants(
                                nombre=prod.nombre,
                                variantes=variantes_data,
                            )
                            for i, variante in enumerate(variantes_pendientes):
                                if i < len(tn_variants):
                                    variante.tn_product_id   = tn_product_id
                                    variante.tn_variant_id   = str(tn_variants[i]['id'])
                                    variante.tn_sincronizado = True
                                    variante.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado'])
                                    publicados += 1
                            padres_vistos.add(prod.id)
                        else:
                            # Producto standalone sin variantes
                            tn_product_id, tn_variant_id = tn.create_product(
                                nombre=prod.nombre,
                                precio=prod.precio,
                                stock=prod.stock,
                                sku=prod.codigo_barras or None,
                            )
                            prod.tn_product_id   = tn_product_id
                            prod.tn_variant_id   = tn_variant_id
                            prod.tn_sincronizado = True
                            prod.save(update_fields=['tn_product_id', 'tn_variant_id', 'tn_sincronizado'])
                            publicados += 1

                    except Exception as e:
                        logger.error("Error publicando producto %s en TN: %s", prod.nombre, e)
                        errores += 1

                logger.info("TN export finalizado — tienda=%s publicados=%s errores=%s", t.nombre, publicados, errores)
            except Exception as e:
                logger.error("Error en hilo export TN tienda=%s: %s", tienda_id, e, exc_info=True)
            finally:
                db_conn.close()

        t = threading.Thread(target=_exportar, daemon=True)
        t.start()

        return Response({
            'mensaje': f'Publicación iniciada para {total_pendientes} producto(s). '
                       'El proceso corre en segundo plano, puede tardar unos minutos. '
                       'Revisá los logs o recargá los productos para verificar.',
            'pendientes': total_pendientes,
        }, status=202)

    # ── Importar productos desde Tienda Nube ─────────────────────────────────

    @action(detail=True, methods=['post'], url_path='tiendanube/import-products', url_name='tn-import-products')
    def tn_import_products(self, request, pk=None):
        """
        Importa productos desde Tienda Nube al sistema.
        - Si ya existe un producto con el mismo tn_variant_id → lo actualiza (stock, y precio solo si se pide).
        - Si no existe → intenta matchear por SKU o nombre, y vincula (stock, y precio solo si se pide).
        - Si no hay match → crea el producto (siempre con el precio de TN, al no haber uno local que preservar).
        Body opcional: { importar_precio: bool }  — default False: los precios pueden
        diferir a propósito entre la tienda física y la online, así que por defecto
        NO se pisa el precio local de productos ya existentes, solo el stock.
        """
        tienda = self.get_object()
        if not tienda.tn_access_token or not tienda.tn_store_id:
            return Response({'error': 'Tienda Nube no conectada.'}, status=400)

        importar_precio = bool(request.data.get('importar_precio', False))

        from .services.tiendanube_service import TiendaNubeService
        tn = TiendaNubeService(tienda)

        try:
            productos_tn = tn.get_all_products()
        except Exception as e:
            logger.error("Error obteniendo productos TN: %s", e)
            return Response({'error': str(e)}, status=500)

        creados = 0
        actualizados = 0
        vinculados = 0
        errores = []

        for prod_tn in productos_tn:
            tn_product_id = str(prod_tn.get('id', ''))
            nombre_tn     = (prod_tn.get('name') or {}).get('es') or str(prod_tn.get('name', ''))
            variantes_tn  = prod_tn.get('variants', [])
            es_multivar   = len(variantes_tn) > 1

            # Para productos multi-variante, resolver/crear el producto padre
            padre = None
            if es_multivar:
                padre = Producto.objects.filter(tienda=tienda, tn_product_id=tn_product_id, producto_padre__isnull=True, tn_variant_id__isnull=True).first()
                if not padre:
                    padre = Producto.objects.filter(tienda=tienda, nombre__iexact=nombre_tn, producto_padre__isnull=True, tn_variant_id__isnull=True).first()
                if not padre:
                    precio_ref = Decimal(str(variantes_tn[0].get('price') or '0')).quantize(Decimal('0.01'))
                    padre = Producto.objects.create(
                        tienda          = tienda,
                        nombre          = nombre_tn,
                        precio          = precio_ref,
                        stock           = 0,
                        tn_product_id   = tn_product_id,
                        tn_sincronizado = True,
                    )
                    creados += 1
                elif not padre.tn_product_id:
                    padre.tn_product_id   = tn_product_id
                    padre.tn_sincronizado = True
                    padre.save(update_fields=['tn_product_id', 'tn_sincronizado'])

            for variant in variantes_tn:
                tn_variant_id = str(variant.get('id', ''))
                sku           = variant.get('sku') or ''
                precio_raw    = variant.get('price') or prod_tn.get('price') or '0'
                precio        = Decimal(str(precio_raw)).quantize(Decimal('0.01'))
                stock_tn      = variant.get('stock') if variant.get('stock') is not None else 0
                talle_val     = None
                nombre_var    = nombre_tn
                if variant.get('values'):
                    vals = ' / '.join(v.get('es', '') or str(v) for v in variant['values'] if v)
                    if vals:
                        nombre_var = f"{nombre_tn} - {vals}"
                        talle_val  = vals

                try:
                    # 1) Buscar por tn_variant_id
                    producto = Producto.objects.filter(tienda=tienda, tn_variant_id=tn_variant_id).first()

                    if producto:
                        campos_actualizados = ['stock', 'tn_product_id', 'tn_sincronizado']
                        if importar_precio:
                            producto.precio = precio
                            campos_actualizados.append('precio')
                        producto.stock           = stock_tn
                        producto.tn_product_id   = tn_product_id
                        producto.tn_sincronizado = True
                        if es_multivar and padre and not producto.producto_padre_id:
                            producto.producto_padre = padre
                            campos_actualizados.append('producto_padre')
                        producto.save(update_fields=campos_actualizados)
                        actualizados += 1
                        continue

                    # 2) Buscar por SKU / nombre
                    if sku:
                        producto = Producto.objects.filter(tienda=tienda, codigo_barras=sku).first()
                    if not producto:
                        producto = Producto.objects.filter(tienda=tienda, nombre__iexact=nombre_var).first()
                    if not producto and nombre_tn != nombre_var:
                        producto = Producto.objects.filter(tienda=tienda, nombre__iexact=nombre_tn).first()

                    if producto:
                        producto.tn_product_id   = tn_product_id
                        producto.tn_variant_id   = tn_variant_id
                        producto.tn_sincronizado = True
                        if importar_precio:
                            producto.precio = precio
                        producto.stock           = stock_tn
                        if es_multivar and padre:
                            producto.producto_padre = padre
                            if talle_val and not producto.talle:
                                producto.talle = talle_val
                        producto.save()
                        vinculados += 1
                    else:
                        # 3) Crear nuevo producto
                        Producto.objects.create(
                            tienda          = tienda,
                            nombre          = nombre_var,
                            precio          = precio,
                            stock           = stock_tn,
                            talle           = talle_val,
                            tn_product_id   = tn_product_id,
                            tn_variant_id   = tn_variant_id,
                            tn_sincronizado = True,
                            producto_padre  = padre if es_multivar else None,
                        )
                        creados += 1

                except Exception as e:
                    logger.error("Error importando variante TN %s: %s", tn_variant_id, e, exc_info=True)
                    errores.append(f"Variante {tn_variant_id}: {str(e)}")

        return Response({
            'creados':     creados,
            'vinculados':  vinculados,
            'actualizados': actualizados,
            'errores':     errores,
        }, status=200)

    # ── Sincronizar stock hacia Tienda Nube ──────────────────────────────────

    @action(detail=True, methods=['post'], url_path='tiendanube/sync-stock', url_name='tn-sync-stock')
    def tn_sync_stock(self, request, pk=None):
        """
        Empuja el stock actual de todos los productos sincronizados hacia Tienda Nube.
        """
        tienda = self.get_object()
        if not tienda.tn_access_token or not tienda.tn_store_id:
            return Response({'error': 'Tienda Nube no conectada.'}, status=400)

        from .services.tiendanube_service import TiendaNubeService
        tn = TiendaNubeService(tienda)

        productos = Producto.objects.filter(
            tienda=tienda,
            tn_sincronizado=True,
            tn_variant_id__isnull=False,
        ).exclude(tn_variant_id='')

        if not productos.exists():
            return Response({'error': 'No hay productos sincronizados con Tienda Nube.'}, status=400)

        ok = 0
        errores = []
        for prod in productos:
            try:
                tn.update_variant_stock(prod.tn_product_id, prod.tn_variant_id, prod.stock)
                ok += 1
            except Exception as e:
                # Si la variante no existe (404), intentar refrescar el ID desde TN
                is_404 = hasattr(e, 'response') and getattr(e.response, 'status_code', None) == 404
                if is_404 and prod.tn_product_id:
                    try:
                        prod_tn = tn.get_product(prod.tn_product_id)
                        variants = prod_tn.get('variants', [])
                        if variants:
                            new_vid = str(variants[0]['id'])
                            prod.tn_variant_id = new_vid
                            prod.save(update_fields=['tn_variant_id'])
                            tn.update_variant_stock(prod.tn_product_id, new_vid, prod.stock)
                            ok += 1
                            continue
                    except Exception as inner:
                        logger.error("No se pudo refrescar variante TN para %s: %s", prod.nombre, inner)
                logger.error("Error actualizando stock TN variante %s: %s", prod.tn_variant_id, e)
                errores.append(f"{prod.nombre}: {str(e)}")

        return Response({'actualizados': ok, 'errores': errores}, status=200)


def _cliente_data_desde_orden_tn(order, venta):
    """
    Arma el dict cliente_data que espera FacturacionService.emitir_factura()
    a partir de los datos de facturación de una orden de Tienda Nube.
    Sin CUIT informado por TN, se factura como Consumidor Final (comportamiento
    seguro por defecto, igual que en el resto de la app).
    """
    customer = order.get('customer') or {}
    billing_address = order.get('billing_address') or order.get('customer', {}).get('default_address') or {}
    cuit = (
        order.get('billing_document') or
        customer.get('identification') or
        ''
    )
    domicilio = ', '.join(
        p for p in [billing_address.get('address'), billing_address.get('city')] if p
    )
    return {
        'cliente_nombre': venta.cliente_nombre or 'Consumidor Final',
        'cliente_cuit': cuit,
        'cliente_domicilio': domicilio,
        'cliente_condicion_iva': 'CF',
    }


def _procesar_orden_tiendanube(tienda, order, order_id):
    """
    Crea una Venta a partir de una orden de Tienda Nube.
    Descuenta stock de cada producto encontrado.
    """
    # Método de pago
    gateway_name = order.get('gateway_name') or order.get('gateway') or 'Tienda Nube'
    metodo_pago_obj, _ = MetodoPago.objects.get_or_create(
        nombre='Tienda Nube',
        defaults={'descripcion': 'Ventas realizadas a través de Tienda Nube', 'activo': True},
    )

    # Vendedor por defecto
    user_tn, _ = User.objects.get_or_create(
        username='tiendanube',
        defaults={
            'is_staff': False,
            'is_active': True,
            'tienda': tienda,
            'first_name': 'Tienda',
            'last_name': 'Nube',
        },
    )

    total = Decimal(str(order.get('total', '0'))).quantize(Decimal('0.01'))

    venta = Venta.objects.create(
        tienda=tienda,
        usuario=user_tn,
        total=total,
        metodo_pago=gateway_name,
        origen_tiendanube=True,
        tn_order_id=order_id,
        cliente_nombre=order.get('contact_name') or order.get('billing_name') or '',
    )

    productos_orden = order.get('products', [])
    for item in productos_orden:
        sku      = item.get('sku') or ''
        nombre   = item.get('name') or 'Producto'
        cantidad = int(item.get('quantity', 1))
        precio   = Decimal(str(item.get('price', '0'))).quantize(Decimal('0.01'))

        tn_variant_id = str(item.get('variant_id', '') or '')
        producto = None
        if tn_variant_id:
            producto = Producto.objects.filter(tienda=tienda, tn_variant_id=tn_variant_id).first()
        if not producto and sku:
            producto = Producto.objects.filter(tienda=tienda, codigo=sku).first()
        if not producto:
            producto = Producto.objects.filter(tienda=tienda, nombre__iexact=nombre).first()

        if producto:
            DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=precio * cantidad,
            )
            # Descontar stock
            if producto.stock >= cantidad:
                producto.stock -= cantidad
                producto.save(update_fields=['stock'])
            else:
                logger.warning("Stock insuficiente para %s (pedido: %s, disponible: %s)",
                               producto.nombre, cantidad, producto.stock)
        else:
            logger.warning("Producto no encontrado para orden TN: sku=%s nombre=%s", sku, nombre)
            DetalleVenta.objects.create(
                venta=venta,
                producto=None,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=precio * cantidad,
            )

    logger.info("Venta TN creada — id=%s total=%s tienda=%s", venta.id, total, tienda.nombre)
    return venta


def _procesar_cancelacion_orden_ml(venta, order_id):
    """
    Revierte una venta de Mercado Libre cuya orden fue cancelada después de haber
    sido procesada: repone el stock, la marca como anulada, emite la Nota de
    Crédito fiscal si ya tenía factura, y avisa por notificación push.

    No reutiliza la acción 'anular' de VentaViewSet porque esa requiere un
    usuario autenticado (supervisor/admin) -- acá el disparador es el propio
    webhook de ML, sin request de un humano.
    """
    if venta.anulada:
        return

    usuario_ml, created = User.objects.get_or_create(
        username='mercadolibre',
        defaults={'first_name': 'Mercado Libre', 'is_staff': False, 'is_active': True},
    )
    if created:
        usuario_ml.set_unusable_password()
        usuario_ml.save()

    # Si ya tenía factura electrónica emitida, cancelarla fiscalmente antes de
    # tocar la venta. Si esto falla, se loguea pero no bloquea el resto (reponer
    # stock y anular la venta es más urgente que la parte fiscal).
    try:
        factura = getattr(venta, 'factura', None)
        if factura and factura.estado == 'EMITIDA' and factura.tienda.tipo_facturacion != 'NINGUNA':
            motivo_nc = 'Orden de Mercado Libre cancelada'
            facturacion_service = FacturacionService(factura.tienda)
            exito, datos_nc, error = facturacion_service.emitir_nota_credito(factura, factura.total, motivo_nc)

            campos_base = dict(
                factura_origen=factura, tienda=factura.tienda, punto_venta=factura.tienda.punto_venta,
                tipo_comprobante=factura.tipo_comprobante, motivo=motivo_nc,
                monto=factura.total, impuesto_iva=Decimal('0.00'),
                cliente_nombre=factura.cliente_nombre, cliente_cuit=factura.cliente_cuit,
                sistema_facturacion=factura.tienda.tipo_facturacion,
            )
            if exito:
                campos_base['punto_venta'] = datos_nc.get('punto_venta', factura.tienda.punto_venta)
                campos_base['tipo_comprobante'] = datos_nc.get('tipo_comprobante', factura.tipo_comprobante)
                campos_base['monto'] = datos_nc.get('monto', factura.total)
                campos_base['impuesto_iva'] = datos_nc.get('impuesto_iva', Decimal('0.00'))
                NotaCredito.objects.create(
                    **campos_base, numero_comprobante=datos_nc.get('numero_comprobante'),
                    estado='EMITIDA', cae=datos_nc.get('cae'),
                    fecha_vencimiento_cae=datos_nc.get('fecha_vencimiento_cae'),
                    numero_comprobante_afip=datos_nc.get('numero_comprobante_afip'),
                    respuesta_bruta=datos_nc.get('respuesta_bruta'),
                )
                logger.info(f"✅ Nota de crédito fiscal automática emitida para venta ML {venta.id} (orden {order_id} cancelada)")
            else:
                NotaCredito.objects.create(**campos_base, estado='ERROR', error_mensaje=error)
                logger.error(f"❌ No se pudo emitir NC automática para venta ML {venta.id}: {error}")
    except Exception as e:
        logger.error(f"Error al generar NC automática por cancelación ML (venta {venta.id}): {e}", exc_info=True)

    # Reponer stock de cada detalle (mismo criterio que 'anular' para ventas normales)
    for detalle in venta.detalles.all():
        if detalle.producto and not detalle.anulado_individualmente:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save(update_fields=['stock'])
            from .services.tiendanube_service import sincronizar_stock_producto
            sincronizar_stock_producto(producto)
            logger.info(f"✅ Stock repuesto por cancelación ML: {producto.nombre} (+{detalle.cantidad})")

    venta.anulada = True
    venta.save(update_fields=['anulada'])

    _registrar_accion(
        tienda=venta.tienda, usuario=usuario_ml, accion='anulacion_venta',
        detalle=f'Anulación automática (orden Mercado Libre {order_id} cancelada) · venta #{str(venta.id)[:8]} · ${venta.total}',
        objeto_id=venta.id,
    )

    try:
        from .services.notificaciones_service import NotificacionesService
        NotificacionesService.enviar_notificacion_venta_anulada_ml(venta)
    except Exception as notif_err:
        logger.warning(f"Error al enviar notificación push por cancelación ML (venta {venta.id}): {notif_err}")

    logger.info(f"✅ Venta ML {venta.id} anulada por cancelación de orden {order_id}")


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def _tiendas_gestionables(self):
        """Devuelve el queryset de Tiendas que el usuario autenticado puede gestionar."""
        user = self.request.user
        if user.is_superuser:
            return Tienda.objects.all()
        tiendas = user.tiendas_autorizadas.all()
        if user.tienda:
            tiendas = tiendas | Tienda.objects.filter(pk=user.tienda.pk)
        return tiendas

    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.all().order_by('username')
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug)
            return queryset

        # Staff con tiendas autorizadas: solo ve usuarios de las tiendas que gestiona
        tiendas_ids = list(self._tiendas_gestionables().values_list('pk', flat=True))
        if not tiendas_ids:
            return User.objects.none()

        qs = queryset.filter(tienda__pk__in=tiendas_ids)
        if tienda_slug:
            qs = qs.filter(tienda__nombre=tienda_slug)
        return qs

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        """Endpoint para cambiar la contraseña de un usuario"""
        if not request.user.is_superuser:
            return Response(
                {'error': 'No tienes permisos para cambiar contraseñas.'},
                status=status.HTTP_403_FORBIDDEN
            )

        user = self.get_object()
        serializer = ChangePasswordSerializer(data=request.data)

        if serializer.is_valid():
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'status': 'Contraseña actualizada correctamente'})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_update(self, serializer):
        """Solo superusuarios pueden modificar is_staff, is_superuser e is_supervisor."""
        if not self.request.user.is_superuser:
            serializer.save(
                is_staff=serializer.instance.is_staff,
                is_superuser=serializer.instance.is_superuser,
                is_supervisor=serializer.instance.is_supervisor,
            )
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='set-tiendas-autorizadas')
    def set_tiendas_autorizadas(self, request, pk=None):
        """
        Asigna tiendas_autorizadas a un usuario.
        Solo se pueden asignar tiendas a las que el admin autenticado tiene acceso.
        Body: {"tiendas": [id1, id2, ...]}
        """
        target_user = self.get_object()
        tienda_ids = request.data.get('tiendas', [])

        if not isinstance(tienda_ids, list):
            return Response({'error': 'Se esperaba una lista de IDs.'}, status=status.HTTP_400_BAD_REQUEST)

        tiendas_permitidas_ids = set(str(pk) for pk in self._tiendas_gestionables().values_list('pk', flat=True))
        tienda_ids_str = set(str(i) for i in tienda_ids)

        ids_invalidos = tienda_ids_str - tiendas_permitidas_ids
        if ids_invalidos:
            return Response(
                {'error': f'No tenés acceso a las tiendas: {list(ids_invalidos)}'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Intersection correcta: ids pedidos ∩ ids permitidos
        tiendas_a_asignar_ids = tienda_ids_str & tiendas_permitidas_ids

        # Preservar tiendas que ya tenía y que este admin no puede gestionar
        actuales = set(str(pk) for pk in target_user.tiendas_autorizadas.values_list('pk', flat=True))
        no_gestionables = actuales - tiendas_permitidas_ids

        target_user.tiendas_autorizadas.set(list(tiendas_a_asignar_ids | no_gestionables))

        return Response({
            'tiendas_autorizadas': list(target_user.tiendas_autorizadas.values('id', 'nombre'))
        })

class VentaPageNumberPagination(rest_framework_pagination.PageNumberPagination):
    """Paginación para Ventas: permite page_size por query param (para exportación Excel)."""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50000


class VentaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = VentaPageNumberPagination

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    # FIX DE CONEXIÓN + totales globales (sobre el queryset completo, no solo la página)
    def list(self, request, *args, **kwargs):
        close_old_connections()
        queryset = self.filter_queryset(self.get_queryset())

        # Una sola query de agregación: conteos + montos ajustados
        # - Notas de crédito → monto 0 (no son ingreso directo)
        # - Ventas Pendiente → monto 0 (aún no cobradas)
        # - Todo lo demás (incluye ventas de diferencia de cambio ya pagadas) → venta.total
        queryset_agg = queryset.annotate(
            total_efectivo=Case(
                When(metodo_pago__in=['Nota de Crédito', 'Pendiente'], then=Value(Decimal('0'))),
                default=F('total'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )

        agg = queryset_agg.aggregate(
            total_ventas=Count('id'),
            total_activas=Count('id', filter=Q(anulada=False)),
            total_anuladas=Count('id', filter=Q(anulada=True)),
            monto_total=Sum('total_efectivo'),
            monto_activas=Sum('total_efectivo', filter=Q(anulada=False)),
            monto_anuladas=Sum('total_efectivo', filter=Q(anulada=True)),
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['totales_global'] = {
                'total_ventas':   agg['total_ventas'] or 0,
                'monto_total':    str(agg['monto_total'] or 0),
                'total_activas':  agg['total_activas'] or 0,
                'monto_activas':  str(agg['monto_activas'] or 0),
                'total_anuladas': agg['total_anuladas'] or 0,
                'monto_anuladas': str(agg['monto_anuladas'] or 0),
            }
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        user = self.request.user
        # Optimización: usar select_related para evitar consultas N+1
        # Nota: metodo_pago es CharField, no ForeignKey, por lo que no se puede usar en select_related
        queryset = Venta.objects.select_related(
            'tienda', 'usuario', 'arancel_aplicado', 'factura'
        ).prefetch_related(
            'detalles__producto',
            'nota_credito_origen__detalles__detalle_venta_original__producto',
            'cambio_devolucion_diferencia',
        ).order_by('-fecha_venta')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        # Para usuarios no-superuser: ven ventas de su tienda principal + todas las tiendas autorizadas
        if not user.is_superuser:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if not tiendas_ids:
                return Venta.objects.none()
            # Usuarios staff (no supervisor): solo pueden buscar por ID, no listar todas las ventas
            if user.is_staff and not user.is_supervisor:
                venta_id = self.request.query_params.get('id', None)
                if not venta_id:
                    return Venta.objects.none()
            queryset = queryset.filter(tienda__pk__in=tiendas_ids)
        elif tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)

        fecha_venta_date = self.request.query_params.get('fecha_venta__date', None)
        fecha_desde = self.request.query_params.get('fecha_desde', None)
        fecha_hasta = self.request.query_params.get('fecha_hasta', None)
        if fecha_desde or fecha_hasta:
            if fecha_desde:
                queryset = queryset.filter(fecha_venta__date__gte=fecha_desde)
            if fecha_hasta:
                queryset = queryset.filter(fecha_venta__date__lte=fecha_hasta)
        elif fecha_venta_date:
            queryset = queryset.filter(fecha_venta__date=fecha_venta_date)

        hora_desde = self.request.query_params.get('hora_desde', None)
        hora_hasta = self.request.query_params.get('hora_hasta', None)
        if hora_desde:
            queryset = queryset.filter(fecha_venta__time__gte=hora_desde)
        if hora_hasta:
            queryset = queryset.filter(fecha_venta__time__lte=hora_hasta)

        usuario = self.request.query_params.get('usuario', None)
        if usuario:
            queryset = queryset.filter(usuario=usuario)

        anulada = self.request.query_params.get('anulada', None)
        if anulada is not None:
            queryset = queryset.filter(anulada=anulada == 'true')

        # Buscar por ID de venta (puede venir con o sin guiones desde el código de barras)
        # También puede venir como código EAN13 (13 dígitos) que debemos convertir de vuelta al UUID
        venta_id = self.request.query_params.get('id', None)
        if venta_id:
            # Si es un código EAN13 (13 dígitos numéricos), buscar por los primeros caracteres del UUID
            # El código EAN13 se genera a partir de los primeros 12 caracteres hex del UUID
            # Conversión: a-f -> 0-5, 0-9 -> 0-9
            if len(venta_id) == 13 and venta_id.isdigit():
                # El código EAN13 tiene un dígito de control, así que usamos los primeros 12
                codigo_base = venta_id[:12]
                # Extraer el hash (los últimos 9 dígitos después del prefijo 779)
                if codigo_base.startswith('779'):
                    hash_9_digitos = codigo_base[3:]
                    # Buscar todas las ventas y verificar cuál genera este hash
                    # Como no podemos hacer búsqueda inversa fácil, iteramos sobre las ventas
                    ventas_match = []
                    for venta in queryset:
                        # Calcular el hash de esta venta (mismo algoritmo que en el frontend)
                        # Frontend usa: hash = (hash * 31 + char) % 1000000000
                        venta_id_str = str(venta.id).replace('-', '')
                        hash_calculado = 0
                        for char in venta_id_str:
                            hash_calculado = (hash_calculado * 31 + ord(char)) % 1000000000
                        hash_absoluto = abs(hash_calculado)
                        hash_str = str(hash_absoluto).zfill(9)[:9]  # zfill es como padStart en Python
                        if hash_str == hash_9_digitos:
                            ventas_match.append(venta.id)
                    
                    if ventas_match:
                        queryset = queryset.filter(id__in=ventas_match)
                    else:
                        queryset = queryset.none()
            else:
                # Si el ID viene sin guiones (del código de barras), intentar agregarlos en las posiciones correctas
                # Formato UUID: 8-4-4-4-12 caracteres
                cleaned_id = venta_id.replace('-', '')
                if len(cleaned_id) == 32:  # UUID sin guiones tiene 32 caracteres
                    # Formatear como UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                    formatted_id = f"{cleaned_id[:8]}-{cleaned_id[8:12]}-{cleaned_id[12:16]}-{cleaned_id[16:20]}-{cleaned_id[20:]}"
                    try:
                        import uuid
                        # Validar que es un UUID válido
                        uuid.UUID(formatted_id)
                        queryset = queryset.filter(id=formatted_id)
                    except (ValueError, TypeError):
                        # Si no es un UUID válido, buscar por los primeros caracteres (para búsqueda parcial)
                        if len(cleaned_id) >= 8:
                            # Buscar ventas cuyo UUID empiece con estos caracteres
                            from django.db.models import Q
                            queryset = queryset.filter(Q(id__startswith=cleaned_id[:8]))
                elif len(cleaned_id) >= 8:
                    # Buscar por los primeros caracteres del UUID (viene del código de barras CODE128)
                    from django.db.models import Q
                    # Buscar ventas cuyo UUID (sin guiones) empiece con estos caracteres
                    queryset = queryset.filter(Q(id__startswith=cleaned_id[:8]) | Q(id__icontains=cleaned_id[:8]))
            
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """Sobrescribir retrieve para permitir acceso a ventas de nota de crédito relacionadas con cambios/devoluciones"""
        pk = kwargs.get('pk')
        user = request.user
        
        # Intentar obtener directamente por ID primero (sin filtros de queryset)
        try:
            instance = Venta.objects.select_related(
                'tienda', 'usuario', 'arancel_aplicado', 'factura'
            ).prefetch_related(
                'detalles__producto',
                'nota_credito_origen__detalles__detalle_venta_original__producto',
                'cambio_devolucion_diferencia',
            ).get(pk=pk)
        except Venta.DoesNotExist:
            return Response(
                {'detail': 'No encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error al obtener venta en retrieve: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Error al obtener la venta.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Verificar permisos básicos
        if not user.is_superuser:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if instance.tienda_id not in tiendas_ids:
                # Si es una nota de crédito o diferencia pendiente relacionada con cambio/devolución, permitir acceso
                if instance.metodo_pago in ['Nota de Crédito', 'Pendiente'] and CambioDevolucion is not None:
                    try:
                        cambio_nota_credito = instance.nota_credito_origen.first()
                        cambio_diferencia = instance.cambio_devolucion_diferencia.first()
                    except:
                        cambio_nota_credito = None
                        cambio_diferencia = None
                    
                    # Si está relacionada con cambio/devolución, permitir acceso aunque sea de otra tienda
                    # (esto es necesario porque el cambio puede haberse procesado desde otra tienda)
                    if cambio_nota_credito or cambio_diferencia:
                        serializer = self.get_serializer(instance)
                        return Response(serializer.data)
                
                # Si no es nota de crédito relacionada o no tiene permisos, negar acceso
                return Response(
                    {'detail': 'No encontrado.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Para otras ventas o usuarios con permisos, usar el comportamiento estándar
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        if not request.user.is_superuser and not request.user.is_supervisor:
            return Response(
                {"error": "No tienes permiso para anular ventas."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar si esta venta está relacionada con un cambio/devolución
        cambio_devolucion_afectado = None
        if CambioDevolucion is not None:
            try:
                # Verificar si es una nota de crédito
                cambio_nota_credito = venta.nota_credito_origen.first()
                if cambio_nota_credito:
                    cambio_devolucion_afectado = cambio_nota_credito
                    logger.info(f"⚠️ Anulando nota de crédito del cambio/devolución {cambio_nota_credito.id}")
                
                # Verificar si es una venta de diferencia pendiente
                if not cambio_devolucion_afectado:
                    cambio_diferencia = venta.cambio_devolucion_diferencia.first()
                    if cambio_diferencia:
                        cambio_devolucion_afectado = cambio_diferencia
                        logger.info(f"⚠️ Anulando venta de diferencia del cambio/devolución {cambio_diferencia.id}")
            except Exception as e:
                logger.warning(f"⚠️ Error al verificar cambio/devolución relacionado: {e}")
        
        # Anular la venta
        venta.anulada = True
        venta.save()

        # Si está relacionada con un cambio/devolución, revertir todos los cambios
        if cambio_devolucion_afectado:
            try:
                # Revertir el cambio/devolución completo:
                # 1. Restaurar stock de productos devueltos (que se habían restado del stock)
                # 2. Restar stock de productos nuevos que se habían agregado
                # 3. Restaurar los detalles de venta original que fueron marcados como anulados
                # 4. Marcar el cambio/devolución como cancelado
                
                for detalle_cambio in cambio_devolucion_afectado.detalles.all():
                    if detalle_cambio.accion == 'DEVOLVER':
                        # _perform_create_inner sumó stock al devolver (+cantidad).
                        # Para revertir, restamos ese stock nuevamente.
                        if detalle_cambio.detalle_venta_original:
                            detalle_venta = detalle_cambio.detalle_venta_original
                            if detalle_venta.producto:
                                producto = detalle_venta.producto
                                producto.stock -= detalle_cambio.cantidad
                                if producto.stock < 0:
                                    producto.stock = 0
                                producto.save()
                                from .services.tiendanube_service import sincronizar_stock_producto
                                sincronizar_stock_producto(producto)
                                logger.info(f"✅ Stock revertido para producto devuelto: {producto.nombre} (-{detalle_cambio.cantidad})")

                            if detalle_venta.anulado_individualmente:
                                detalle_venta.anulado_individualmente = False
                                detalle_venta.save(update_fields=['anulado_individualmente'])
                                logger.info(f"✅ Detalle de venta original restaurado: {detalle_venta.id}")

                    elif detalle_cambio.accion == 'CAMBIAR':
                        # _perform_create_inner: sumó stock al producto devuelto (+) y restó al nuevo (-).
                        # Para revertir: restamos del devuelto y sumamos al nuevo.
                        if detalle_cambio.detalle_venta_original:
                            detalle_venta = detalle_cambio.detalle_venta_original
                            if detalle_venta.producto:
                                producto_devuelto = detalle_venta.producto
                                producto_devuelto.stock -= detalle_cambio.cantidad
                                if producto_devuelto.stock < 0:
                                    producto_devuelto.stock = 0
                                producto_devuelto.save()
                                from .services.tiendanube_service import sincronizar_stock_producto
                                sincronizar_stock_producto(producto_devuelto)
                                logger.info(f"✅ Stock revertido para producto devuelto en cambio: {producto_devuelto.nombre} (-{detalle_cambio.cantidad})")

                            if detalle_venta.anulado_individualmente:
                                detalle_venta.anulado_individualmente = False
                                detalle_venta.save(update_fields=['anulado_individualmente'])
                                logger.info(f"✅ Detalle de venta original restaurado en cambio: {detalle_venta.id}")

                        if detalle_cambio.producto_nuevo:
                            producto_nuevo = detalle_cambio.producto_nuevo
                            producto_nuevo.stock += detalle_cambio.cantidad
                            producto_nuevo.save()
                            from .services.tiendanube_service import sincronizar_stock_producto
                            sincronizar_stock_producto(producto_nuevo)
                            logger.info(f"✅ Stock revertido para producto nuevo en cambio: {producto_nuevo.nombre} (+{detalle_cambio.cantidad})")
                    
                    elif detalle_cambio.accion == 'AGREGAR':
                        # Cuando se agregó un producto nuevo, se había restado del stock
                        # Al anular, debemos volver a agregarlo al stock
                        if detalle_cambio.producto_nuevo:
                            producto = detalle_cambio.producto_nuevo
                            producto.stock += detalle_cambio.cantidad
                            producto.save()
                            from .services.tiendanube_service import sincronizar_stock_producto
                            sincronizar_stock_producto(producto)
                            logger.info(f"✅ Stock restaurado para producto agregado: {producto.nombre} (+{detalle_cambio.cantidad})")
                
                # Recalcular el total de la venta original respetando descuentos/recargos originales
                venta_original = cambio_devolucion_afectado.venta_original
                subtotal_activos = sum(
                    d.subtotal for d in venta_original.detalles.all()
                    if not d.anulado_individualmente
                )
                desc_monto = venta_original.descuento_monto or Decimal('0.00')
                desc_pct   = venta_original.descuento_porcentaje or Decimal('0.00')
                rec_monto  = venta_original.recargo_monto or Decimal('0.00')
                rec_pct    = venta_original.recargo_porcentaje or Decimal('0.00')
                if desc_monto > 0:
                    total_recalculado = max(Decimal('0.00'), subtotal_activos - desc_monto)
                elif desc_pct > 0:
                    total_recalculado = subtotal_activos * (Decimal('1') - desc_pct / Decimal('100'))
                elif rec_monto > 0:
                    total_recalculado = subtotal_activos + rec_monto
                elif rec_pct > 0:
                    total_recalculado = subtotal_activos * (Decimal('1') + rec_pct / Decimal('100'))
                else:
                    total_recalculado = subtotal_activos
                venta_original.total = total_recalculado
                venta_original.save()
                logger.info(f"✅ Total de venta original recalculado: ${total_recalculado}")
                
                # Marcar el cambio/devolución como cancelado
                cambio_devolucion_afectado.estado = 'CANCELADO'
                cambio_devolucion_afectado.save()
                logger.info(f"✅ Cambio/devolución {cambio_devolucion_afectado.id} marcado como CANCELADO")
                
            except Exception as e:
                logger.error(f"❌ Error al revertir cambio/devolución: {e}", exc_info=True)
        else:
            # Para ventas normales, solo restaurar el stock de los productos de esta venta
            detalles = DetalleVenta.objects.filter(venta=venta)
            for detalle in detalles:
                if detalle.producto and not detalle.anulado_individualmente:
                    producto = detalle.producto
                    producto.stock += detalle.cantidad
                    producto.save()
                    from .services.tiendanube_service import sincronizar_stock_producto
                    sincronizar_stock_producto(producto)
                    logger.info(f"✅ Stock restaurado para venta normal: {producto.nombre} (+{detalle.cantidad})")

            # Cuenta Corriente: revertir la deuda pendiente de esta venta. venta.total ya
            # refleja lo que quedó tras eventuales anulaciones parciales previas (anular_detalle),
            # así que este crédito siempre cancela exactamente el saldo restante.
            if venta.metodo_pago == 'Cuenta Corriente' and venta.cliente_id and venta.total > 0:
                MovimientoCuentaCorriente.objects.create(
                    cliente=venta.cliente,
                    tienda=venta.tienda,
                    venta=venta,
                    usuario=request.user,
                    tipo='CREDITO',
                    monto=venta.total,
                    concepto=f'Anulación venta {venta.id}',
                )

        if cambio_devolucion_afectado:
            _registrar_accion(
                tienda=venta.tienda,
                usuario=request.user,
                accion='anulacion_cambio_devolucion',
                detalle=(
                    f'Anulación cambio/devolución #{str(cambio_devolucion_afectado.id)[:8]} '
                    f'· venta original #{str(cambio_devolucion_afectado.venta_original_id)[:8]}'
                ),
                objeto_id=cambio_devolucion_afectado.id,
            )
        else:
            _registrar_accion(
                tienda=venta.tienda,
                usuario=request.user,
                accion='anulacion_venta',
                detalle=f'Anulación venta #{str(venta.id)[:8]} · ${venta.total} · {venta.metodo_pago or ""}',
                objeto_id=venta.id,
            )
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        if not request.user.is_superuser and not request.user.is_supervisor:
            return Response(
                {"error": "No tienes permiso para anular detalles de venta."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        detalle_id = request.data.get('detalle_id')
        if not detalle_id:
            return Response({"error": "Se requiere el ID del detalle de venta."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            detalle = DetalleVenta.objects.get(id=detalle_id, venta__id=pk)
        except DetalleVenta.DoesNotExist:
            return Response({"error": "Detalle de venta no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser and not request.user.is_supervisor:
            return Response({"error": "No tienes permiso para anular este detalle de venta."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "No se puede anular un detalle de una venta que ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            from .services.tiendanube_service import sincronizar_stock_producto
            sincronizar_stock_producto(producto)
            detalle.anulado_individualmente = True
            detalle.save()
            
            venta = detalle.venta
            total_antes_anulacion = venta.total
            total_subtotal = sum(d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente)
            
            # --- LÓGICA DE RECALCULO DE TOTAL CON DESCUENTO/RECARGO ---
            if venta.recargo_monto > 0:
                venta.total = total_subtotal + venta.recargo_monto
            elif venta.recargo_porcentaje > 0:
                venta.total = total_subtotal * (Decimal('1') + (venta.recargo_porcentaje / Decimal('100')))
            elif venta.descuento_monto > 0:
                venta.total = max(Decimal('0.00'), total_subtotal - venta.descuento_monto)
            elif venta.descuento_porcentaje > 0:
                venta.total = total_subtotal * (Decimal('1') - (venta.descuento_porcentaje / Decimal('100')))
            else:
                venta.total = total_subtotal
            # ---------------------------------------------------------

            # Recalcular arancel sobre el nuevo total si aplica
            if venta.arancel_aplicado:
                arancel_porcentaje = venta.arancel_aplicado.arancel_porcentaje
                venta.arancel_total = venta.total * (arancel_porcentaje / Decimal('100'))
            else:
                venta.arancel_total = Decimal('0.00') # Asegurar que es 0.00
            
            if not venta.detalles.filter(anulado_individualmente=False).exists():
                venta.anulada = True

            venta.save()

            # Cuenta Corriente: revertir en el libro solo la parte del ítem anulado (la
            # diferencia entre el total anterior y el recalculado), sin tocar el resto de la deuda.
            if venta.metodo_pago == 'Cuenta Corriente' and venta.cliente_id:
                delta = total_antes_anulacion - venta.total
                if delta > 0:
                    MovimientoCuentaCorriente.objects.create(
                        cliente=venta.cliente,
                        tienda=venta.tienda,
                        venta=venta,
                        usuario=request.user,
                        tipo='CREDITO',
                        monto=delta,
                        concepto=f'Anulación ítem venta {venta.id}',
                    )

            nombre_prod = detalle.producto.nombre if detalle.producto else 'producto eliminado'
            talle_str = f' T:{detalle.producto.talle}' if detalle.producto and detalle.producto.talle else ''
            _registrar_accion(
                tienda=venta.tienda,
                usuario=request.user,
                accion='anulacion_item',
                detalle=f'Anulación ítem: {nombre_prod}{talle_str} x{detalle.cantidad} · ${detalle.subtotal} · Venta #{str(venta.id)[:8]}',
                objeto_id=venta.id,
            )
            return Response({"status": "Detalle de venta anulado con éxito y stock restaurado."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()

            venta = detalle.venta
            if not venta.detalles.filter(anulado_individualmente=False).exists():
                venta.anulada = True
                venta.save()

            nombre_prod = detalle.producto.nombre if detalle.producto else 'producto eliminado'
            talle_str = f' T:{detalle.producto.talle}' if detalle.producto and detalle.producto.talle else ''
            _registrar_accion(
                tienda=venta.tienda,
                usuario=request.user,
                accion='anulacion_item',
                detalle=f'Anulación ítem: {nombre_prod}{talle_str} x{detalle.cantidad} · ${detalle.subtotal} · Venta #{str(venta.id)[:8]}',
                objeto_id=venta.id,
            )
            return Response({"status": "Detalle de venta anulado con éxito, sin stock que restaurar."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def emitir_factura(self, request, pk=None):
        """Emitir una factura electrónica para una venta"""
        venta = get_object_or_404(Venta, pk=pk)
        
        # Validaciones
        if venta.anulada:
            return Response(
                {"error": "No se puede emitir factura para una venta anulada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if venta.facturada:
            return Response(
                {"error": "Esta venta ya tiene una factura emitida."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar que la tienda tenga facturación configurada
        if venta.tienda.tipo_facturacion == 'NINGUNA':
            return Response(
                {"error": "La tienda no tiene configurado un sistema de facturación."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar permisos
        user = request.user
        if not user.is_superuser and venta.tienda_id not in _get_tiendas_ids_usuario(user):
            return Response(
                {"error": "No tienes permiso para emitir facturas de esta tienda."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar datos del cliente
        serializer = EmitirFacturaSerializer(data=request.data)
        if not serializer.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Error de validación en emitir_factura: {serializer.errors}")
            logger.error(f"Datos recibidos: {request.data}")
            return Response(
                {"error": "Error de validación", "detalles": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cliente_data = serializer.validated_data
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"=== Iniciando emisión de factura ===")
            logger.info(f"Venta ID: {venta.id}")
            logger.info(f"Tienda: {venta.tienda.nombre}")
            logger.info(f"Tipo facturación: {venta.tienda.tipo_facturacion}")
            logger.info(f"Datos del cliente: {cliente_data}")
            
            # Inicializar servicio de facturación
            facturacion_service = FacturacionService(venta.tienda)
            
            # Emitir factura
            logger.info(f"⚠️ Llamando a facturacion_service.emitir_factura...")
            exito, datos_factura, error = facturacion_service.emitir_factura(venta, cliente_data)
            logger.info(f"Resultado: exito={exito}, error={error}")
            
            if not exito:
                # Crear registro de factura con error
                factura = Factura.objects.create(
                    venta=venta,
                    tienda=venta.tienda,
                    punto_venta=venta.tienda.punto_venta,
                    tipo_comprobante='B',  # Por defecto Factura B
                    cliente_nombre=cliente_data.get('cliente_nombre', 'Consumidor Final'),
                    cliente_cuit=cliente_data.get('cliente_cuit', ''),
                    cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                    cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                    cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                    subtotal=venta.total,
                    impuesto_iva=Decimal('0.00'),
                    total=venta.total,
                    estado='ERROR',
                    sistema_facturacion=venta.tienda.tipo_facturacion,
                    error_mensaje=error,
                )
                
                return Response(
                    {
                        "error": error,
                        "factura_id": str(factura.id),
                        "estado": "ERROR"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Crear registro de factura exitosa
            factura = Factura.objects.create(
                venta=venta,
                tienda=venta.tienda,
                numero_comprobante=datos_factura.get('numero_comprobante'),
                punto_venta=datos_factura.get('punto_venta', venta.tienda.punto_venta),
                tipo_comprobante=datos_factura.get('tipo_comprobante', 'B'),
                cliente_nombre=cliente_data.get('cliente_nombre', 'Consumidor Final'),
                cliente_cuit=cliente_data.get('cliente_cuit', ''),
                cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                subtotal=datos_factura.get('subtotal', venta.total),
                impuesto_iva=datos_factura.get('impuesto_iva', Decimal('0.00')),
                total=datos_factura.get('total', venta.total),
                estado='EMITIDA',
                sistema_facturacion=venta.tienda.tipo_facturacion,
                cae=datos_factura.get('cae'),
                fecha_vencimiento_cae=datos_factura.get('fecha_vencimiento_cae'),
                numero_comprobante_afip=datos_factura.get('numero_comprobante_afip'),
                respuesta_bruta=datos_factura.get('respuesta_bruta'),
            )
            
            # Marcar venta como facturada y actualizar datos del cliente
            venta.facturada = True
            venta.cliente_nombre = cliente_data.get('cliente_nombre', '')
            venta.cliente_cuit = cliente_data.get('cliente_cuit', '')
            venta.cliente_domicilio = cliente_data.get('cliente_domicilio', '')
            venta.cliente_tipo_documento = cliente_data.get('cliente_tipo_documento', '')
            venta.save()
            
            # Serializar y retornar factura
            factura_serializer = FacturaSerializer(factura)
            
            return Response(
                {
                    "message": "Factura emitida exitosamente",
                    "factura": factura_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Excepción no capturada en emitir_factura: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": f"Error al emitir factura: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def ticket_cambio(self, request, pk=None):
        """
        Genera y retorna el PDF del ticket de cambio para una venta
        """
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        if not BARCODE_AVAILABLE:
            return Response(
                {"error": "python-barcode no está instalado. Instala con: pip install python-barcode"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        venta = get_object_or_404(Venta, pk=pk)
        
        # Verificar permisos
        user = request.user
        if not user.is_superuser and venta.tienda_id not in _get_tiendas_ids_usuario(user):
            return Response(
                {"error": "No tienes permiso para ver este ticket de cambio"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener nombre de la tienda
        nombre_tienda = venta.tienda.nombre if venta.tienda else 'N/A'
        
        # Crear buffer para el PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=(80*mm, 120*mm), topMargin=10*mm, bottomMargin=10*mm, leftMargin=5*mm, rightMargin=5*mm)
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=8,
            alignment=1  # Centrado
        )
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#000000'),
            spaceAfter=6,
            alignment=1  # Centrado
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.textColor = colors.HexColor('#000000')
        
        # Contenido del PDF
        story = []
        
        # Nombre de la tienda
        story.append(Paragraph(f"<b>{nombre_tienda}</b>", title_style))
        story.append(Spacer(1, 8))
        
        # Leyenda "Ticket para cambio"
        story.append(Paragraph("<b>TICKET PARA CAMBIO</b>", subtitle_style))
        story.append(Spacer(1, 12))
        
        # Fecha de compra
        fecha_str = venta.fecha_venta.strftime('%d/%m/%Y %H:%M')
        story.append(Paragraph(f"<b>Fecha de compra:</b> {fecha_str}", normal_style))
        story.append(Spacer(1, 12))
        
        # Generar código de barras
        try:
            # Crear código de barras Code128 con el ID de la venta
            venta_id_str = str(venta.id).replace('-', '')  # Remover guiones del UUID
            # Limitar a los primeros 40 caracteres (límite razonable para código de barras)
            venta_id_str = venta_id_str[:40]
            
            code128 = barcode.get_barcode_class('code128')
            barcode_instance = code128(venta_id_str, writer=ImageWriter())
            
            # Generar imagen del código de barras en memoria
            barcode_buffer = BytesIO()
            barcode_instance.write(barcode_buffer, options={
                'module_width': 0.3,
                'module_height': 15,
                'quiet_zone': 2,
                'font_size': 8,
                'text_distance': 3
            })
            barcode_buffer.seek(0)
            
            # Crear imagen de ReportLab desde el buffer
            barcode_image = Image(barcode_buffer, width=60*mm, height=15*mm)
            story.append(barcode_image)
            story.append(Spacer(1, 6))
            
            # ID de la venta debajo del código de barras
            story.append(Paragraph(f"<b>ID: {str(venta.id)}</b>", ParagraphStyle(
                'BarcodeText',
                parent=normal_style,
                fontSize=8,
                alignment=1  # Centrado
            )))
            
        except Exception as e:
            logger.error(f"Error al generar código de barras: {e}")
            # Si falla el código de barras, mostrar solo el ID
            story.append(Paragraph(f"<b>ID de Venta:</b> {str(venta.id)}", normal_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        
        # Crear respuesta HTTP con el PDF
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ticket_cambio_{venta.id}.pdf"'
        return response


class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        tiendas_ids = _get_tiendas_ids_usuario(user)
        if tiendas_ids:
            return DetalleVenta.objects.filter(venta__tienda__pk__in=tiendas_ids)
        return DetalleVenta.objects.none()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Retorna todos los métodos de pago activos.
        Mercado Libre siempre se muestra para permitir ventas manuales con aranceles por producto.
        """
        return MetodoPago.objects.filter(activo=True).order_by('nombre')

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


# CAMBIO CRUCIAL: NUEVO VIEWSET para aranceles
class ArancelMetodoTiendaViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        """Permitir lectura a usuarios staff, pero solo superusuarios pueden crear/editar/eliminar"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ArancelMetodoTiendaCreateSerializer
        return ArancelMetodoTiendaSerializer

    def get_queryset(self):
        user = self.request.user
        # Uso select_related para optimizar la consulta de tienda y método de pago
        queryset = ArancelMetodoTienda.objects.all().select_related('tienda', 'metodo_pago')
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        # Superusuarios pueden ver todos los aranceles
        if user.is_superuser:
            if tienda_slug:
                result = queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
                logger.info(f"✅ Superuser - Aranceles para tienda '{tienda_slug}': {result.count()} aranceles")
                return result
            result = queryset.order_by('tienda__nombre', 'metodo_pago__nombre', 'nombre_plan')
            logger.info(f"✅ Superuser - Todos los aranceles: {result.count()} aranceles")
            return result
        
        # Supervisores: ven aranceles de su tienda principal + tiendas autorizadas
        elif user.is_supervisor:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if tienda_slug:
                if Tienda.objects.filter(nombre=tienda_slug, pk__in=tiendas_ids).exists():
                    return queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
                return ArancelMetodoTienda.objects.none()
            return queryset.filter(tienda__pk__in=tiendas_ids).order_by('metodo_pago__nombre', 'nombre_plan')

        # Usuarios staff: pueden ver aranceles de su tienda principal + tiendas autorizadas
        elif user.is_staff:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if not tiendas_ids:
                logger.warning(f"⚠️ Staff '{user.username}' sin tiendas asignadas.")
                return ArancelMetodoTienda.objects.none()
            if tienda_slug:
                if Tienda.objects.filter(nombre=tienda_slug, pk__in=tiendas_ids).exists():
                    result = queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
                    logger.info(f"✅ Staff '{user.username}' - Aranceles para tienda '{tienda_slug}': {result.count()}")
                    return result
                logger.warning(f"⚠️ Staff '{user.username}' - Tienda '{tienda_slug}' no autorizada.")
                return ArancelMetodoTienda.objects.none()
            result = queryset.filter(tienda__pk__in=tiendas_ids).order_by('metodo_pago__nombre', 'nombre_plan')
            logger.info(f"✅ Staff '{user.username}' - Aranceles de todas sus tiendas: {result.count()}")
            return result

        # Si no es superuser ni staff, no puede ver aranceles
        logger.warning(f"⚠️ User '{user.username}' - Sin permisos para ver aranceles.")
        return ArancelMetodoTienda.objects.none()

    def perform_create(self, serializer):
        """Al crear, usar la tienda del slug"""
        tienda_slug = self.request.data.get('tienda')
        if tienda_slug:
            try:
                tienda = Tienda.objects.get(nombre=tienda_slug)
                serializer.save(tienda=tienda)
            except Tienda.DoesNotExist:
                from rest_framework import serializers as drf_serializers
                raise drf_serializers.ValidationError({'tienda': 'Tienda no encontrada'})
        else:
            serializer.save()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


class CompraViewSet(viewsets.ModelViewSet):
    serializer_class = CompraSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Compra.objects.all()
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                queryset = queryset.filter(tienda__nombre=tienda_slug)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            return Compra.objects.none()

        # Filtro por rango de fechas
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        if date_from:
            queryset = queryset.filter(fecha_compra__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(fecha_compra__date__lte=date_to)

        # Búsqueda por concepto (proveedor)
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(proveedor__icontains=search)

        return queryset.order_by('-fecha_compra')

    def get_serializer_class(self):
        if self.action == 'create':
            return CompraCreateSerializer
        return CompraSerializer
    
    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


class CompraStockViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'create':
            return CompraStockCreateSerializer
        return CompraStockSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = CompraStock.objects.all()
        tienda_slug = self.request.query_params.get('tienda_slug')

        if user.is_superuser:
            if tienda_slug:
                queryset = queryset.filter(tienda__nombre=tienda_slug)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            return CompraStock.objects.none()

        # Filtros opcionales por fecha
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(fecha_compra__gte=date_from)
        if date_to:
            queryset = queryset.filter(fecha_compra__lte=date_to)

        return queryset

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


class HistorialAccionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import HistorialAccionSerializer
        return HistorialAccionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_superuser:
            return HistorialAccion.objects.none()
        qs = HistorialAccion.objects.select_related('usuario').filter(tienda=user.tienda)
        fecha_desde = self.request.query_params.get('fecha_desde')
        fecha_hasta = self.request.query_params.get('fecha_hasta')
        usuario_id  = self.request.query_params.get('usuario_id')
        if fecha_desde:
            qs = qs.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__date__lte=fecha_hasta)
        if usuario_id:
            qs = qs.filter(usuario__id=usuario_id)
        return qs


# VIEWSET: Aranceles Mercado Libre por Producto (arancel % + costo envío por producto)
# Reemplaza la configuración por categoría
if ArancelMercadoLibreProducto is not None and ArancelMercadoLibreProductoSerializer is not None:
    class ArancelMercadoLibreProductoViewSet(viewsets.ModelViewSet):
        permission_classes = [permissions.IsAuthenticated]
        
        def get_serializer_class(self):
            if self.action in ['create', 'update', 'partial_update']:
                return ArancelMercadoLibreProductoCreateSerializer
            return ArancelMercadoLibreProductoSerializer
        
        def get_queryset(self):
            user = self.request.user
            queryset = ArancelMercadoLibreProducto.objects.all().select_related('tienda', 'producto')
            
            if user.is_superuser:
                tienda_slug = self.request.query_params.get('tienda_slug', None)
                if tienda_slug:
                    queryset = queryset.filter(tienda__nombre=tienda_slug)
                return queryset.order_by('tienda__nombre', 'producto__nombre')
            
            elif user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
                return queryset.order_by('producto__nombre')
            
            return ArancelMercadoLibreProducto.objects.none()
        
        def perform_create(self, serializer):
            user = self.request.user
            if not user.is_superuser and user.tienda:
                serializer.save(tienda=user.tienda)
            else:
                serializer.save()
        
        def list(self, request, *args, **kwargs):
            close_old_connections()
            return super().list(request, *args, **kwargs)
else:
    ArancelMercadoLibreProductoViewSet = None

# VIEWSET: Aranceles Mercado Libre por Categoría (legacy - se mantiene por compatibilidad)
if ArancelMercadoLibre is not None and ArancelMercadoLibreSerializer is not None:
    class ArancelMercadoLibreViewSet(viewsets.ModelViewSet):
        permission_classes = [permissions.IsAuthenticated]
        
        def get_serializer_class(self):
            if self.action in ['create', 'update', 'partial_update']:
                return ArancelMercadoLibreCreateSerializer
            return ArancelMercadoLibreSerializer
        
        def get_queryset(self):
            if ArancelMercadoLibre is None:
                from rest_framework.exceptions import NotFound
                raise NotFound("ArancelMercadoLibre no está disponible.")
            
            user = self.request.user
            queryset = ArancelMercadoLibre.objects.all().select_related('tienda', 'categoria_ml')
            
            if user.is_superuser:
                tienda_slug = self.request.query_params.get('tienda_slug', None)
                if tienda_slug:
                    queryset = queryset.filter(tienda__nombre=tienda_slug)
                return queryset.order_by('tienda__nombre', 'categoria_ml__nombre')
            
            elif user.tienda:
                from .models import Producto
                categorias_usadas = Producto.objects.filter(
                    tienda=user.tienda,
                    ml_categoria_id__isnull=False
                ).exclude(ml_categoria_id='').values_list('ml_categoria_id', flat=True).distinct()
                queryset = queryset.filter(
                    tienda=user.tienda,
                    categoria_ml__id__in=categorias_usadas
                )
                return queryset.order_by('categoria_ml__nombre')
            
            return ArancelMercadoLibre.objects.none()
        
        def perform_create(self, serializer):
            user = self.request.user
            if not user.is_superuser and user.tienda:
                serializer.save(tienda=user.tienda)
            else:
                serializer.save()
        
        def list(self, request, *args, **kwargs):
            close_old_connections()
            return super().list(request, *args, **kwargs)
else:
    ArancelMercadoLibreViewSet = None
        

class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

# --- ENDPOINT PARA NOTIFICACIONES PUSH (FCM) ---
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def registrar_token_fcm(request):
    """
    Endpoint para registrar un token FCM de un dispositivo.
    Se usa para recibir notificaciones push cuando se realizan ventas.
    """
    from .services.notificaciones_service import NotificacionesService
    
    token = request.data.get('token')
    device_info = request.data.get('device_info', None)
    
    if not token:
        return Response(
            {'error': 'El token FCM es requerido'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        fcm_token, created = NotificacionesService.registrar_token(
            user=request.user,
            token=token,
            device_info=device_info
        )
        
        return Response({
            'success': True,
            'message': 'Token registrado correctamente' if created else 'Token actualizado correctamente',
            'token_id': str(fcm_token.id)
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error al registrar token FCM: {str(e)}")
        return Response(
            {'error': f'Error al registrar token: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['DELETE', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def eliminar_token_fcm(request):
    """
    Endpoint para eliminar/desactivar un token FCM.
    Útil cuando el usuario cierra sesión o desactiva notificaciones.
    """
    from .services.notificaciones_service import NotificacionesService
    
    token = request.data.get('token')
    
    if not token:
        return Response(
            {'error': 'El token FCM es requerido'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        success = NotificacionesService.eliminar_token(token)
        
        if success:
            return Response({
                'success': True,
                'message': 'Token eliminado correctamente'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Token no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.error(f"Error al eliminar token FCM: {str(e)}")
        return Response(
            {'error': f'Error al eliminar token: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- NUEVA VISTA PARA MÉTRICAS DE INVENTARIO ---
class InventarioMetricsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Los "padre" que solo agrupan variantes (producto_padre_id=None pero con
        # variantes.exists()) no son un producto vendible en sí -- mismo criterio que
        # ya usa la exportación a Excel. Si un producto ya existente se agrupó como
        # padre vía "Agrupar variantes" (a diferencia de crearlo directamente con
        # variantes, que sí pone stock=0 al padre), conserva su stock/costo previos
        # a la agrupación; sumarlos junto con los de sus variantes duplicaría la
        # cantidad y el valor real del stock.
        padres_con_variantes = Producto.objects.filter(
            tienda=tienda_obj, producto_padre__isnull=True, variantes__isnull=False
        ).distinct()
        productos_qs = Producto.objects.filter(tienda=tienda_obj).exclude(pk__in=padres_con_variantes)

        # Métrica de stock total (cantidad)
        total_stock = productos_qs.aggregate(total_stock=Sum('stock'))['total_stock'] or 0

        # Métrica de monto total del stock (precio de venta)
        monto_total_stock_precio = productos_qs.aggregate(
            total_monto_stock=Sum(F('stock') * Coalesce('precio', Value(0), output_field=DecimalField()))
        )['total_monto_stock'] or Decimal('0.00')

        # Métrica de monto total del stock (costo)
        monto_total_stock_costo = productos_qs.aggregate(
            total_monto_stock_costo=Sum(F('stock') * Coalesce('costo', Value(0), output_field=DecimalField()))
        )['total_monto_stock_costo'] or Decimal('0.00')

        data = {
            'total_stock': total_stock,
            'total_monto_stock_precio': monto_total_stock_precio,
            'total_monto_stock_costo': monto_total_stock_costo,
        }

        return Response(data)

# --- VISTA PARA VERIFICAR CONFIGURACIÓN DE BASE DE DATOS ---
@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # Permitir acceso sin autenticación para diagnóstico
def verificar_database_config(request):
    """
    Endpoint para verificar qué base de datos está usando el sistema.
    Útil para diagnosticar si está usando la BD en la nube o la local.
    """
    from django.conf import settings
    from django.db import connection
    import os
    
    db_config = settings.DATABASES['default']
    environment = os.environ.get('DJANGO_ENVIRONMENT', 'development').lower()
    
    # Información de la base de datos (sin credenciales sensibles)
    db_info = {
        'environment': environment,
        'engine': db_config.get('ENGINE', 'N/A'),
        'database_name': db_config.get('NAME', 'N/A'),
        'host': db_config.get('HOST', 'N/A'),
        'port': db_config.get('PORT', 'N/A'),
        'user': db_config.get('USER', 'N/A'),
        'has_database_url': 'DATABASE_URL' in os.environ,
        'is_sqlite': 'sqlite3' in db_config.get('ENGINE', ''),
        'is_postgresql': 'postgresql' in db_config.get('ENGINE', ''),
    }
    
    # Intentar hacer una consulta simple para verificar la conexión
    try:
        with connection.cursor() as cursor:
            if db_info['is_postgresql']:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                db_info['database_version'] = version
                db_info['connection_status'] = '✅ Conectado a PostgreSQL'
                
                # Contar usuarios para verificar que está usando la BD correcta
                cursor.execute("SELECT COUNT(*) FROM inventario_user;")
                user_count = cursor.fetchone()[0]
                db_info['user_count'] = user_count
                
                # Obtener lista de usernames (solo los primeros 10)
                cursor.execute("SELECT username FROM inventario_user ORDER BY username LIMIT 10;")
                usernames = [row[0] for row in cursor.fetchall()]
                db_info['sample_usernames'] = usernames
                
            elif db_info['is_sqlite']:
                cursor.execute("SELECT sqlite_version();")
                version = cursor.fetchone()[0]
                db_info['database_version'] = version
                db_info['connection_status'] = '⚠️ Usando SQLite (local)'
                
                # Contar usuarios
                cursor.execute("SELECT COUNT(*) FROM inventario_user;")
                user_count = cursor.fetchone()[0]
                db_info['user_count'] = user_count
                
                # Obtener lista de usernames
                cursor.execute("SELECT username FROM inventario_user ORDER BY username LIMIT 10;")
                usernames = [row[0] for row in cursor.fetchall()]
                db_info['sample_usernames'] = usernames
            else:
                db_info['connection_status'] = '❓ Tipo de base de datos desconocido'
                
    except Exception as e:
        db_info['connection_status'] = f'❌ Error de conexión: {str(e)}'
        db_info['error'] = str(e)
    
    # Advertencia si está en producción pero usando SQLite
    if environment == 'production' and db_info['is_sqlite']:
        db_info['warning'] = '⚠️ ADVERTENCIA: Estás en PRODUCCIÓN pero usando SQLite local. Debes usar PostgreSQL en la nube.'
    
    return Response(db_info, status=status.HTTP_200_OK)

# --- VISTA PARA MÉTRICAS DE VENTAS (ACTUALIZADA) ---
class MetricasAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        year = request.query_params.get('year', None)
        month = request.query_params.get('month', None)
        day = request.query_params.get('day', None)
        date_from = request.query_params.get('date_from', None)
        date_to = request.query_params.get('date_to', None)
        seller_id = request.query_params.get('seller_id', None)
        payment_method = request.query_params.get('payment_method', None)

        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        
        # Filtramos las ventas para excluir las anuladas, notas de crédito y ventas pendientes
        queryset_ventas = Venta.objects.filter(tienda=tienda_obj, anulada=False).exclude(
            metodo_pago__in=['Nota de Crédito', 'Pendiente']
        )
        queryset_compras = Compra.objects.filter(tienda=tienda_obj)

        use_date_range = date_from and date_to
        if use_date_range:
            try:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                if dt_from > dt_to:
                    return Response({"error": "'date_from' debe ser anterior o igual a 'date_to'."}, status=status.HTTP_400_BAD_REQUEST)
                queryset_ventas = queryset_ventas.filter(
                    fecha_venta__date__gte=dt_from,
                    fecha_venta__date__lte=dt_to
                )
                queryset_compras = queryset_compras.filter(
                    fecha_compra__date__gte=dt_from,
                    fecha_compra__date__lte=dt_to
                )
            except ValueError:
                return Response({"error": "Formato de fecha inválido. Use YYYY-MM-DD para date_from y date_to."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if year:
                queryset_ventas = queryset_ventas.filter(fecha_venta__year=year)
                queryset_compras = queryset_compras.filter(fecha_compra__year=year)
            if month:
                queryset_ventas = queryset_ventas.filter(fecha_venta__month=month)
                queryset_compras = queryset_compras.filter(fecha_compra__month=month)
            if day:
                queryset_ventas = queryset_ventas.filter(fecha_venta__day=day)
                queryset_compras = queryset_compras.filter(fecha_compra__day=day)
        if seller_id:
            queryset_ventas = queryset_ventas.filter(usuario__id=seller_id)
        if payment_method:
            queryset_ventas = queryset_ventas.filter(metodo_pago=payment_method)

        # Calcular el total de ventas, pero para ventas que vienen de cambios/devoluciones,
        # usar solo la diferencia en lugar del total completo
        # Las ventas relacionadas con cambios/devoluciones tienen diferencia_pendiente=True
        # y necesitamos usar el monto_diferencia del cambio/devolución relacionado
        
        # Optimización: obtener todas las ventas con relaciones optimizadas
        # Usar select_related para ForeignKeys y prefetch_related para relaciones reversas
        # Nota: metodo_pago es CharField, no ForeignKey, por lo que no se puede usar en select_related
        if CambioDevolucion is not None:
            ventas_list = list(queryset_ventas.select_related(
                'tienda', 'usuario', 'arancel_aplicado'
            ).prefetch_related(
                'cambio_devolucion_diferencia',
                'nota_credito_origen'
            ))
        else:
            ventas_list = list(queryset_ventas.select_related(
                'tienda', 'usuario', 'arancel_aplicado'
            ))
        
        # Optimización: crear diccionarios para acceso rápido a relaciones
        cambio_diferencia_map = {}
        nota_credito_map = {}
        if CambioDevolucion is not None:
            # Pre-cargar todas las relaciones en una sola consulta
            for venta in ventas_list:
                # Acceder a las relaciones prefetch para cachearlas
                cambio_dif = list(venta.cambio_devolucion_diferencia.all())
                if cambio_dif:
                    cambio_diferencia_map[venta.id] = cambio_dif[0]
                
                nota_cred = list(venta.nota_credito_origen.all())
                if nota_cred:
                    nota_credito_map[venta.id] = nota_cred[0]
        
        total_ventas_periodo = Decimal('0.00')
        
        # Iterar una sola vez procesando todo
        for venta in ventas_list:
            # Excluir notas de crédito primero (más rápido)
            if venta.id in nota_credito_map:
                continue
            
            # Para todas las ventas (incluyendo diferencias de cambio/devolución),
            # usar venta.total que el serializer ya calcula aplicando descuentos/recargos.
            total_ventas_periodo += venta.total
        
        # Filtramos los detalles de venta para excluir los anulados individualmente
        # Pero para ventas que vienen de cambios/devoluciones, solo contamos los productos nuevos
        # Optimización: usar select_related para evitar consultas N+1 con producto
        detalles_activos = DetalleVenta.objects.filter(
            venta__in=queryset_ventas, 
            anulado_individualmente=False
        ).select_related('producto', 'venta')
        total_productos_vendidos_periodo = detalles_activos.aggregate(total_productos_vendidos=Sum('cantidad'))['total_productos_vendidos'] or 0
        
        # Calcular costo vendido: para ventas normales usar todos los detalles,
        # para ventas de diferencia solo contar productos nuevos (ya están en los detalles de la venta)
        total_costo_vendido = detalles_activos.aggregate(total_costo_vendido=Sum(F('cantidad') * Coalesce('costo_unitario', Value(0), output_field=DecimalField())))['total_costo_vendido'] or Decimal('0.00')
        
        # Ajustar costo vendido si hay ventas que vienen de cambios/devoluciones
        # (en este caso, los productos ya están correctamente en los detalles, así que no hay que ajustar)

        total_compras_periodo = queryset_compras.aggregate(total_egresos=Sum('total'))['total_egresos'] or Decimal('0.00')

        # CAMBIO 10: NUEVO CÁLCULO: Arancel Total de Ventas con Comisión
        # Calcular arancel considerando solo la diferencia para ventas de cambio/devolución
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        total_arancel_ventas = Decimal('0.00')
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            if venta.id in cambio_diferencia_map:
                cambio_diferencia = cambio_diferencia_map[venta.id]
                if cambio_diferencia.monto_diferencia > 0:
                    # Para ventas de diferencia, calcular arancel solo sobre la diferencia
                    # (el arancel ya debería estar calculado sobre el total de la venta, pero lo ajustamos proporcionalmente)
                    if venta.arancel_total and venta.total > 0:
                        factor_proporcion = cambio_diferencia.monto_diferencia / venta.total
                        total_arancel_ventas += venta.arancel_total * factor_proporcion
                    else:
                        total_arancel_ventas += venta.arancel_total or Decimal('0.00')
                else:
                    total_arancel_ventas += venta.arancel_total or Decimal('0.00')
            else:
                total_arancel_ventas += venta.arancel_total or Decimal('0.00')

        # Costo de envío ML: descontar de métricas (webhook + ventas manuales con pago ML)
        total_costo_envio_ml = sum(
            (v.costo_envio_ml or Decimal('0.00'))
            for v in ventas_list
            if v.id not in nota_credito_map and (v.costo_envio_ml or Decimal('0.00')) > Decimal('0.00')
        )

        # Descuentos ML reales: cargo por venta + costo fijo + cuotas + envío real (del webhook)
        _ml_ventas = [v for v in ventas_list if v.id not in nota_credito_map and v.origen_mercadolibre]
        total_ml_sale_fee      = sum(v.ml_sale_fee      or Decimal('0.00') for v in _ml_ventas)
        total_ml_fixed_fee     = sum(v.ml_fixed_fee     or Decimal('0.00') for v in _ml_ventas)
        total_ml_financing_fee = sum(v.ml_financing_fee or Decimal('0.00') for v in _ml_ventas)
        total_ml_shipping_cost = sum(v.ml_shipping_cost or Decimal('0.00') for v in _ml_ventas)
        total_ml_descuentos = total_ml_sale_fee + total_ml_fixed_fee + total_ml_financing_fee + total_ml_shipping_cost

        # Impuestos ML reales (de fee_details del webhook)
        total_ml_impuestos = sum(
            (v.ml_tax_fee or Decimal('0.00'))
            for v in ventas_list
            if v.id not in nota_credito_map and v.origen_mercadolibre
        )

        # Flag: la tienda tiene Mercado Libre integrado
        tienda_tiene_ml = bool(getattr(tienda_obj, 'ml_access_token', None) and getattr(tienda_obj, 'ml_sync_habilitado', False))

        # % ventas ML ya cobradas: ML acredita 6 días después de la fecha de entrega
        ml_pct_cobradas = None
        if tienda_tiene_ml:
            total_ml = sum(1 for v in ventas_list if v.id not in nota_credito_map and v.origen_mercadolibre)
            umbral_cobro = timezone.now() - timedelta(days=6)
            ml_cobradas = sum(
                1 for v in ventas_list
                if v.id not in nota_credito_map
                and v.origen_mercadolibre
                and v.ml_fecha_entrega
                and v.ml_fecha_entrega <= umbral_cobro
            )
            ml_pct_cobradas = round((ml_cobradas / total_ml * 100), 1) if total_ml > 0 else 0

        # La rentabilidad resta costo productos, egresos, aranceles, costo envío ML, descuentos ML e impuestos ML
        rentabilidad_bruta = total_ventas_periodo - total_costo_vendido - total_compras_periodo - total_arancel_ventas - total_costo_envio_ml - total_ml_descuentos - total_ml_impuestos
        margen_rentabilidad = (rentabilidad_bruta / total_ventas_periodo * 100) if total_ventas_periodo > 0 else 0

        # Filtrar detalles que tienen producto (excluir notas de crédito y detalles sin producto)
        # cantidad_pagados_ml: unidades vendidas por ML cuyo pago ya fue acreditado (ml_sale_fee > 0)
        productos_mas_vendidos = detalles_activos.filter(producto__isnull=False).values(
            'producto__nombre', 'producto__talle'
        ).annotate(
            cantidad_total=Sum('cantidad'),
            monto_total=Sum('subtotal'),
            cantidad_pagados_ml=Sum(
                Case(
                    When(venta__origen_mercadolibre=True, venta__ml_sale_fee__gt=0, then=F('cantidad')),
                    default=Value(0),
                    output_field=DecimalField()
                )
            )
        ).order_by('-cantidad_total')
        
        # Para ventas por usuario, también aplicar la lógica de diferencia
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        ventas_por_usuario_dict = {}
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            username = venta.usuario.username if venta.usuario else 'Sin usuario'
            
            monto_venta = venta.total

            if username not in ventas_por_usuario_dict:
                ventas_por_usuario_dict[username] = {'total_vendido': Decimal('0.00'), 'cantidad_ventas': 0}
            ventas_por_usuario_dict[username]['total_vendido'] += monto_venta
            ventas_por_usuario_dict[username]['cantidad_ventas'] += 1
        
        ventas_por_usuario = [
            {'usuario__username': username, 'total_vendido': float(data['total_vendido']), 'cantidad_ventas': data['cantidad_ventas']}
            for username, data in ventas_por_usuario_dict.items()
        ]
        ventas_por_usuario.sort(key=lambda x: x['total_vendido'], reverse=True)
        
        # Para ventas por método de pago, también aplicar la lógica de diferencia
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        ventas_por_metodo_pago_dict = {}
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            metodo_pago = venta.metodo_pago or 'Sin método'
            
            monto_venta = venta.total

            if metodo_pago not in ventas_por_metodo_pago_dict:
                ventas_por_metodo_pago_dict[metodo_pago] = Decimal('0.00')
            ventas_por_metodo_pago_dict[metodo_pago] += monto_venta
        
        ventas_por_metodo_pago = [
            {'metodo_pago': metodo, 'total_vendido': float(monto)}
            for metodo, monto in ventas_por_metodo_pago_dict.items()
        ]
        ventas_por_metodo_pago.sort(key=lambda x: x['total_vendido'], reverse=True)

        egresos_por_mes = queryset_compras.annotate(
            year=ExtractYear('fecha_compra'),
            mes=ExtractMonth('fecha_compra')
        ).values('year', 'mes').annotate(
            total_egresos=Sum('total')
        ).order_by('year', 'mes')

        data = {
            'total_ventas_periodo': total_ventas_periodo,
            'total_productos_vendidos_periodo': total_productos_vendidos_periodo,
            'total_costo_vendido_periodo': total_costo_vendido,
            'total_compras_periodo': total_compras_periodo,
            'total_arancel_ventas': total_arancel_ventas,
            'total_costo_envio_ml': total_costo_envio_ml,
            'total_ml_descuentos': total_ml_descuentos,
            'total_ml_sale_fee': total_ml_sale_fee,
            'total_ml_fixed_fee': total_ml_fixed_fee,
            'total_ml_financing_fee': total_ml_financing_fee,
            'total_ml_shipping_cost': total_ml_shipping_cost,
            'total_ml_impuestos': total_ml_impuestos,
            'tienda_tiene_ml': tienda_tiene_ml,
            'ml_aranceles_automaticos': getattr(tienda_obj, 'ml_aranceles_automaticos', True),
            'ml_pct_cobradas': ml_pct_cobradas,
            'rentabilidad_bruta_periodo': rentabilidad_bruta,
            'margen_rentabilidad_periodo': margen_rentabilidad,
            'productos_mas_vendidos': list(productos_mas_vendidos),
            'ventas_por_usuario': list(ventas_por_usuario),
            'ventas_por_metodo_pago': list(ventas_por_metodo_pago),
            'egresos_por_mes': list(egresos_por_mes),
        }

        return Response(data)


class WidgetVentasHoyAPIView(APIView):
    """
    Datos de ventas del día para el widget de iPhone (Scriptable). Se autentica
    con un token de solo lectura por tienda (Tienda.widget_token), no con el
    login normal, para que el widget siga funcionando sin depender de un JWT
    que expira y se pueda revocar sin afectar la cuenta.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        token = request.query_params.get('token')
        if not token:
            return Response({'error': "Falta el parámetro 'token'."}, status=status.HTTP_400_BAD_REQUEST)

        tienda = Tienda.objects.filter(widget_token=token).first()
        if not tienda:
            return Response({'error': 'Token inválido.'}, status=status.HTTP_404_NOT_FOUND)

        hoy = timezone.localdate()
        ventas_qs = Venta.objects.filter(
            tienda=tienda, anulada=False, fecha_venta__date=hoy
        ).exclude(metodo_pago__in=['Nota de Crédito', 'Pendiente'])

        if CambioDevolucion is not None:
            ventas_list = list(ventas_qs.prefetch_related('cambio_devolucion_diferencia', 'nota_credito_origen'))
        else:
            ventas_list = list(ventas_qs)

        total = Decimal('0.00')
        cantidad_ventas = 0
        ventas_incluidas_ids = []
        for venta in ventas_list:
            if CambioDevolucion is not None and list(venta.nota_credito_origen.all()):
                continue
            monto = venta.total
            if CambioDevolucion is not None:
                dif = list(venta.cambio_devolucion_diferencia.all())
                if dif:
                    monto = dif[0].monto_diferencia
            total += monto or Decimal('0.00')
            cantidad_ventas += 1
            ventas_incluidas_ids.append(venta.id)

        unidades_vendidas = DetalleVenta.objects.filter(
            venta_id__in=ventas_incluidas_ids, anulado_individualmente=False
        ).aggregate(total=Sum('cantidad'))['total'] or 0

        ticket_promedio = (total / cantidad_ventas) if cantidad_ventas > 0 else Decimal('0.00')

        return Response({
            'tienda_nombre': tienda.nombre,
            'tienda_logo': tienda.logo,
            'total_ventas_hoy': str(total),
            'cantidad_ventas': cantidad_ventas,
            'unidades_vendidas': unidades_vendidas,
            'ticket_promedio': str(ticket_promedio),
            'actualizado': timezone.now().isoformat(),
        })


class FacturaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar facturas emitidas"""
    serializer_class = FacturaSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_comprobante', 'cliente_nombre', 'cliente_cuit', 'cae']
    ordering_fields = ['fecha_emision', 'numero_comprobante', 'total']
    ordering = ['-fecha_emision']

    def get_queryset(self):
        user = self.request.user

        queryset = Factura.objects.select_related('venta', 'tienda').all()

        if user.is_superuser:
            tienda_id = self.request.query_params.get('tienda', None)
            if tienda_id:
                queryset = queryset.filter(tienda_id=tienda_id)
            else:
                tienda_nombre = self.request.query_params.get('tienda_nombre')
                if tienda_nombre:
                    queryset = queryset.filter(tienda__nombre=tienda_nombre)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            return Factura.objects.none()

        estado = self.request.query_params.get('estado', None)
        if estado:
            queryset = queryset.filter(estado=estado)

        tipo_comprobante = self.request.query_params.get('tipo_comprobante', None)
        if tipo_comprobante:
            queryset = queryset.filter(tipo_comprobante=tipo_comprobante)

        venta_id = self.request.query_params.get('venta', None)
        if venta_id:
            queryset = queryset.filter(venta_id=venta_id)

        fecha_desde = self.request.query_params.get('fecha_desde', None)
        if fecha_desde:
            queryset = queryset.filter(fecha_emision__date__gte=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta', None)
        if fecha_hasta:
            queryset = queryset.filter(fecha_emision__date__lte=fecha_hasta)

        venta_anulada = self.request.query_params.get('venta_anulada', None)
        if venta_anulada is not None:
            queryset = queryset.filter(venta__anulada=venta_anulada.lower() == 'true')

        return queryset
    
    @action(detail=True, methods=['get'], url_path='pdf', url_name='pdf')
    def generar_pdf(self, request, pk=None):
        """
        Genera y retorna el PDF de la factura
        """
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        factura = self.get_object()
        
        # Verificar permisos
        user = request.user
        if not user.is_superuser and user.tienda != factura.tienda:
            return Response(
                {"error": "No tienes permiso para ver esta factura"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Asegurar que la relación tienda esté cargada correctamente
        # Recargar desde la base de datos si es necesario
        try:
            factura.refresh_from_db()
            # Forzar la carga de la relación tienda
            tienda_obj = factura.tienda
            if tienda_obj:
                tienda_obj.refresh_from_db()
        except Exception as e:
            logger.warning(f"⚠️ Error al recargar factura o tienda: {e}")
        
        # Obtener detalles de la venta
        venta = factura.venta
        detalles = venta.detalles.all()
        
        # Obtener el nombre de la tienda con fallback
        nombre_tienda = 'N/A'
        try:
            # Intentar obtener desde la relación
            if factura.tienda_id:
                # Recargar tienda desde DB
                from inventario.models import Tienda
                tienda_obj = Tienda.objects.get(id=factura.tienda_id)
                nombre_tienda = tienda_obj.nombre or 'N/A'
                logger.info(f"✅ Nombre de tienda obtenido desde DB: {nombre_tienda}")
            elif factura.tienda:
                nombre_tienda = factura.tienda.nombre or 'N/A'
                logger.info(f"✅ Nombre de tienda obtenido desde relación: {nombre_tienda}")
            else:
                logger.warning(f"⚠️ La factura {factura.id} no tiene tienda asignada")
        except Exception as e:
            logger.warning(f"⚠️ Error al obtener nombre de tienda: {e}")
            import traceback
            logger.warning(traceback.format_exc())
        
        logger.info(f"📄 Generando PDF para factura {factura.id}, tienda: '{nombre_tienda}'")
        
        # Crear buffer para el PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12,
            alignment=1  # Centrado
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.textColor = colors.HexColor('#000000')
        
        # Contenido del PDF
        story = []
        
        # Título - Usar nombre de la tienda (ya obtenido arriba)
        # Manejar tanto tipo_comprobante como letra (A, B, C) como número (1, 6, 11)
        tipo_comprobante_para_texto = factura.tipo_comprobante
        if isinstance(tipo_comprobante_para_texto, (int, str)) and str(tipo_comprobante_para_texto) in ['1', '6', '11']:
            # Convertir número a letra
            tipo_map = {'1': 'A', '6': 'B', '11': 'C'}
            tipo_comprobante_para_texto = tipo_map.get(str(tipo_comprobante_para_texto), 'B')
        
        tipo_factura_text = dict(Factura.TIPO_FACTURA_CHOICES).get(tipo_comprobante_para_texto, tipo_comprobante_para_texto)
        story.append(Paragraph(f"<b>{nombre_tienda}</b>", title_style))
        story.append(Paragraph(f"FACTURA {tipo_factura_text}", ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=8,
            alignment=1  # Centrado
        )))
        story.append(Spacer(1, 12))
        
        # Datos de la tienda
        if factura.tienda.cuit:
            story.append(Paragraph(f"<b>CUIT:</b> {factura.tienda.cuit}", normal_style))
        if factura.tienda.direccion:
            story.append(Paragraph(f"<b>Domicilio:</b> {factura.tienda.direccion}", normal_style))
        story.append(Spacer(1, 12))
        
        # Datos de la factura (mover punto de venta y número más abajo, no justo después del nombre)
        # Primero mostrar fecha
        story.append(Paragraph(f"<b>Fecha de Emisión:</b> {factura.fecha_emision.strftime('%d/%m/%Y %H:%M')}", normal_style))
        # Generar código numérico de 13 dígitos desde el UUID de la venta (mismo que lee el código de barras)
        venta_id_sin_guiones = str(venta.id).replace('-', '')
        hash_num = 0
        for char in venta_id_sin_guiones:
            hash_num = (hash_num * 31 + ord(char)) % 1000000000
        hash_9_digitos = str(abs(hash_num)).zfill(9)[:9]
        codigo_base = '779' + hash_9_digitos
        # Calcular dígito de control para EAN13
        suma = sum(int(codigo_base[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
        checksum = (10 - (suma % 10)) % 10
        codigo_numerico = codigo_base + str(checksum)
        # Mostrar código numérico de 13 dígitos debajo de la fecha (mismo que lee el código de barras)
        story.append(Paragraph(f"<b>ID de Venta:</b> {codigo_numerico}", normal_style))
        # Mostrar punto de venta y número juntos en una línea más abajo
        story.append(Paragraph(f"<b>Comprobante:</b> {factura.punto_venta:04d}-{factura.numero_comprobante:08d}", normal_style))
        if factura.cae:
            story.append(Paragraph(f"<b>CAE:</b> {factura.cae}", normal_style))
        if factura.fecha_vencimiento_cae:
            story.append(Paragraph(f"<b>CAE Vto:</b> {factura.fecha_vencimiento_cae.strftime('%d/%m/%Y')}", normal_style))
        if venta.metodo_pago == 'Cuenta Corriente' and venta.fecha_limite_pago:
            story.append(Paragraph(f"<b>Fecha límite de pago:</b> {venta.fecha_limite_pago.strftime('%d/%m/%Y')}", normal_style))
        story.append(Spacer(1, 12))

        # Datos del cliente
        story.append(Paragraph("<b>DATOS DEL CLIENTE</b>", normal_style))
        story.append(Paragraph(f"<b>Nombre:</b> {factura.cliente_nombre}", normal_style))
        if factura.cliente_cuit:
            story.append(Paragraph(f"<b>CUIT/DNI:</b> {factura.cliente_cuit}", normal_style))
        if factura.cliente_domicilio:
            story.append(Paragraph(f"<b>Domicilio:</b> {factura.cliente_domicilio}", normal_style))
        condicion_iva_text = dict(Factura.CONDICION_IVA_CHOICES).get(factura.cliente_condicion_iva, factura.cliente_condicion_iva)
        story.append(Paragraph(f"<b>Condición IVA:</b> {condicion_iva_text}", normal_style))
        story.append(Spacer(1, 12))
        
        # IMPORTANTE: Los precios de los productos ya tienen IVA incluido (21%)
        # Necesitamos calcular el subtotal SIN IVA
        # Si precio_con_iva = precio_sin_iva * 1.21, entonces precio_sin_iva = precio_con_iva / 1.21
        
        # Tabla de productos
        data = [['Cant.', 'Descripción', 'Precio Unit.', 'Subtotal']]
        subtotal_sin_iva = Decimal('0.00')
        total_iva_calculado = Decimal('0.00')
        
        for detalle in detalles:
            if not detalle.anulado_individualmente:
                producto_nombre = detalle.producto.nombre if detalle.producto else 'Producto eliminado'
                # El precio_unitario ya tiene IVA incluido
                precio_con_iva = Decimal(str(detalle.precio_unitario))
                # Calcular precio sin IVA: precio_con_iva / 1.21
                precio_sin_iva = precio_con_iva / Decimal('1.21')
                # Calcular subtotal sin IVA
                subtotal_item_sin_iva = precio_sin_iva * Decimal(str(detalle.cantidad))
                # Calcular IVA del item
                iva_item = subtotal_item_sin_iva * Decimal('0.21')
                
                subtotal_sin_iva += subtotal_item_sin_iva
                total_iva_calculado += iva_item
                
                # Mostrar precio con IVA (el precio original del producto)
                data.append([
                    str(detalle.cantidad),
                    producto_nombre,
                    f"${precio_con_iva:.2f}",
                    f"${detalle.subtotal:.2f}"
                ])
        
        # IMPORTANTE: El total de la venta YA tiene descuentos/recargos aplicados
        # No debemos recalcular descuentos/recargos aquí, solo mostrar los valores correctos
        # El total de la venta ya incluye IVA y descuentos/recargos aplicados sobre el total con IVA
        
        # Calcular el subtotal y IVA a partir del total final (que ya tiene descuentos aplicados)
        total_final = Decimal(str(venta.total))
        subtotal_final_sin_iva = (total_final / Decimal('1.21')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        iva_final = (total_final - subtotal_final_sin_iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Calcular el descuento/recargo que se aplicó (para mostrarlo en el PDF)
        # El descuento/recargo se aplicó sobre el total CON IVA
        subtotal_inicial_con_iva = sum(
            Decimal(str(d.precio_unitario)) * Decimal(str(d.cantidad))
            for d in detalles if not d.anulado_individualmente
        )
        
        descuento_monto_calc = Decimal('0.00')
        recargo_monto_calc = Decimal('0.00')
        
        # Calcular descuento aplicado (sobre el total con IVA)
        if venta.descuento_porcentaje and venta.descuento_porcentaje > 0:
            descuento_porc = venta.descuento_porcentaje / Decimal('100')
            descuento_monto_calc = subtotal_inicial_con_iva * descuento_porc
        elif venta.descuento_monto and venta.descuento_monto > 0:
            descuento_monto_calc = venta.descuento_monto
        
        # Calcular recargo aplicado (sobre el total con IVA después del descuento)
        if venta.recargo_porcentaje and venta.recargo_porcentaje > 0:
            recargo_base = subtotal_inicial_con_iva - descuento_monto_calc
            recargo_porc = venta.recargo_porcentaje / Decimal('100')
            recargo_monto_calc = recargo_base * recargo_porc
        elif venta.recargo_monto and venta.recargo_monto > 0:
            recargo_monto_calc = venta.recargo_monto
        
        # Agregar línea separadora antes de totales
        data.append(['', '', '', ''])  # Línea vacía
        
        # Subtotal inicial con IVA (antes de descuentos/recargos)
        subtotal_inicial_con_iva = sum(
            Decimal(str(d.precio_unitario)) * Decimal(str(d.cantidad))
            for d in detalles if not d.anulado_individualmente
        )
        data.append(['', '', '<b>Subtotal:</b>', f"${subtotal_inicial_con_iva:.2f}"])
        
        # Descuentos (mostrar sobre el total con IVA)
        if descuento_monto_calc > 0:
            descuento_label = f'<b>Descuento'
            if venta.descuento_porcentaje and venta.descuento_porcentaje > 0:
                descuento_label += f' ({venta.descuento_porcentaje}%)'
            descuento_label += ':</b>'
            data.append(['', '', descuento_label, f"-${descuento_monto_calc:.2f}"])
        
        # Recargos (mostrar sobre el total con IVA)
        if recargo_monto_calc > 0:
            recargo_label = '<b>Recargo'
            if venta.recargo_porcentaje and venta.recargo_porcentaje > 0:
                recargo_label += f' ({venta.recargo_porcentaje}%)'
            recargo_label += ':</b>'
            data.append(['', '', recargo_label, f"+${recargo_monto_calc:.2f}"])
        
        # Si es una venta de diferencia de cambio/devolución, mostrar el monto devuelto
        monto_devuelto_mostrar = Decimal('0.00')
        if CambioDevolucion is not None:
            try:
                cambio_diferencia = venta.cambio_devolucion_diferencia.first()
                if cambio_diferencia:
                    # Mostrar el monto devuelto (productos devueltos)
                    monto_devuelto_mostrar = cambio_diferencia.monto_devolucion
                    if monto_devuelto_mostrar > 0:
                        data.append(['', '', '<b>Monto devuelto (cambio/devolución):</b>', f"-${monto_devuelto_mostrar:.2f}"])
                        # Ajustar el subtotal y total para reflejar el monto devuelto
                        subtotal_final_sin_iva = subtotal_final_sin_iva - (monto_devuelto_mostrar / Decimal('1.21'))
                        total_final = total_final - monto_devuelto_mostrar
                        iva_final = subtotal_final_sin_iva * Decimal('0.21')
            except Exception as e:
                logger.warning(f"⚠️ Error al obtener cambio_devolucion para mostrar monto devuelto: {e}")
        
        # Subtotal sin IVA (después de descuentos/recargos y monto devuelto)
        data.append(['', '', '<b>Subtotal (sin IVA):</b>', f"${subtotal_final_sin_iva:.2f}"])
        
        # IVA
        if iva_final > 0:
            data.append(['', '', '<b>IVA 21%:</b>', f"${iva_final:.2f}"])
        
        # Total
        data.append(['', '', '<b>TOTAL:</b>', f"<b>${total_final:.2f}</b>"])
        
        table = Table(data, colWidths=[20*mm, 100*mm, 30*mm, 30*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -4), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (2, -3), (-1, -1), 'RIGHT'),
            ('FONTNAME', (2, -3), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, -3), (-1, -1), 10),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Pie de página
        story.append(Paragraph("<i>Gracias por su compra</i>", normal_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        
        # Crear respuesta HTTP con el PDF
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="factura_{factura.punto_venta:04d}-{factura.numero_comprobante:08d}.pdf"'
        
        return response

    @action(detail=True, methods=['post'], url_path='emitir_nota_credito')
    def emitir_nota_credito(self, request, pk=None):
        """Emite una Nota de Crédito electrónica vinculada a esta factura."""
        factura = self.get_object()
        user    = request.user

        if not user.is_superuser and user.tienda != factura.tienda:
            return Response({'error': 'No tienes permiso para emitir NC de esta tienda.'},
                            status=status.HTTP_403_FORBIDDEN)

        if factura.estado != 'EMITIDA':
            return Response({'error': 'Solo se pueden emitir notas de crédito para facturas en estado EMITIDA.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if factura.tienda.tipo_facturacion == 'NINGUNA':
            return Response({'error': 'La tienda no tiene configurado un sistema de facturación.'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = EmitirNotaCreditoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Datos inválidos', 'detalles': serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)

        monto  = serializer.validated_data['monto']
        motivo = serializer.validated_data.get('motivo', '')

        if monto <= 0:
            return Response({'error': 'El monto debe ser mayor a cero.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if monto > factura.total:
            return Response(
                {'error': f'El monto (${monto}) no puede superar el total de la factura (${factura.total}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        facturacion_service = FacturacionService(factura.tienda)
        exito, datos_nc, error = facturacion_service.emitir_nota_credito(factura, monto, motivo)

        campos_base = dict(
            factura_origen=factura,
            tienda=factura.tienda,
            punto_venta=factura.tienda.punto_venta,
            tipo_comprobante=factura.tipo_comprobante,
            motivo=motivo,
            monto=monto,
            impuesto_iva=Decimal('0.00'),
            cliente_nombre=factura.cliente_nombre,
            cliente_cuit=factura.cliente_cuit,
            sistema_facturacion=factura.tienda.tipo_facturacion,
        )

        if not exito:
            nc = NotaCredito.objects.create(**campos_base, estado='ERROR', error_mensaje=error)
            return Response({'error': error, 'nc_id': str(nc.id)}, status=status.HTTP_400_BAD_REQUEST)

        campos_base['punto_venta']      = datos_nc.get('punto_venta',      factura.tienda.punto_venta)
        campos_base['tipo_comprobante'] = datos_nc.get('tipo_comprobante', factura.tipo_comprobante)
        campos_base['monto']            = datos_nc.get('monto',            monto)
        campos_base['impuesto_iva']     = datos_nc.get('impuesto_iva',     Decimal('0.00'))

        nc = NotaCredito.objects.create(
            **campos_base,
            numero_comprobante=datos_nc.get('numero_comprobante'),
            estado='EMITIDA',
            cae=datos_nc.get('cae'),
            fecha_vencimiento_cae=datos_nc.get('fecha_vencimiento_cae'),
            numero_comprobante_afip=datos_nc.get('numero_comprobante_afip'),
            respuesta_bruta=datos_nc.get('respuesta_bruta'),
        )

        return Response(
            {'mensaje': 'Nota de crédito emitida exitosamente', 'nota_credito': NotaCreditoSerializer(nc).data},
            status=status.HTTP_201_CREATED,
        )


class NotaCreditoViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar notas de crédito emitidas."""
    serializer_class    = NotaCreditoSerializer
    permission_classes  = [permissions.IsAuthenticated]
    pagination_class    = None
    ordering            = ['-fecha_emision']

    def get_queryset(self):
        user     = self.request.user
        queryset = NotaCredito.objects.select_related('factura_origen', 'tienda').all()

        if user.is_superuser:
            tienda_id = self.request.query_params.get('tienda')
            if tienda_id:
                queryset = queryset.filter(tienda_id=tienda_id)
            else:
                tienda_nombre = self.request.query_params.get('tienda_nombre')
                if tienda_nombre:
                    queryset = queryset.filter(tienda__nombre=tienda_nombre)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            return NotaCredito.objects.none()

        factura_id = self.request.query_params.get('factura')
        if factura_id:
            queryset = queryset.filter(factura_origen_id=factura_id)

        estado = self.request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)

        return queryset


# Siempre definir CambioDevolucionViewSet, pero hacer que verifique los modelos dinámicamente
# Intentar obtener los modelos dinámicamente - puede que Django no los haya cargado todavía en este punto
try:
    _CambioDevolucion, _DetalleCambioDevolucion = _get_cambio_devolucion_models()
    if _CambioDevolucion is not None and _DetalleCambioDevolucion is not None:
        CambioDevolucion = _CambioDevolucion
        DetalleCambioDevolucion = _DetalleCambioDevolucion
except Exception as e:
    logger.warning(f"⚠️ Error al obtener modelos CambioDevolucion en tiempo de definición: {e}")
    CambioDevolucion = None
    DetalleCambioDevolucion = None

# Siempre definir el ViewSet real, verificará los modelos dinámicamente cuando se necesiten
# Crear un serializer temporal para evitar AssertionError de DRF
from rest_framework import serializers as drf_serializers
class _TempSerializer(drf_serializers.Serializer):
    pass

class CambioDevolucionViewSet(viewsets.ModelViewSet):
        """ViewSet para gestionar cambios y devoluciones"""
        permission_classes = [permissions.IsAuthenticated]
        # Usar un serializer temporal, get_serializer_class() lo reemplazará con el correcto
        serializer_class = _TempSerializer
        
        def get_serializer_class(self):
            # Obtener los modelos dinámicamente si aún no están disponibles
            global CambioDevolucion, DetalleCambioDevolucion
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                try:
                    CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                except Exception as e:
                    logger.error(f"Error obteniendo modelos en get_serializer_class: {e}")
                    raise ImportError("CambioDevolucion models not available. Please restart the server after running migrations.")
            
            # Intentar obtener los serializers reales, reimportando si es necesario
            from rest_framework import serializers as drf_serializers
            
            # Obtener referencias locales a los serializers
            serializer = CambioDevolucionSerializer
            create_serializer = CambioDevolucionCreateSerializer
            
            # Si los serializers son dummy, intentar reimportar
            try:
                if (serializer is not None and 
                    not issubclass(serializer, drf_serializers.ModelSerializer)):
                    logger.warning("Serializers son dummy, intentando reimportar...")
                    import importlib
                    import inventario.serializers as serializers_module
                    importlib.reload(serializers_module)
                    from inventario.serializers import CambioDevolucionSerializer as NewSerializer, CambioDevolucionCreateSerializer as NewCreateSerializer
                    serializer = NewSerializer
                    create_serializer = NewCreateSerializer
            except Exception as e:
                logger.error(f"Error al reimportar serializers: {e}")
            
            # Verificar que los serializers son válidos
            try:
                if (serializer is not None and
                    create_serializer is not None and
                    issubclass(serializer, drf_serializers.ModelSerializer) and
                    issubclass(create_serializer, drf_serializers.ModelSerializer) and
                    hasattr(serializer, 'Meta') and
                    hasattr(serializer.Meta, 'model') and
                    serializer.Meta.model == CambioDevolucion):
                    
                    if self.action == 'create':
                        return create_serializer
                    return serializer
            except (TypeError, AttributeError) as e:
                logger.error(f"Error verificando serializers: {e}")
            
            # Si llegamos aquí, los serializers no están disponibles
            raise ImportError("CambioDevolucion serializers not available. Please restart the server after running migrations.")
        
        def get_queryset(self):
            # Obtener los modelos dinámicamente si aún no están disponibles
            global CambioDevolucion, DetalleCambioDevolucion
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                try:
                    CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                except Exception as e:
                    logger.error(f"Error obteniendo modelos en get_queryset: {e}", exc_info=True)
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                from django.core.exceptions import ImproperlyConfigured
                raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            # Continuar con la lógica normal
            user = self.request.user
            queryset = CambioDevolucion.objects.all().select_related(
                'venta_original', 'tienda', 'usuario', 'venta_nota_credito', 'venta_diferencia_pendiente'
            ).prefetch_related('detalles').order_by('-fecha_creacion')
            
            tienda_slug = self.request.query_params.get('tienda_slug', None)
            
            if not user.is_superuser:
                tiendas_ids = list(user.tiendas_autorizadas.values_list('pk', flat=True))
                if user.tienda:
                    tiendas_ids.append(user.tienda.pk)
                if tiendas_ids:
                    queryset = queryset.filter(tienda__pk__in=tiendas_ids)
                else:
                    return CambioDevolucion.objects.none()
            elif tienda_slug:
                queryset = queryset.filter(tienda__nombre=tienda_slug)
            
            # Filtrar por venta original
            venta_id = self.request.query_params.get('venta_original', None)
            if venta_id:
                queryset = queryset.filter(venta_original_id=venta_id)
            
            return queryset
        
        def create(self, request, *args, **kwargs):
                """Sobrescribir create para devolver el objeto con el serializer completo"""
                # Asegurarse de que los modelos estén disponibles
                global CambioDevolucion, DetalleCambioDevolucion
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    try:
                        CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                    except Exception as e:
                        logger.error(f"❌ Error obteniendo modelos en create: {e}", exc_info=True)
                        from django.core.exceptions import ImproperlyConfigured
                        raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                
                # Llamar a perform_create que retorna el objeto creado
                cambio_devolucion = self.perform_create(serializer)
                
                # Refrescar para asegurar que todas las relaciones estén cargadas
                cambio_devolucion.refresh_from_db()
                
                # Usar el serializer completo para la respuesta
                response_serializer = CambioDevolucionSerializer(cambio_devolucion)
                headers = self.get_success_headers(response_serializer.data)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        
        def perform_create(self, serializer):
            """Procesa el cambio/devolución: actualiza stock, genera nota de crédito si aplica"""
            with transaction.atomic():
                return self._perform_create_inner(serializer)

        def _perform_create_inner(self, serializer):
            validated_data = serializer.validated_data
            venta_original = validated_data['venta_original']
            detalles_data = validated_data['detalles']
            tipo = validated_data.get('tipo', 'CAMBIO')
            motivo = validated_data.get('motivo', '')
            descuento_porcentaje = validated_data.get('descuento_porcentaje') or Decimal('0.00')
            descuento_monto = validated_data.get('descuento_monto') or Decimal('0.00')
            recargo_porcentaje = validated_data.get('recargo_porcentaje') or Decimal('0.00')
            recargo_monto = validated_data.get('recargo_monto') or Decimal('0.00')

            # Verificar permisos
            user = self.request.user
            if not user.is_superuser:
                tiendas_ids = set(user.tiendas_autorizadas.values_list('pk', flat=True))
                if user.tienda:
                    tiendas_ids.add(user.tienda.pk)
                if venta_original.tienda.pk not in tiendas_ids:
                    raise drf_serializers.ValidationError({"error": "No tienes permiso para procesar cambios/devoluciones de esta tienda."})
            
            # Calcular montos
            monto_devolucion = Decimal('0.00')
            monto_nuevo = Decimal('0.00')
            
            # Crear el cambio/devolución
            cambio_devolucion = CambioDevolucion.objects.create(
                    venta_original=venta_original,
                    tienda=venta_original.tienda,
                    usuario=user,
                    tipo=tipo,
                    motivo=motivo,
                    estado='PROCESADO',
                    descuento_porcentaje=descuento_porcentaje,
                    descuento_monto=descuento_monto,
                    recargo_porcentaje=recargo_porcentaje,
                    recargo_monto=recargo_monto,
                )
            
            # Procesar cada detalle
            for detalle_data in detalles_data:
                accion = detalle_data['accion']
                cantidad = int(detalle_data['cantidad']) if detalle_data.get('cantidad') is not None else 1
                detalle_venta_original_id = detalle_data.get('detalle_venta_original_id')
                producto_nuevo_id = detalle_data.get('producto_nuevo_id')
                precio_unitario_nuevo_raw = detalle_data.get('precio_unitario_nuevo')
                precio_unitario_nuevo = Decimal(str(precio_unitario_nuevo_raw)) if precio_unitario_nuevo_raw is not None else None
                
                detalle_venta_original = None
                producto_nuevo = None
                
                # Obtener detalle de venta original si aplica
                if detalle_venta_original_id:
                    detalle_venta_original = DetalleVenta.objects.get(id=detalle_venta_original_id)
                    if accion in ('DEVOLVER', 'CAMBIAR') and detalle_venta_original.anulado_individualmente:
                        nombre = detalle_venta_original.producto.nombre if detalle_venta_original.producto else 'producto'
                        raise drf_serializers.ValidationError({
                            "error": f"El producto '{nombre}' ya fue devuelto en un cambio/devolución anterior. Anulá ese cambio antes de intentar otra devolución."
                        })
                
                # Obtener producto nuevo si aplica
                if producto_nuevo_id:
                    producto_nuevo = Producto.objects.get(id=producto_nuevo_id)
                
                # Calcular precios y subtotales
                precio_unitario_devuelto = None
                subtotal_devuelto = Decimal('0.00')
                subtotal_nuevo = Decimal('0.00')
                
                if detalle_venta_original:
                    # Calcular precio ajustado considerando descuentos/recargos de la venta original
                    precio_unitario_original = detalle_venta_original.precio_unitario
                    
                    # Calcular factor de ajuste si hay descuento/recargo porcentual
                    adjustment_factor = Decimal('1.0')
                    venta_original_obj = venta_original
                    
                    if venta_original_obj.descuento_porcentaje and venta_original_obj.descuento_porcentaje > 0:
                        adjustment_factor = Decimal('1.0') - (venta_original_obj.descuento_porcentaje / Decimal('100'))
                    elif venta_original_obj.recargo_porcentaje and venta_original_obj.recargo_porcentaje > 0:
                        adjustment_factor = Decimal('1.0') + (venta_original_obj.recargo_porcentaje / Decimal('100'))
                    
                    # Si el ajuste es por monto, calcular proporcionalmente
                    is_amount_adjustment = (venta_original_obj.descuento_monto and venta_original_obj.descuento_monto > 0) or \
                                           (venta_original_obj.recargo_monto and venta_original_obj.recargo_monto > 0)
                    
                    if is_amount_adjustment:
                        # Calcular el subtotal original de la venta (suma de todos los detalles no anulados)
                        subtotal_original_venta = sum(
                            det.precio_unitario * det.cantidad 
                            for det in venta_original_obj.detalles.all() 
                            if not det.anulado_individualmente
                        )
                        
                        # Calcular el total ajustado
                        total_ajustado = subtotal_original_venta
                        if venta_original_obj.descuento_monto and venta_original_obj.descuento_monto > 0:
                            total_ajustado = subtotal_original_venta - venta_original_obj.descuento_monto
                        elif venta_original_obj.recargo_monto and venta_original_obj.recargo_monto > 0:
                            total_ajustado = subtotal_original_venta + venta_original_obj.recargo_monto
                        
                        # Calcular el factor de proporción
                        if subtotal_original_venta > 0:
                            factor_proporcion = total_ajustado / subtotal_original_venta
                            precio_unitario_devuelto = precio_unitario_original * factor_proporcion
                        else:
                            precio_unitario_devuelto = precio_unitario_original
                    else:
                        # Si es porcentual, aplicar el factor directamente
                        precio_unitario_devuelto = precio_unitario_original * adjustment_factor
                    
                    subtotal_devuelto = precio_unitario_devuelto * cantidad
                    monto_devolucion += subtotal_devuelto
                
                if producto_nuevo and precio_unitario_nuevo:
                    subtotal_nuevo = precio_unitario_nuevo * cantidad
                    monto_nuevo += subtotal_nuevo
                
                # Crear detalle del cambio/devolución
                DetalleCambioDevolucion.objects.create(
                cambio_devolucion=cambio_devolucion,
                detalle_venta_original=detalle_venta_original,
                producto_nuevo=producto_nuevo,
                accion=accion,
                cantidad=cantidad,
                precio_unitario_devuelto=precio_unitario_devuelto,
                precio_unitario_nuevo=precio_unitario_nuevo,
                subtotal_devuelto=subtotal_devuelto,
                subtotal_nuevo=subtotal_nuevo
                )
                
                # Manejar stock
                if accion == 'DEVOLVER':
                    # Devolver stock del producto original
                    if detalle_venta_original and detalle_venta_original.producto:
                        producto = detalle_venta_original.producto
                        producto.stock = (producto.stock or 0) + cantidad
                        producto.save(update_fields=['stock'])
                        from .services.tiendanube_service import sincronizar_stock_producto
                        sincronizar_stock_producto(producto)

                        # Anular el detalle de venta si se devuelve todo
                        if cantidad >= detalle_venta_original.cantidad:
                            detalle_venta_original.anulado_individualmente = True
                            detalle_venta_original.save(update_fields=['anulado_individualmente'])

                elif accion == 'CAMBIAR':
                    # Devolver stock del producto original
                    if detalle_venta_original and detalle_venta_original.producto:
                        producto = detalle_venta_original.producto
                        producto.stock = (producto.stock or 0) + cantidad
                        producto.save(update_fields=['stock'])
                        from .services.tiendanube_service import sincronizar_stock_producto
                        sincronizar_stock_producto(producto)

                        # Anular el detalle de venta si se cambia todo
                        if cantidad >= detalle_venta_original.cantidad:
                            detalle_venta_original.anulado_individualmente = True
                            detalle_venta_original.save(update_fields=['anulado_individualmente'])

                    # Reducir stock del producto nuevo
                    if producto_nuevo:
                        if (producto_nuevo.stock or 0) < cantidad:
                            raise drf_serializers.ValidationError({"error": f"Stock insuficiente para el producto {producto_nuevo.nombre}."})
                        producto_nuevo.stock = (producto_nuevo.stock or 0) - cantidad
                        producto_nuevo.save(update_fields=['stock'])
                        from .services.tiendanube_service import sincronizar_stock_producto
                        sincronizar_stock_producto(producto_nuevo)

                elif accion == 'AGREGAR':
                    # Reducir stock del producto nuevo
                    if producto_nuevo:
                        if (producto_nuevo.stock or 0) < cantidad:
                            raise drf_serializers.ValidationError({"error": f"Stock insuficiente para el producto {producto_nuevo.nombre}."})
                        producto_nuevo.stock = (producto_nuevo.stock or 0) - cantidad
                        producto_nuevo.save(update_fields=['stock'])
                        from .services.tiendanube_service import sincronizar_stock_producto
                        sincronizar_stock_producto(producto_nuevo)
            
            # Después de procesar todos los detalles: calcular montos totales y generar nota de crédito/venta pendiente
            monto_diferencia = monto_nuevo - monto_devolucion

            # El descuento/recargo cargado en este cambio se usa para decidir si
            # corresponde nota de crédito o diferencia a pagar -- mismo criterio
            # (% sobre el total de productos nuevos, $ sobre la diferencia) que usa
            # VentaCreateSerializer al crear la venta por la diferencia. Sin esto, un
            # recargo que debería convertir un saldo a favor en una diferencia a
            # cobrar se ignoraba acá y se emitía una nota de crédito igual.
            # monto_nuevo/monto_diferencia quedan sin ajustar porque esa venta los
            # vuelve a usar como base (evita aplicar el recargo dos veces).
            if descuento_porcentaje > 0:
                monto_diferencia_ajustada = monto_nuevo * (Decimal('1') - descuento_porcentaje / Decimal('100')) - monto_devolucion
            elif descuento_monto > 0:
                monto_diferencia_ajustada = monto_diferencia - descuento_monto
            elif recargo_monto > 0:
                monto_diferencia_ajustada = monto_diferencia + recargo_monto
            elif recargo_porcentaje > 0:
                monto_diferencia_ajustada = monto_diferencia * (Decimal('1') + recargo_porcentaje / Decimal('100'))
            else:
                monto_diferencia_ajustada = monto_diferencia

            saldo_a_favor = abs(monto_diferencia_ajustada) if monto_diferencia_ajustada < 0 else Decimal('0.00')

            cambio_devolucion.monto_devolucion = monto_devolucion
            cambio_devolucion.monto_nuevo = monto_nuevo
            cambio_devolucion.monto_diferencia = monto_diferencia
            cambio_devolucion.saldo_a_favor = saldo_a_favor
            cambio_devolucion.save()
            
            # Si hay saldo a favor, generar automáticamente recibo/nota de crédito (una sola vez)
            if saldo_a_favor > 0:
                try:
                    venta_nota_credito = Venta.objects.create(
                        total=saldo_a_favor,
                        tienda=venta_original.tienda,
                        usuario=user,
                        metodo_pago='Nota de Crédito',
                        fecha_venta=timezone.now(),
                        facturada=False,
                        descuento_monto=saldo_a_favor,
                        descuento_porcentaje=Decimal('0.00'),
                        recargo_monto=Decimal('0.00'),
                        recargo_porcentaje=Decimal('0.00'),
                    )
                    DetalleVenta.objects.create(
                        venta=venta_nota_credito,
                        producto=None,
                        cantidad=1,
                        precio_unitario=saldo_a_favor,
                        subtotal=saldo_a_favor,
                        costo_unitario=Decimal('0.00'),
                    )
                    cambio_devolucion.nota_credito_generada = True
                    cambio_devolucion.venta_nota_credito = venta_nota_credito
                    cambio_devolucion.save()
                    logger.info(f"✅ Nota de crédito generada automáticamente: {venta_nota_credito.id} por ${saldo_a_favor}")
                except Exception as e:
                    logger.error(f"Error al generar nota de crédito automática: {str(e)}", exc_info=True)
                    raise drf_serializers.ValidationError({
                        "error": f"No se pudo generar la nota de crédito: {str(e)}. Detalles: {repr(e)}"
                    })
            
            # Si hay diferencia a pagar, marcar el cambio/devolución como pendiente.
            # La venta se crea desde el frontend con el método de pago real y cambio_devolucion_id,
            # y el serializer de Venta la vincula automáticamente al asignar venta_diferencia_pendiente.
            if monto_diferencia_ajustada > 0:
                cambio_devolucion.diferencia_pendiente = True
                cambio_devolucion.save()
                logger.info(f"✅ Diferencia pendiente marcada: ${monto_diferencia_ajustada} (bruta ${monto_diferencia}) para cambio/devolución {cambio_devolucion.id}")
            
            tipo_label = 'Cambio' if tipo == 'CAMBIO' else 'Devolución'
            try:
                prods = ', '.join(
                    d.detalle_venta_original.producto.nombre
                    for d in cambio_devolucion.detalles.all()
                    if d.detalle_venta_original and d.detalle_venta_original.producto
                )
            except Exception:
                prods = '—'
            _registrar_accion(
                tienda=cambio_devolucion.tienda,
                usuario=user,
                accion='cambio_devolucion',
                detalle=f'{tipo_label}: {prods} · dif. ${cambio_devolucion.monto_diferencia}' + (f' · {motivo}' if motivo else ''),
                objeto_id=cambio_devolucion.id,
            )
            return cambio_devolucion

        @action(detail=True, methods=['get'], url_path='obtener-venta-diferencia')
        def obtener_venta_diferencia(self, request, pk=None):
            cambio_devolucion = get_object_or_404(CambioDevolucion, pk=pk)
            
            if not cambio_devolucion.diferencia_pendiente or not cambio_devolucion.venta_diferencia_pendiente:
                return Response(
                    {"error": "No hay venta pendiente para la diferencia."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            venta_serializer = VentaSerializer(cambio_devolucion.venta_diferencia_pendiente)
            return Response({
                "venta": venta_serializer.data,
                "monto_diferencia": cambio_devolucion.monto_diferencia,
                "message": "Esta venta puede ser completada desde el flujo normal de ventas."
            })
        
        def update(self, request, *args, **kwargs):
            cambio_devolucion = self.get_object()
            
            if cambio_devolucion.estado == 'CANCELADO':
                return Response(
                    {"error": "Este cambio/devolución ya está cancelado."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            nuevo_estado = request.data.get('estado')
            if nuevo_estado == 'CANCELADO':
                with transaction.atomic():
                    for detalle in cambio_devolucion.detalles.all():
                        if detalle.accion in ['DEVOLVER', 'CAMBIAR'] and detalle.detalle_venta_original:
                            if detalle.detalle_venta_original.producto:
                                producto = detalle.detalle_venta_original.producto
                                producto.stock = (producto.stock or 0) - detalle.cantidad
                                producto.save(update_fields=['stock'])
                                from .services.tiendanube_service import sincronizar_stock_producto
                                sincronizar_stock_producto(producto)

                            if detalle.detalle_venta_original.anulado_individualmente:
                                detalle.detalle_venta_original.anulado_individualmente = False
                                detalle.detalle_venta_original.save(update_fields=['anulado_individualmente'])

                        if detalle.accion in ['CAMBIAR', 'AGREGAR'] and detalle.producto_nuevo:
                            producto = detalle.producto_nuevo
                            producto.stock = (producto.stock or 0) + detalle.cantidad
                            producto.save(update_fields=['stock'])
                            from .services.tiendanube_service import sincronizar_stock_producto
                            sincronizar_stock_producto(producto)

                    cambio_devolucion.estado = 'CANCELADO'
                    cambio_devolucion.save()
                logger.info(f"✅ Cambio/Devolución {cambio_devolucion.id} cancelado. Stock revertido.")
                
                return Response({
                    "message": "Cambio/Devolución cancelado con éxito. Los cambios de stock han sido revertidos.",
                    "estado": "CANCELADO"
                })
            
            return super().update(request, *args, **kwargs)
        
        def list(self, request, *args, **kwargs):
            global CambioDevolucion, DetalleCambioDevolucion
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                try:
                    CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                except Exception as e:
                    logger.error(f"❌ Error obteniendo modelos en list: {e}", exc_info=True)
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                from django.core.exceptions import ImproperlyConfigured
                raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            close_old_connections()
            return super().list(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Cierre de Caja
# ─────────────────────────────────────────────────────────────────────────────

class CierreCajaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CierreCajaSerializer

    def get_queryset(self):
        user = self.request.user
        tienda_slug = self.request.query_params.get('tienda')
        fecha_desde = self.request.query_params.get('fecha_desde')
        fecha_hasta = self.request.query_params.get('fecha_hasta')

        qs = CierreCaja.objects.select_related('tienda', 'usuario').prefetch_related('egresos')

        if user.is_superuser:
            pass  # ve todos los cierres
        elif user.is_supervisor:
            # Supervisor ve cierres de su tienda principal + autorizadas + los que abrió él
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if tiendas_ids:
                qs = qs.filter(Q(tienda__pk__in=tiendas_ids) | Q(usuario=user))
            else:
                qs = qs.filter(usuario=user)
        else:
            # Staff y usuarios normales solo ven sus propios cierres
            qs = qs.filter(usuario=user)

        if tienda_slug:
            qs = qs.filter(tienda__nombre=tienda_slug)
        if fecha_desde:
            qs = qs.filter(fecha_apertura__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_apertura__date__lte=fecha_hasta)

        return qs

    def _get_tienda(self, request):
        tienda_slug = request.data.get('tienda_slug') or request.query_params.get('tienda')
        if tienda_slug:
            return Tienda.objects.get(nombre=tienda_slug)
        if request.user.tienda:
            return request.user.tienda
        raise serializers.ValidationError({'tienda': 'No se puede determinar la tienda.'})

    def create(self, request, *args, **kwargs):
        tienda = self._get_tienda(request)
        # Bloqueo a nivel DB para evitar doble apertura por race condition
        with transaction.atomic():
            ya_abierta = CierreCaja.objects.select_for_update().filter(
                usuario=request.user, tienda=tienda, estado='ABIERTO'
            ).exists()
            if ya_abierta:
                return Response(
                    {'error': 'Ya tenés una caja abierta para esta tienda. Cerrala antes de abrir una nueva.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        tienda = self._get_tienda(self.request)
        serializer.save(usuario=self.request.user, tienda=tienda)

    @action(detail=False, methods=['get'], url_path='activo')
    def activo(self, request):
        tienda_slug = request.query_params.get('tienda')
        qs = CierreCaja.objects.filter(usuario=request.user, estado='ABIERTO')
        if tienda_slug:
            qs = qs.filter(tienda__nombre=tienda_slug)
        cierre = qs.order_by('-fecha_apertura').first()
        if cierre:
            return Response(CierreCajaSerializer(cierre).data)
        return Response(None)

    @action(detail=True, methods=['post'], url_path='cerrar')
    def cerrar(self, request, pk=None):
        cierre = self.get_object()
        if cierre.estado == 'CERRADO':
            return Response({'error': 'El cierre ya está cerrado.'}, status=400)

        # Ventas en efectivo del período
        # Suma el monto en efectivo real de cada venta:
        # - ventas nuevas: usa monto_efectivo (correcto para pagos combinados)
        # - ventas de cambio/devolución: usa monto_diferencia (no el total del producto completo)
        # - ventas antiguas sin monto_efectivo: fallback a total si el método era puro efectivo
        from django.db.models import Case, When, F, Value
        from django.db.models import DecimalField as _Dec
        CambioDevolucion_cls, _ = _get_cambio_devolucion_models()
        ventas_qs_cierre = Venta.objects.filter(
            tienda=cierre.tienda,
            usuario=cierre.usuario,
            fecha_venta__gte=cierre.fecha_apertura,
            anulada=False,
        ).exclude(metodo_pago__in=['Nota de Crédito', 'Pendiente'])
        if CambioDevolucion_cls is not None:
            sq_monto_dif = CambioDevolucion_cls.objects.filter(
                venta_diferencia_pendiente=OuterRef('pk')
            ).values('monto_diferencia')[:1]
            ventas_qs_cierre = ventas_qs_cierre.annotate(
                _monto_dif=Subquery(sq_monto_dif, output_field=_Dec(max_digits=10, decimal_places=2))
            )
            case_efectivo = Case(
                When(monto_efectivo__isnull=False, then=F('monto_efectivo')),
                When(Q(_monto_dif__isnull=False) & Q(metodo_pago__icontains='efectivo'), then=F('_monto_dif')),
                When(metodo_pago__icontains='efectivo', then=F('total')),
                default=Value(Decimal('0.00')),
                output_field=_Dec(max_digits=12, decimal_places=2),
            )
        else:
            case_efectivo = Case(
                When(monto_efectivo__isnull=False, then=F('monto_efectivo')),
                When(metodo_pago__icontains='efectivo', then=F('total')),
                default=Value(Decimal('0.00')),
                output_field=_Dec(max_digits=12, decimal_places=2),
            )
        ventas_efectivo = ventas_qs_cierre.aggregate(
            total=Sum(case_efectivo)
        )['total'] or Decimal('0.00')

        # Separar movimientos por tipo
        def _sum_tipo(tipo):
            return cierre.egresos.filter(tipo=tipo).aggregate(
                total=Sum('importe')
            )['total'] or Decimal('0.00')

        total_gastos   = _sum_tipo('EGRESO')
        total_retiros  = _sum_tipo('RETIRO')
        total_ingresos = _sum_tipo('INGRESO')

        def _int(val):
            try:
                return max(0, int(val or 0))
            except (ValueError, TypeError):
                return 0

        cierre.billetes_20000 = _int(request.data.get('billetes_20000'))
        cierre.billetes_10000 = _int(request.data.get('billetes_10000'))
        cierre.billetes_2000  = _int(request.data.get('billetes_2000'))
        cierre.billetes_1000  = _int(request.data.get('billetes_1000'))
        cierre.billetes_500   = _int(request.data.get('billetes_500'))
        cierre.billetes_200   = _int(request.data.get('billetes_200'))
        cierre.billetes_100   = _int(request.data.get('billetes_100'))
        cierre.monedas        = Decimal(str(request.data.get('monedas') or 0))

        cierre.total_ventas_efectivo = ventas_efectivo
        cierre.total_gastos          = total_gastos
        cierre.total_retiros         = total_retiros
        cierre.total_ingresos_extra  = total_ingresos
        cierre.total_egresos         = total_gastos + total_retiros  # total salidas
        cierre.total_recuento_fisico = cierre.calcular_recuento_fisico()

        # total teórico en caja = inicio + ventas efectivo + ingresos extra - gastos - retiros
        total_teorico  = cierre.cambio_inicial + ventas_efectivo + total_ingresos - total_gastos - total_retiros
        cierre.diferencia    = cierre.total_recuento_fisico - total_teorico
        cierre.estado        = 'CERRADO'
        cierre.fecha_cierre  = timezone.now()
        cierre.notas         = request.data.get('notas', '') or ''
        cierre.save()

        return Response(CierreCajaSerializer(cierre).data)

    @action(detail=True, methods=['get'], url_path='ventas-efectivo')
    def ventas_efectivo(self, request, pk=None):
        from django.db.models import Q
        cierre = self.get_object()
        qs = Venta.objects.filter(
            tienda=cierre.tienda,
            usuario=cierre.usuario,
            fecha_venta__gte=cierre.fecha_apertura,
            anulada=False,
        ).filter(
            # ventas nuevas con efectivo > 0, o ventas antiguas con metodo efectivo
            Q(monto_efectivo__gt=0) |
            Q(monto_efectivo__isnull=True, metodo_pago__icontains='efectivo')
        )

        if cierre.fecha_cierre:
            qs = qs.filter(fecha_venta__lte=cierre.fecha_cierre)

        return Response(list(
            qs.values('id', 'fecha_venta', 'total', 'monto_efectivo', 'cliente_nombre', 'metodo_pago')
        ))

    @action(detail=True, methods=['get'], url_path='ventas-resumen')
    def ventas_resumen(self, request, pk=None):
        """Retorna todas las ventas del turno agrupadas por método de pago, más el detalle individual."""
        cierre = self.get_object()
        qs = Venta.objects.filter(
            tienda=cierre.tienda,
            usuario=cierre.usuario,
            fecha_venta__gte=cierre.fecha_apertura,
            anulada=False,
        ).exclude(
            # Las notas de crédito son saldo a favor del cliente (no ingreso real)
            # y las Pendientes son placeholders sin cobro efectivo.
            metodo_pago__in=['Nota de Crédito', 'Pendiente']
        )
        if cierre.fecha_cierre:
            qs = qs.filter(fecha_venta__lte=cierre.fecha_cierre)

        # Para efectivo puro, mostrar monto_efectivo (cash real) en lugar del total del producto.
        # Esto evita que ventas de cambio/devolución inflen el total mostrado por método.
        from django.db.models import Case, When, F, Q as _Q
        from django.db.models import DecimalField as _Dec
        qs_con_importe = qs.annotate(
            importe_metodo=Case(
                When(
                    _Q(metodo_pago__icontains='efectivo') & ~_Q(metodo_pago__contains='+') & _Q(monto_efectivo__isnull=False),
                    then=F('monto_efectivo')
                ),
                default=F('total'),
                output_field=_Dec(max_digits=12, decimal_places=2)
            )
        )
        por_metodo = list(
            qs_con_importe.values('metodo_pago')
              .annotate(total=Sum('importe_metodo'), cantidad=Count('id'))
              .order_by('metodo_pago')
        )

        ventas = list(qs.values('id', 'fecha_venta', 'total', 'cliente_nombre', 'metodo_pago').order_by('fecha_venta'))

        # Suma el efectivo real del turno (igual que el endpoint cerrar)
        # Para ventas de cambio/devolución usa monto_diferencia, no el total del producto completo
        from django.db.models import Case, When, F, Value, Q as _Q
        from django.db.models import DecimalField as _Dec
        CambioDevolucion_vr, _ = _get_cambio_devolucion_models()
        qs_ef = qs.filter(
            _Q(monto_efectivo__gt=0) |
            _Q(monto_efectivo__isnull=True, metodo_pago__icontains='efectivo')
        )
        if CambioDevolucion_vr is not None:
            sq_dif = CambioDevolucion_vr.objects.filter(
                venta_diferencia_pendiente=OuterRef('pk')
            ).values('monto_diferencia')[:1]
            qs_ef = qs_ef.annotate(
                _monto_dif=Subquery(sq_dif, output_field=_Dec(max_digits=10, decimal_places=2))
            )
            case_ef = Case(
                When(monto_efectivo__isnull=False, then=F('monto_efectivo')),
                When(_Q(_monto_dif__isnull=False) & _Q(metodo_pago__icontains='efectivo'), then=F('_monto_dif')),
                When(metodo_pago__icontains='efectivo', then=F('total')),
                default=Value(Decimal('0.00')),
                output_field=_Dec(max_digits=12, decimal_places=2),
            )
        else:
            case_ef = Case(
                When(monto_efectivo__isnull=False, then=F('monto_efectivo')),
                When(metodo_pago__icontains='efectivo', then=F('total')),
                default=Value(Decimal('0.00')),
                output_field=_Dec(max_digits=12, decimal_places=2),
            )
        total_ventas_efectivo = qs_ef.aggregate(total=Sum(case_ef))['total'] or Decimal('0.00')

        return Response({
            'por_metodo': por_metodo,
            'ventas': ventas,
            'total_ventas_efectivo': float(total_ventas_efectivo),
        })


class EgresoCajaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EgresoCajaSerializer

    def get_queryset(self):
        user = self.request.user
        cierre_id = self.request.query_params.get('cierre_caja')
        tienda_slug = self.request.query_params.get('tienda')

        qs = EgresoCaja.objects.select_related('cierre_caja', 'usuario')
        if not user.is_superuser:
            qs = qs.filter(usuario=user)
        if cierre_id:
            qs = qs.filter(cierre_caja_id=cierre_id)
        if tienda_slug:
            qs = qs.filter(tienda__nombre=tienda_slug)

        return qs

    def perform_create(self, serializer):
        tienda_slug = self.request.data.get('tienda_slug')
        if tienda_slug:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        elif self.request.user.tienda:
            tienda = self.request.user.tienda
        else:
            raise serializers.ValidationError({'tienda': 'No se puede determinar la tienda.'})

        egreso = serializer.save(usuario=self.request.user, tienda=tienda)

        # Solo los Gastos (EGRESO) impactan en Registro de Egresos y métricas.
        # Retiros e Ingresos quedan solo en el cierre de caja.
        if egreso.tipo == 'EGRESO':
            Compra.objects.create(
                tienda=tienda,
                total=egreso.importe,
                proveedor=f"[Caja] Gasto: {egreso.concepto}",
                usuario=self.request.user,
            )

    def perform_destroy(self, instance):
        # Si era un EGRESO, revertir la Compra asociada que se creó al registrarlo.
        if instance.tipo == 'EGRESO':
            compra = Compra.objects.filter(
                tienda=instance.tienda,
                proveedor=f"[Caja] Gasto: {instance.concepto}",
                total=instance.importe,
            ).order_by('-fecha_compra').first()
            if compra:
                compra.delete()
        instance.delete()


# ── Clientes y Cuenta Corriente ────────────────────────────────────────────────

class ClienteViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ClienteSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Cliente.objects.select_related('tienda')
        tienda_slug = self.request.query_params.get('tienda_slug')

        if user.is_superuser:
            if tienda_slug:
                qs = qs.filter(tienda__nombre=tienda_slug)
        else:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if not tiendas_ids:
                return Cliente.objects.none()
            qs = qs.filter(tienda__pk__in=tiendas_ids)
            if tienda_slug:
                # Búsqueda desde Punto de Venta: acotada a la tienda puntual de la venta en curso,
                # no al conjunto ampliado de tiendas autorizadas (mismo criterio que evitó el bug
                # de scoping multi-tienda en Cambio/Devolución).
                qs = qs.filter(tienda__nombre=tienda_slug)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                models.Q(cuit_cuil__icontains=search) | models.Q(nombre_razon_social__icontains=search)
            )

        if self.request.query_params.get('incluir_inactivos') != 'true':
            qs = qs.filter(activo=True)

        return qs

    def perform_destroy(self, instance):
        # Soft delete: un cliente con historial de compras o cuenta corriente no se borra en duro.
        instance.activo = False
        instance.save(update_fields=['activo'])

    @action(detail=True, methods=['get'])
    def historial(self, request, pk=None):
        cliente = self.get_object()
        ventas = Venta.objects.filter(cliente=cliente, anulada=False).select_related(
            'tienda', 'usuario', 'arancel_aplicado', 'factura'
        ).prefetch_related('detalles__producto').order_by('-fecha_venta')
        movimientos = cliente.movimientos_cuenta_corriente.all().order_by('-fecha')
        tiene_deuda_vencida, fecha_vencimiento_mas_antigua = obtener_deuda_vencida_info(cliente)
        return Response({
            'saldo_pendiente': str(calcular_saldo_pendiente(cliente)),
            'tiene_deuda_vencida': tiene_deuda_vencida,
            'fecha_vencimiento_mas_antigua': fecha_vencimiento_mas_antigua,
            # Serializer completo: permite reimprimir el recibo de cada consumo igual que en Listado de Ventas.
            'ventas': VentaSerializer(ventas, many=True, context={'request': request}).data,
            'movimientos': MovimientoCuentaCorrienteSerializer(movimientos, many=True).data,
        })

    @action(detail=False, methods=['get'])
    def deuda_vencida(self, request):
        """Clientes con saldo pendiente y al menos una venta a Cuenta Corriente vencida (para la alerta)."""
        clientes_con_deuda = [c for c in self.get_queryset() if obtener_deuda_vencida_info(c)[0]]
        serializer = ClienteSerializer(clientes_con_deuda, many=True, context={'request': request})
        return Response({'count': len(clientes_con_deuda), 'results': serializer.data})

    @action(detail=True, methods=['post'])
    def cobrar_deuda(self, request, pk=None):
        from decimal import InvalidOperation

        metodo_pago = (request.data.get('metodo_pago') or '').strip()
        tienda_slug = request.data.get('tienda_slug')
        if not metodo_pago:
            return Response({'error': 'Se requiere un método de pago.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            monto = Decimal(str(request.data.get('monto')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto <= 0:
            return Response({'error': 'El monto debe ser mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            cliente = Cliente.objects.select_for_update().get(pk=pk)

            if not request.user.is_superuser and cliente.tienda_id not in _get_tiendas_ids_usuario(request.user):
                return Response(
                    {'error': 'No tenés permiso para operar sobre este cliente.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            saldo_actual = calcular_saldo_pendiente(cliente)
            if monto > saldo_actual:
                return Response(
                    {'error': f'El monto (${monto}) supera el saldo pendiente (${saldo_actual}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Si es efectivo y hay una caja abierta, el ingreso se suma a esa caja para la
            # reconciliación del turno. Si no hay caja abierta, el cobro se registra igual
            # en la cuenta corriente; simplemente no queda un ingreso de caja asociado.
            cierre_abierto = None
            if 'efectivo' in metodo_pago.lower():
                tienda_para_caja = cliente.tienda
                if tienda_slug:
                    tienda_resuelta = Tienda.objects.filter(nombre=tienda_slug).first()
                    if tienda_resuelta:
                        tienda_para_caja = tienda_resuelta
                cierre_abierto = CierreCaja.objects.filter(
                    usuario=request.user, tienda=tienda_para_caja, estado='ABIERTO'
                ).first()

            movimiento = MovimientoCuentaCorriente.objects.create(
                cliente=cliente,
                tienda=cliente.tienda,
                tipo='CREDITO',
                monto=monto,
                concepto=f'Cobro cuenta corriente - {metodo_pago}',
                usuario=request.user,
            )

            # Reutiliza EgresoCaja(tipo='INGRESO'): ya confirmado que solo impacta la
            # reconciliación de caja (total_ingresos_extra) y no las métricas de venta,
            # ya que solo tipo='EGRESO' genera una Compra sombra (perform_create más abajo).
            if cierre_abierto:
                EgresoCaja.objects.create(
                    cierre_caja=cierre_abierto,
                    tienda=cierre_abierto.tienda,
                    usuario=request.user,
                    tipo='INGRESO',
                    concepto=f'Cobro cuenta corriente - {cliente.nombre_razon_social}',
                    importe=monto,
                )

            saldo_final = calcular_saldo_pendiente(cliente)

        return Response({
            'ok': True,
            'movimiento': MovimientoCuentaCorrienteSerializer(movimiento).data,
            'saldo_pendiente': str(saldo_final),
            'egreso_caja_creado': cierre_abierto is not None,
        })


# ── Rubros (IVA por rubro para carga masiva de productos) ────────────────────

class RubroViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RubroSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Rubro.objects.select_related('tienda')
        tienda_slug = self.request.query_params.get('tienda_slug')

        if user.is_superuser:
            if tienda_slug:
                qs = qs.filter(tienda__nombre=tienda_slug)
        else:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if not tiendas_ids:
                return Rubro.objects.none()
            qs = qs.filter(tienda__pk__in=tiendas_ids)
            if tienda_slug:
                qs = qs.filter(tienda__nombre=tienda_slug)

        return qs


# ── Presupuestos ──────────────────────────────────────────────────────────────

class PresupuestoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return PresupuestoCreateSerializer
        return PresupuestoSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Presupuesto.objects.select_related('tienda', 'cliente', 'usuario').prefetch_related('detalles__producto')
        tienda_slug = self.request.query_params.get('tienda_slug')

        if user.is_superuser:
            if tienda_slug:
                qs = qs.filter(tienda__nombre=tienda_slug)
        else:
            tiendas_ids = _get_tiendas_ids_usuario(user)
            if not tiendas_ids:
                return Presupuesto.objects.none()
            qs = qs.filter(tienda__pk__in=tiendas_ids)
            if tienda_slug:
                qs = qs.filter(tienda__nombre=tienda_slug)

        id_busqueda = self.request.query_params.get('id')
        if id_busqueda:
            qs = qs.filter(id__istartswith=id_busqueda.strip())

        cliente_busqueda = self.request.query_params.get('cliente')
        if cliente_busqueda:
            qs = qs.filter(
                models.Q(cliente__nombre_razon_social__icontains=cliente_busqueda) |
                models.Q(cliente__cuit_cuil__icontains=cliente_busqueda)
            )

        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_creacion__date__gte=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_creacion__date__lte=fecha_hasta)

        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        return qs

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        if serializer.instance.estado != 'PENDIENTE':
            raise drf_serializers.ValidationError(
                "Solo se puede modificar un presupuesto mientras está Pendiente."
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.estado == 'CONVERTIDO':
            raise drf_serializers.ValidationError(
                "No se puede eliminar un presupuesto ya convertido en venta."
            )
        instance.delete()

    def _construir_pdf(self, presupuesto):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'PresupuestoTitle', parent=styles['Heading1'], fontSize=16,
            textColor=colors.HexColor('#000000'), spaceAfter=12, alignment=1
        )
        subtitle_style = ParagraphStyle(
            'PresupuestoSubtitle', parent=styles['Heading2'], fontSize=14,
            textColor=colors.HexColor('#000000'), spaceAfter=8, alignment=1
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.textColor = colors.HexColor('#000000')

        story = []
        tienda = presupuesto.tienda
        cliente = presupuesto.cliente

        tiene_logo = False
        if tienda.logo:
            try:
                match_logo = re.match(r'^data:image/\w+;base64,(.+)$', tienda.logo)
                logo_b64 = match_logo.group(1) if match_logo else tienda.logo
                logo_image = Image(BytesIO(base64.b64decode(logo_b64)), width=30 * mm, height=20 * mm, kind='proportional')
                logo_image.hAlign = 'CENTER'
                story.append(logo_image)
                story.append(Spacer(1, 8))
                tiene_logo = True
            except Exception:
                pass

        # Con logo, el nombre de la tienda pasa a un segundo plano (el logo ya la identifica)
        if tiene_logo:
            nombre_tienda_style = ParagraphStyle(
                'PresupuestoNombreTiendaChico', parent=styles['Normal'], fontSize=10,
                textColor=colors.HexColor('#555555'), spaceAfter=12, alignment=1
            )
            story.append(Paragraph(tienda.nombre, nombre_tienda_style))
        else:
            story.append(Paragraph(f"<b>{tienda.nombre}</b>", title_style))
        story.append(Paragraph("PRESUPUESTO", subtitle_style))
        story.append(Spacer(1, 12))

        if tienda.cuit:
            story.append(Paragraph(f"<b>CUIT:</b> {tienda.cuit}", normal_style))
        if tienda.direccion:
            story.append(Paragraph(f"<b>Domicilio:</b> {tienda.direccion}", normal_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph(f"<b>Fecha:</b> {presupuesto.fecha_creacion.strftime('%d/%m/%Y %H:%M')}", normal_style))
        story.append(Paragraph(f"<b>Nº de Presupuesto:</b> {presupuesto.id}", normal_style))
        if presupuesto.fecha_vigencia:
            story.append(Paragraph(f"<b>Válido hasta:</b> {presupuesto.fecha_vigencia.strftime('%d/%m/%Y')}", normal_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("<b>DATOS DEL CLIENTE</b>", normal_style))
        story.append(Paragraph(f"<b>Nombre:</b> {cliente.nombre_razon_social}", normal_style))
        story.append(Paragraph(f"<b>CUIT/DNI:</b> {cliente.cuit_cuil}", normal_style))
        if cliente.email:
            story.append(Paragraph(f"<b>Email:</b> {cliente.email}", normal_style))
        story.append(Spacer(1, 12))

        data = [['Cant.', 'Descripción', 'Precio Unit.', 'Subtotal']]
        subtotal_bruto = Decimal('0.00')
        for detalle in presupuesto.detalles.all():
            producto_nombre = detalle.producto.nombre if detalle.producto else 'Producto eliminado'
            precio_unitario = Decimal(str(detalle.precio_unitario))
            subtotal_bruto += precio_unitario * Decimal(str(detalle.cantidad))
            data.append([
                str(detalle.cantidad),
                producto_nombre,
                f"${precio_unitario:.2f}",
                f"${detalle.subtotal:.2f}",
            ])

        cantidad_items = len(data) - 1  # sin contar la fila de encabezado

        data.append(['', '', '', ''])
        inicio_totales = len(data)  # primera fila de la sección de totales (la separadora)
        data.append(['', '', 'Subtotal:', f"${subtotal_bruto:.2f}"])

        if presupuesto.descuento_monto and presupuesto.descuento_monto > 0:
            label = 'Descuento'
            if presupuesto.descuento_porcentaje and presupuesto.descuento_porcentaje > 0:
                label += f' ({presupuesto.descuento_porcentaje}%)'
            label += ':'
            data.append(['', '', label, f"-${presupuesto.descuento_monto:.2f}"])
        elif presupuesto.descuento_porcentaje and presupuesto.descuento_porcentaje > 0:
            monto = subtotal_bruto * (presupuesto.descuento_porcentaje / Decimal('100'))
            data.append(['', '', f'Descuento ({presupuesto.descuento_porcentaje}%):', f"-${monto:.2f}"])

        if presupuesto.recargo_monto and presupuesto.recargo_monto > 0:
            label = 'Recargo'
            if presupuesto.recargo_porcentaje and presupuesto.recargo_porcentaje > 0:
                label += f' ({presupuesto.recargo_porcentaje}%)'
            label += ':'
            data.append(['', '', label, f"+${presupuesto.recargo_monto:.2f}"])
        elif presupuesto.recargo_porcentaje and presupuesto.recargo_porcentaje > 0:
            monto = subtotal_bruto * (presupuesto.recargo_porcentaje / Decimal('100'))
            data.append(['', '', f'Recargo ({presupuesto.recargo_porcentaje}%):', f"+${monto:.2f}"])

        data.append(['', '', 'TOTAL:', f"${Decimal(str(presupuesto.total)):.2f}"])

        table = Table(data, colWidths=[20 * mm, 100 * mm, 30 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, cantidad_items), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (2, inicio_totales), (-1, -1), 'RIGHT'),
            ('FONTNAME', (2, inicio_totales), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, inicio_totales), (-1, -1), 10),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

        if presupuesto.metodo_pago_sugerido:
            story.append(Paragraph(f"<b>Medio de pago sugerido:</b> {presupuesto.metodo_pago_sugerido}", normal_style))
        if presupuesto.notas:
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"<b>Notas:</b> {presupuesto.notas}", normal_style))

        story.append(Spacer(1, 20))
        story.append(Paragraph("<i>Presupuesto sin validez fiscal. Precios sujetos a modificación.</i>", normal_style))

        doc.build(story)
        buffer.seek(0)
        return buffer

    @action(detail=True, methods=['get'], url_path='pdf', url_name='pdf')
    def pdf(self, request, pk=None):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        presupuesto = self.get_object()
        buffer = self._construir_pdf(presupuesto)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="presupuesto_{presupuesto.id}.pdf"'
        return response

    @action(detail=True, methods=['post'], url_path='enviar-email', url_name='enviar-email')
    def enviar_email(self, request, pk=None):
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        presupuesto = self.get_object()
        email = (request.data.get('email') or presupuesto.cliente.email or '').strip()
        if not email:
            return Response(
                {"error": "No hay un email de destino. Indicá uno o cargalo en la ficha del cliente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        buffer = self._construir_pdf(presupuesto)

        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings as dj_settings

        subject = f"[{presupuesto.tienda.nombre}] Presupuesto Nº {presupuesto.id}"
        texto = (
            f"Hola {presupuesto.cliente.nombre_razon_social},\n\n"
            f"Te enviamos el presupuesto Nº {presupuesto.id} generado por {presupuesto.tienda.nombre}.\n"
            f"Total: ${presupuesto.total}\n\n"
            "Adjuntamos el detalle en PDF."
        )
        html = f"""<!DOCTYPE html><html lang="es"><body>
<p>Hola {presupuesto.cliente.nombre_razon_social},</p>
<p>Te enviamos el presupuesto Nº <b>{presupuesto.id}</b> generado por <b>{presupuesto.tienda.nombre}</b>.</p>
<p>Total: <b>${presupuesto.total}</b></p>
<p>Adjuntamos el detalle en PDF.</p>
</body></html>"""

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=texto,
                from_email=getattr(dj_settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
                to=[email],
            )
            msg.attach_alternative(html, 'text/html')
            msg.attach(f'presupuesto_{presupuesto.id}.pdf', buffer.getvalue(), 'application/pdf')
            msg.send(fail_silently=False)
        except Exception as e:
            logger.error("Presupuesto.enviar_email: error enviando a %s: %s", email, e)
            return Response({"error": f"No se pudo enviar el email: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'ok': True, 'mensaje': f'Presupuesto enviado a {email}.'})


# ── Registro público + Suscripciones ─────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def planes_publicos(request):
    """Devuelve los 3 planes con sus límites y features (endpoint público)."""
    from .models import Plan
    # 'legacy' es un plan interno (asignado a mano desde Django Admin para eximir
    # a una tienda de límites), nunca se ofrece en el alta pública ni en upgrades.
    planes = Plan.objects.exclude(nombre='legacy').order_by('precio_mensual')
    data = [
        {
            'id': p.id,
            'nombre': p.nombre,
            'display': p.get_nombre_display(),
            'precio_mensual': str(p.precio_mensual),
            'max_productos': p.max_productos,
            'max_usuarios': p.max_usuarios,
            'permite_factura_electronica': p.permite_factura_electronica,
            'permite_integracion_ecommerce': p.permite_integracion_ecommerce,
        }
        for p in planes
    ]
    return Response(data)


class _RegistroError(Exception):
    """Envuelve una Response de error para poder validar y cortar temprano
    dentro de _crear_tienda_usuario_suscripcion sin duplicar el chequeo en
    cada llamador (alta pública, alta vía instalación de Tienda Nube, etc)."""
    def __init__(self, response):
        self.response = response


def _crear_tienda_usuario_suscripcion(data):
    """
    Valida y crea Tienda + User admin + Suscripcion 'pending', a partir del
    mismo payload que usa el alta pública.
    Body esperado: { nombre_tienda, email, username, password, plan, cuit,
                      mp_payer_email, telefono (opcional), logo (opcional) }
    Devuelve (tienda, user, plan). Lanza _RegistroError si algo no es válido.
    """
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError as DjangoValidationError
    from .models import Plan, Suscripcion
    from django.utils import timezone

    required = ['nombre_tienda', 'email', 'username', 'password', 'plan', 'cuit', 'mp_payer_email']
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise _RegistroError(Response({'error': f'Faltan campos: {", ".join(missing)}'}, status=400))

    nombre_tienda   = data['nombre_tienda'].strip()
    username        = data['username'].strip().lower()
    email           = data['email'].strip().lower()
    password        = data['password']
    plan_nombre     = data['plan'].lower()
    cuit            = data['cuit'].strip()
    mp_payer_email  = data['mp_payer_email'].strip().lower()
    logo            = (data.get('logo') or '').strip() or None

    cuit_limpio = re.sub(r'[^0-9]', '', cuit)
    if len(cuit_limpio) != 11:
        raise _RegistroError(Response({'error': 'El CUIT/CUIL debe tener 11 dígitos.'}, status=400))

    try:
        validate_email(mp_payer_email)
    except DjangoValidationError:
        raise _RegistroError(Response({'error': 'El email de Mercado Pago no es válido.'}, status=400))

    if logo and len(logo) > MAX_LOGO_BASE64_CHARS:
        raise _RegistroError(Response({'error': 'El logo es demasiado pesado. Probá con una imagen más chica.'}, status=400))

    if Tienda.objects.filter(nombre__iexact=nombre_tienda).exists():
        raise _RegistroError(Response({'error': 'Ya existe una tienda con ese nombre.'}, status=400))

    if User.objects.filter(username__iexact=username).exists():
        raise _RegistroError(Response({'error': 'Ese nombre de usuario ya está en uso.'}, status=400))

    if User.objects.filter(email__iexact=email).exists():
        raise _RegistroError(Response({'error': 'Ya existe una cuenta con ese email.'}, status=400))

    if plan_nombre == 'legacy':
        raise _RegistroError(Response({'error': f'Plan "{plan_nombre}" no existe.'}, status=400))

    try:
        plan = Plan.objects.get(nombre=plan_nombre)
    except Plan.DoesNotExist:
        raise _RegistroError(Response({'error': f'Plan "{plan_nombre}" no existe.'}, status=400))

    with transaction.atomic():
        tienda = Tienda.objects.create(
            nombre=nombre_tienda,
            email=email,
            telefono=data.get('telefono', ''),
            cuit=cuit,
            logo=logo,
        )
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=True,
            is_superuser=True,
            tienda=tienda,
        )
        Suscripcion.objects.create(
            tienda=tienda,
            plan=plan,
            estado='pending',
            fecha_inicio=timezone.now(),
            mp_payer_email=mp_payer_email,
        )

    return tienda, user, plan


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def verificar_cuit_disponible(request):
    """
    Chequeo informativo (no bloqueante) para el formulario de alta: indica si ya
    existe una tienda registrada con este CUIT, para poder avisarle al usuario
    que puede pedir que le unifiquen el acceso en vez de crear una cuenta suelta.

    No devuelve nombre de tienda ni ningún otro dato identificable: que dos CUITs
    coincidan no prueba que sea el mismo dueño, y el CUIT no es un dato secreto.
    """
    cuit_query = re.sub(r'[^0-9]', '', request.query_params.get('cuit', ''))
    if len(cuit_query) != 11:
        return Response({'existe': False})

    cuits_existentes = Tienda.objects.exclude(cuit__isnull=True).exclude(cuit='').values_list('cuit', flat=True)
    existe = any(re.sub(r'[^0-9]', '', c) == cuit_query for c in cuits_existentes)
    return Response({'existe': existe})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def registro_publico(request):
    """
    Crea una nueva tienda + usuario admin + suscripción en trial.
    Body: { nombre_tienda, email, username, password, telefono, plan (nombre) }
    Devuelve: { token_access, token_refresh, init_point (URL checkout MP) }
    """
    from .models import Suscripcion
    from rest_framework_simplejwt.tokens import RefreshToken
    from django.conf import settings as django_settings
    import urllib.parse

    try:
        tienda, user, plan = _crear_tienda_usuario_suscripcion(request.data)
    except _RegistroError as e:
        return e.response

    # Generar tokens JWT para que el usuario quede logueado
    refresh = RefreshToken.for_user(user)

    # Construir checkout URL del plan en MP
    # MP creará el preapproval individual y nos notificará vía webhook
    frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
    # Usamos la raíz "/" como back_url: MP agrega ?preapproval_id=XXX y el frontend
    # lo detecta en la raíz (que siempre carga) y redirige al componente de resultado.
    back_url = f"{frontend_url}/"
    init_point   = None

    if plan.mp_plan_id:
        backend_url = getattr(django_settings, 'BACKEND_URL', '').rstrip('/')
        params = {
            'preapproval_plan_id': plan.mp_plan_id,
            'back_url':            back_url,
            'external_reference':  str(tienda.id),  # UUID de la tienda; se recibe en el webhook
        }
        if backend_url:
            params['notification_url'] = f"{backend_url}/api/mp-webhook-suscripcion/"
        init_point = f"https://www.mercadopago.com.ar/subscriptions/checkout?{urllib.parse.urlencode(params)}"

    return Response({
        'token_access':  str(refresh.access_token),
        'token_refresh': str(refresh),
        'tienda_slug':   tienda.nombre,
        'username':      user.username,
        'init_point':    init_point,
        'trial_dias':    Suscripcion.DIAS_TRIAL,
        'plan':          plan.nombre,
    }, status=201)


def _registrar_webhook_tn(tienda, request):
    """
    Registra (o re-registra) el webhook order/paid en Tienda Nube para una
    tienda recién conectada. No interrumpe el flujo si falla — se puede
    reintentar a mano desde el panel.
    """
    from .services.tiendanube_service import TiendaNubeService
    try:
        tn = TiendaNubeService(tienda)
        if tienda.tn_webhook_id:
            tn.delete_webhook(tienda.tn_webhook_id)
        base = request.build_absolute_uri('/').rstrip('/')
        webhook_url = f"{base}/api/tiendas/{tienda.id}/tiendanube/webhook/"
        webhook_id = tn.register_webhook('order/paid', webhook_url)
        tienda.tn_webhook_id = webhook_id
        tienda.save(update_fields=['tn_webhook_id'])
        logger.info("Webhook TN auto-registrado tras instalación — tienda=%s id=%s", tienda.nombre, webhook_id)
    except Exception as e:
        logger.error("No se pudo auto-registrar el webhook TN para %s: %s", tienda.nombre, e)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def tn_instalar_iniciar(request):
    """
    Primer paso de una instalación de Total Stock iniciada desde la App Store
    de Tienda Nube: recibe el `code` que Tienda Nube manda por query string al
    autorizar, lo intercambia por un access_token, y:
      - Si ese store_id YA está conectado a una tienda existente de Total
        Stock (reinstalación), refresca el token y avisa que solo hace falta
        iniciar sesión.
      - Si es la primera vez, guarda el token en un registro temporal y
        devuelve un `instalacion_token` opaco para completar el alta (o
        vincularlo a una cuenta existente) en el siguiente paso.
    Body: { code }
    """
    from .models import InstalacionTiendaNubePendiente
    from .services.tiendanube_service import TiendaNubeService

    if not (settings.TIENDANUBE_APP_ID and settings.TIENDANUBE_CLIENT_SECRET):
        return Response({'error': 'La app de Tienda Nube no está configurada en el servidor.'}, status=400)

    code = request.data.get('code')
    if not code:
        return Response({'error': 'Falta el código de autorización.'}, status=400)

    try:
        access_token, store_id = TiendaNubeService.exchange_code_for_token(
            settings.TIENDANUBE_APP_ID, settings.TIENDANUBE_CLIENT_SECRET, code
        )
    except Exception as e:
        logger.error("Error intercambiando código TN (instalación): %s", e)
        return Response({'error': f'Error al obtener token: {e}'}, status=400)

    tienda_existente = Tienda.objects.filter(tn_store_id=store_id).first()
    if tienda_existente:
        tienda_existente.tn_access_token = access_token
        tienda_existente.tn_sync_habilitado = True
        tienda_existente.save(update_fields=['tn_access_token', 'tn_sync_habilitado'])
        _registrar_webhook_tn(tienda_existente, request)
        logger.info("Reinstalación de TN detectada — tienda=%s store_id=%s", tienda_existente.nombre, store_id)
        return Response({'ya_conectada': True})

    instalacion = InstalacionTiendaNubePendiente.objects.create(
        token=secrets.token_urlsafe(32),
        tn_store_id=store_id,
        tn_access_token=access_token,
    )
    return Response({'ya_conectada': False, 'instalacion_token': instalacion.token})


def _obtener_instalacion_pendiente(instalacion_token):
    """Devuelve el registro de InstalacionTiendaNubePendiente, o None si no existe/ya se usó."""
    from .models import InstalacionTiendaNubePendiente
    try:
        return InstalacionTiendaNubePendiente.objects.get(token=instalacion_token)
    except InstalacionTiendaNubePendiente.DoesNotExist:
        return None


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def tn_instalar_completar_registro(request):
    """
    Segundo paso (comerciante SIN cuenta previa): crea la cuenta de Total
    Stock igual que el alta pública, y de paso adjunta la conexión de Tienda
    Nube que quedó pendiente de `tn_instalar_iniciar`.
    Body: { instalacion_token, nombre_tienda, email, username, password, plan, cuit, telefono? }

    Importante: el token de instalación se valida (y recién se borra) DESPUÉS
    de crear la tienda con éxito, para que un error de validación normal del
    alta (usuario duplicado, etc.) no deje al comerciante sin forma de
    reintentar con el mismo token.
    """
    instalacion_token = request.data.get('instalacion_token')
    if not instalacion_token:
        return Response({'error': 'Falta instalacion_token.'}, status=400)

    instalacion = _obtener_instalacion_pendiente(instalacion_token)
    if not instalacion:
        return Response({'error': 'La instalación expiró o ya fue utilizada. Volvé a instalar desde Tienda Nube.'}, status=400)

    try:
        tienda, user, plan = _crear_tienda_usuario_suscripcion(request.data)
    except _RegistroError as e:
        return e.response

    tienda.tn_store_id = instalacion.tn_store_id
    tienda.tn_access_token = instalacion.tn_access_token
    tienda.tn_sync_habilitado = True
    tienda.save(update_fields=['tn_store_id', 'tn_access_token', 'tn_sync_habilitado'])
    instalacion.delete()
    _registrar_webhook_tn(tienda, request)

    from rest_framework_simplejwt.tokens import RefreshToken
    from django.conf import settings as django_settings
    from .models import Suscripcion
    import urllib.parse
    refresh = RefreshToken.for_user(user)

    # Mismo armado de checkout de MP que registro_publico, para que el
    # frontend pueda reusar exactamente la misma lógica post-alta.
    frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
    back_url = f"{frontend_url}/"
    init_point = None
    if plan.mp_plan_id:
        backend_url = getattr(django_settings, 'BACKEND_URL', '').rstrip('/')
        params = {
            'preapproval_plan_id': plan.mp_plan_id,
            'back_url':            back_url,
            'external_reference':  str(tienda.id),
        }
        if backend_url:
            params['notification_url'] = f"{backend_url}/api/mp-webhook-suscripcion/"
        init_point = f"https://www.mercadopago.com.ar/subscriptions/checkout?{urllib.parse.urlencode(params)}"

    return Response({
        'token_access':  str(refresh.access_token),
        'token_refresh': str(refresh),
        'tienda_slug':   tienda.nombre,
        'username':      user.username,
        'init_point':    init_point,
        'trial_dias':    Suscripcion.DIAS_TRIAL,
        'plan':          plan.nombre,
    }, status=201)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def tn_instalar_vincular_cuenta_existente(request):
    """
    Segundo paso (comerciante que YA tiene cuenta de Total Stock): adjunta la
    conexión de Tienda Nube pendiente a la tienda del usuario ya logueado.
    Body: { instalacion_token, tienda_slug? }
    """
    instalacion_token = request.data.get('instalacion_token')
    if not instalacion_token:
        return Response({'error': 'Falta instalacion_token.'}, status=400)

    instalacion = _obtener_instalacion_pendiente(instalacion_token)
    if not instalacion:
        return Response({'error': 'La instalación expiró o ya fue utilizada. Volvé a instalar desde Tienda Nube.'}, status=400)

    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'El usuario no tiene tienda asignada.'}, status=400)

    tienda.tn_store_id = instalacion.tn_store_id
    tienda.tn_access_token = instalacion.tn_access_token
    tienda.tn_sync_habilitado = True
    tienda.save(update_fields=['tn_store_id', 'tn_access_token', 'tn_sync_habilitado'])
    instalacion.delete()
    _registrar_webhook_tn(tienda, request)

    return Response({'success': True, 'tienda_slug': tienda.nombre})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def mp_webhook_suscripcion(request):
    """
    Webhook de Mercado Pago para eventos de suscripción (preaprobaciones).
    MP envía POST con { type, data: { id } }.

    Flujo con planes de MP:
      - subscription_preapproval: nueva suscripción o cambio de estado.
        Si no conocemos el preapproval_id, buscamos la tienda por external_reference
        (UUID de tienda, pasado en la URL de checkout) y guardamos el id.
      - subscription_authorized_payment: cobro exitoso. Buscamos por preapproval_id
        dentro de los datos del pago.
    """
    import hashlib
    import hmac
    from django.conf import settings as dj_settings
    from .models import Suscripcion
    from .services.suscripcion_service import (
        activar_suscripcion, renovar_suscripcion,
        cancelar_suscripcion, pausar_suscripcion,
        iniciar_periodo_gracia, obtener_preaprobacion,
    )

    # Validar firma de MP si la clave secreta está configurada
    webhook_secret = getattr(dj_settings, 'MP_WEBHOOK_SECRET', '')
    if webhook_secret:
        x_signature   = request.headers.get('x-signature', '')
        x_request_id  = request.headers.get('x-request-id', '')
        # x-signature tiene formato: ts=<timestamp>,v1=<hash>
        ts = v1 = ''
        for part in x_signature.split(','):
            if part.startswith('ts='):
                ts = part[3:]
            elif part.startswith('v1='):
                v1 = part[3:]
        if ts and v1:
            data_id = str(request.data.get('data', {}).get('id', ''))
            manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"
            expected = hmac.new(
                webhook_secret.encode(),
                manifest.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, v1):
                # Firma inválida: puede ser el test del panel de MP (usa datos ficticios)
                # o un intento no autorizado. En ambos casos devolvemos 200 para que MP
                # no reintente, pero no procesamos el payload.
                logger.warning("Webhook MP: firma inválida, payload ignorado (id=%s)", data_id)
                return Response(status=200)

    payload    = request.data
    event_type = payload.get('type', '')
    resource_id = str(payload.get('data', {}).get('id', '')).strip()

    logger.info("Webhook MP suscripción: type=%s id=%s", event_type, resource_id)

    if not resource_id:
        return Response(status=200)

    # ── subscription_preapproval ──────────────────────────────────────────────
    if event_type == 'subscription_preapproval':

        # Intentar consultar el estado real en MP (necesario para external_reference)
        try:
            datos_mp = obtener_preaprobacion(resource_id)
        except Exception as e:
            logger.error("Error consultando preaprobación %s: %s", resource_id, e)
            return Response(status=200)

        estado_mp      = datos_mp.get('status', '')
        external_ref   = datos_mp.get('external_reference', '')
        payer_email    = datos_mp.get('payer_email', '') or datos_mp.get('payer', {}).get('email', '')

        # Buscar suscripción: 1) por preapproval_id, 2) por UUID en external_reference,
        # 3) por payer_email (cuando external_reference es texto del plan, no UUID)
        import uuid as _uuid
        suscripcion = None

        try:
            suscripcion = Suscripcion.objects.select_related('plan').get(
                mp_preapproval_id=resource_id
            )
        except Suscripcion.DoesNotExist:
            pass

        if suscripcion is None and external_ref:
            try:
                _uuid.UUID(external_ref)   # valida que sea un UUID real
                suscripcion = Suscripcion.objects.select_related('plan').get(
                    tienda__id=external_ref
                )
            except (ValueError, Suscripcion.DoesNotExist):
                pass

        if suscripcion is None and payer_email:
            try:
                user_obj = User.objects.filter(
                    email__iexact=payer_email
                ).select_related('tienda').first()
                if user_obj and hasattr(user_obj, 'tienda') and user_obj.tienda:
                    suscripcion = Suscripcion.objects.select_related('plan').get(
                        tienda=user_obj.tienda
                    )
            except Suscripcion.DoesNotExist:
                pass

        if suscripcion is None:
            logger.warning(
                "Webhook MP: no se encontró suscripción (preapproval=%s, ref=%s, email=%s)",
                resource_id, external_ref, payer_email,
            )
            return Response(status=200)

        # Vincular/actualizar preapproval_id (también para re-suscripción tras cancelación)
        if suscripcion.mp_preapproval_id != resource_id:
            suscripcion.mp_preapproval_id = resource_id
            suscripcion.mp_payer_email = payer_email or suscripcion.mp_payer_email
            suscripcion.save(update_fields=['mp_preapproval_id', 'mp_payer_email'])
            logger.info("Preapproval %s vinculado/actualizado a tienda %s", resource_id, suscripcion.tienda_id)

        # Aplicar cambio de estado según MP
        if estado_mp == 'authorized':
            if suscripcion.estado in ('pending', 'cancelada'):
                # Primera suscripción o re-suscripción tras cancelación: iniciar trial
                activar_suscripcion(suscripcion)
            elif suscripcion.estado in ('trial', 'activa', 'gracia', 'pausada'):
                # MP confirmó renovación o reactivación → activa
                renovar_suscripcion(suscripcion)
        elif estado_mp == 'paused':
            # MP no pudo cobrar → iniciar gracia (5 días antes de suspender)
            iniciar_periodo_gracia(suscripcion)
        elif estado_mp == 'cancelled':
            cancelar_suscripcion(suscripcion)

    # ── subscription_authorized_payment ──────────────────────────────────────
    elif event_type == 'subscription_authorized_payment':
        # resource_id es el ID del pago autorizado, no del preapproval.
        # Buscamos el preapproval_id dentro de los datos del pago.
        try:
            from .services.suscripcion_service import _headers, MP_API_BASE
            import requests as req_lib
            pago_resp = req_lib.get(
                f"{MP_API_BASE}/authorized_payments/{resource_id}",
                headers=_headers(),
                timeout=10,
            )
            pago_resp.raise_for_status()
            preapproval_id = pago_resp.json().get('preapproval_id', '')
        except Exception as e:
            logger.error("Error obteniendo authorized_payment %s: %s", resource_id, e)
            return Response(status=200)

        if not preapproval_id:
            return Response(status=200)

        try:
            suscripcion = Suscripcion.objects.get(mp_preapproval_id=preapproval_id)
        except Suscripcion.DoesNotExist:
            return Response(status=200)

        # Cobro exitoso → renovar suscripción (trial o gracia → activa, próximo cobro día 10)
        from .services.suscripcion_service import renovar_suscripcion as _renovar
        _renovar(suscripcion)
        logger.info("Suscripción renovada por authorized_payment: %s", suscripcion.id)

    return Response(status=200)


MAX_LOGO_BASE64_CHARS = 700_000  # ~500KB decodificado, de sobra para un logo ya redimensionado chico


@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def actualizar_datos_tienda(request):
    """
    Permite a un usuario de la tienda (o superuser/staff operando sobre una
    tienda autorizada) modificar el nombre visible y el logo de su tienda
    desde el Panel de Administración.
    Body: { tienda_slug, nombre?: str, logo?: str|null }  (logo: data URI base64, o null/'' para quitarlo)
    """
    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'No se encontró la tienda.'}, status=400)

    campos_actualizados = []

    if 'nombre' in request.data:
        nuevo_nombre = (request.data.get('nombre') or '').strip()
        if not nuevo_nombre:
            return Response({'error': 'El nombre de la tienda no puede estar vacío.'}, status=400)
        if Tienda.objects.exclude(pk=tienda.pk).filter(nombre__iexact=nuevo_nombre).exists():
            return Response({'error': 'Ya existe una tienda con ese nombre.'}, status=400)
        tienda.nombre = nuevo_nombre
        campos_actualizados.append('nombre')

    if 'logo' in request.data:
        logo = request.data.get('logo') or None
        if logo and len(logo) > MAX_LOGO_BASE64_CHARS:
            return Response({'error': 'El logo es demasiado pesado. Probá con una imagen más chica.'}, status=400)
        tienda.logo = logo
        campos_actualizados.append('logo')

    if 'descuento_efectivo_porcentaje' in request.data:
        valor = request.data.get('descuento_efectivo_porcentaje')
        if valor is None or str(valor).strip() == '':
            tienda.descuento_efectivo_porcentaje = None
        else:
            try:
                from decimal import Decimal, InvalidOperation
                pct = Decimal(str(valor))
            except InvalidOperation:
                return Response({'error': 'El % de descuento en efectivo debe ser numérico.'}, status=400)
            if pct < 0 or pct > 100:
                return Response({'error': 'El % de descuento en efectivo debe estar entre 0 y 100.'}, status=400)
            tienda.descuento_efectivo_porcentaje = pct
        campos_actualizados.append('descuento_efectivo_porcentaje')

    if 'descuento_efectivo_redondeo' in request.data:
        valores_validos = dict(Tienda.DESCUENTO_EFECTIVO_REDONDEO_CHOICES)
        redondeo = request.data.get('descuento_efectivo_redondeo') or ''
        if redondeo not in valores_validos:
            return Response({'error': 'Redondeo inválido.'}, status=400)
        tienda.descuento_efectivo_redondeo = redondeo
        campos_actualizados.append('descuento_efectivo_redondeo')

    if campos_actualizados:
        tienda.save(update_fields=campos_actualizados)

    return Response({
        'nombre': tienda.nombre,
        'logo': tienda.logo,
        'descuento_efectivo_porcentaje': tienda.descuento_efectivo_porcentaje,
        'descuento_efectivo_redondeo': tienda.descuento_efectivo_redondeo,
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def regenerar_widget_token(request):
    """
    Genera (o regenera) el token de solo lectura para el widget de ventas del
    día (iPhone / Scriptable). Regenerar invalida cualquier token anterior: el
    widget ya instalado con el token viejo deja de funcionar hasta que se
    actualice con el nuevo. Body: { tienda_slug }.
    """
    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'No se encontró la tienda.'}, status=400)

    tienda.widget_token = secrets.token_urlsafe(32)
    tienda.save(update_fields=['widget_token'])

    return Response({'widget_token': tienda.widget_token})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def mi_suscripcion(request):
    """Devuelve el estado del plan de la tienda del usuario autenticado."""
    from .plan_enforcement import info_suscripcion
    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'El usuario no tiene tienda asignada.'}, status=400)
    return Response(info_suscripcion(tienda))


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def verificar_suscripcion_mp(request):
    """
    Llamado desde /suscripcion/resultado al volver de MP con ?preapproval_id=xxx.
    Consulta el estado en MP, activa la suscripción si está autorizada,
    y devuelve { estado, activa, username } para que el frontend pueda redirigir.
    """
    from .models import Suscripcion
    from .services.suscripcion_service import (
        obtener_preaprobacion, activar_suscripcion,
    )

    preapproval_id = request.query_params.get('preapproval_id', '').strip()
    if not preapproval_id:
        return Response({'error': 'preapproval_id requerido'}, status=400)

    try:
        datos_mp = obtener_preaprobacion(preapproval_id)
    except Exception as e:
        logger.error("verificar_suscripcion_mp: error consultando MP %s: %s", preapproval_id, e)
        return Response({'estado': 'error_mp', 'activa': False})

    estado_mp    = datos_mp.get('status', '')
    external_ref = datos_mp.get('external_reference', '')
    payer_email  = datos_mp.get('payer_email', '') or datos_mp.get('payer', {}).get('email', '')

    # Buscar suscripción: 1) por preapproval_id, 2) UUID en external_reference,
    # 3) payer_email (cuando external_reference es el nombre del plan, no UUID)
    import uuid as _uuid
    suscripcion = None

    try:
        suscripcion = Suscripcion.objects.select_related('tienda').get(
            mp_preapproval_id=preapproval_id
        )
    except Suscripcion.DoesNotExist:
        pass

    if suscripcion is None and external_ref:
        try:
            _uuid.UUID(external_ref)
            suscripcion = Suscripcion.objects.select_related('tienda').get(
                tienda__id=external_ref
            )
        except (ValueError, Suscripcion.DoesNotExist):
            pass

    if suscripcion is None and payer_email:
        try:
            user_obj = User.objects.filter(
                email__iexact=payer_email
            ).select_related('tienda').first()
            if user_obj and hasattr(user_obj, 'tienda') and user_obj.tienda:
                suscripcion = Suscripcion.objects.select_related('tienda').get(
                    tienda=user_obj.tienda
                )
        except Suscripcion.DoesNotExist:
            pass

    if suscripcion is None:
        return Response({'estado': 'no_encontrada', 'activa': False})

    # Vincular/actualizar preapproval_id (también para re-suscripción tras cancelación)
    if suscripcion.mp_preapproval_id != preapproval_id:
        suscripcion.mp_preapproval_id = preapproval_id
        if payer_email:
            suscripcion.mp_payer_email = payer_email
        suscripcion.save(update_fields=['mp_preapproval_id', 'mp_payer_email'])

    # Activar si MP dice autorizado
    if estado_mp == 'authorized' and suscripcion.estado in ('pending', 'trial', 'pausada', 'cancelada'):
        activar_suscripcion(suscripcion)
        suscripcion.refresh_from_db()

    # Devolver username para que el frontend sepa con qué cuenta loguearse
    try:
        admin_user = suscripcion.tienda.usuarios.filter(is_superuser=True).first()
        username = admin_user.username if admin_user else ''
    except Exception:
        username = ''

    return Response({
        'estado':   suscripcion.estado,
        'activa':   suscripcion.esta_activa,
        'username': username,
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verificar_pago_pendiente(request):
    """
    Endpoint autenticado: el usuario bloqueado en la pantalla de suscripción
    pendiente pulsa "Ya pagué — Verificar".
    Si mp_preapproval_id es NULL (webhook nunca llegó / SPA no cargó tras el pago),
    busca el preapproval en MP usando el email del usuario.
    """
    import requests as req_lib
    from django.conf import settings as django_settings
    from .models import Suscripcion, Plan
    from .services.suscripcion_service import (
        obtener_preaprobacion, activar_suscripcion,
    )

    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'El usuario no tiene tienda asignada.'}, status=400)

    try:
        suscripcion = Suscripcion.objects.select_related('tienda', 'plan').get(tienda=tienda)
    except Suscripcion.DoesNotExist:
        return Response({'error': 'No se encontró suscripción para esta tienda.'}, status=404)

    if suscripcion.esta_activa:
        return Response({'estado': suscripcion.estado, 'activa': True})

    # Preapprovals ya vinculados a OTRAS tiendas: se excluyen de la búsqueda por plan+email
    # de más abajo. Sin esto, a medida que se suman tiendas al mismo plan, cada vez hay más
    # candidatos "authorized" ambiguos y el fallback de "único candidato" deja de servir.
    ids_ya_vinculados = set(
        Suscripcion.objects.exclude(pk=suscripcion.pk)
        .exclude(mp_preapproval_id__isnull=True).exclude(mp_preapproval_id='')
        .values_list('mp_preapproval_id', flat=True)
    )

    # Aceptar preapproval_id directo desde el frontend (viene de la URL de MP)
    preapproval_id_directo = (request.data.get('preapproval_id') or '').strip()
    preapproval_id = suscripcion.mp_preapproval_id or preapproval_id_directo

    logger.info(
        "verificar_pago_pendiente: user=%s email=%s preapproval_db=%s preapproval_body=%s",
        request.user.username, request.user.email,
        suscripcion.mp_preapproval_id, preapproval_id_directo,
    )

    # ── Si tenemos preapproval_id directo, usarlo primero ────────────────────
    if preapproval_id_directo and not suscripcion.mp_preapproval_id:
        token_mp = getattr(django_settings, 'MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
        if token_mp:
            headers = {'Authorization': f'Bearer {token_mp}', 'Content-Type': 'application/json'}
            try:
                det = req_lib.get(
                    f'https://api.mercadopago.com/preapproval/{preapproval_id_directo}',
                    headers=headers, timeout=15,
                )
                det.raise_for_status()
                datos_mp = det.json()
                pa_email = (
                    datos_mp.get('payer_email', '')
                    or datos_mp.get('payer', {}).get('email', '')
                )
                logger.info(
                    "verificar_pago_pendiente: preapproval directo %s status=%s payer=%s",
                    preapproval_id_directo, datos_mp.get('status'), pa_email,
                )
                fields = ['mp_preapproval_id']
                suscripcion.mp_preapproval_id = preapproval_id_directo
                if pa_email and not suscripcion.mp_payer_email:
                    suscripcion.mp_payer_email = pa_email
                    fields.append('mp_payer_email')
                suscripcion.save(update_fields=fields)

                estado_mp = datos_mp.get('status', '')
                if estado_mp == 'authorized' and suscripcion.estado in ('pending', 'trial', 'pausada', 'gracia', 'cancelada'):
                    activar_suscripcion(suscripcion)
                    suscripcion.refresh_from_db()
                    return Response({'estado': suscripcion.estado, 'activa': True,
                                     'mensaje': '¡Suscripción activada! Ingresando al sistema...'})
                return Response({
                    'estado': suscripcion.estado, 'activa': False, 'estado_mp': estado_mp,
                    'mensaje': 'Tu pago aún está siendo procesado por Mercado Pago. Puede demorar unos minutos.',
                })
            except Exception as e:
                logger.warning("verificar_pago_pendiente: error con preapproval directo %s: %s", preapproval_id_directo, e)

    # ── Si no tenemos preapproval_id, buscarlo en MP por plan + email ────────
    if not preapproval_id:
        token_mp = getattr(django_settings, 'MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
        payer_email = request.user.email or ''
        mp_plan_id  = suscripcion.plan.mp_plan_id if suscripcion.plan else ''

        logger.info(
            "verificar_pago_pendiente: buscando en MP plan=%s email=%s",
            mp_plan_id, payer_email,
        )

        if not token_mp or not mp_plan_id:
            return Response({'estado': suscripcion.estado, 'activa': False,
                             'mensaje': 'No encontramos tu pago aún. Si ya pagaste, esperá unos minutos y reintentá.'})

        headers = {'Authorization': f'Bearer {token_mp}', 'Content-Type': 'application/json'}
        encontrado = None
        candidatos_authorized = []

        try:
            r = req_lib.get(
                'https://api.mercadopago.com/preapproval/search',
                params={'preapproval_plan_id': mp_plan_id, 'limit': 100},
                headers=headers, timeout=15,
            )
            r.raise_for_status()
            resultados = r.json().get('results', [])
            logger.info("verificar_pago_pendiente: MP devolvió %d preapprovals", len(resultados))

            for pa in resultados:
                if pa.get('status') != 'authorized':
                    continue
                if str(pa.get('id', '')) in ids_ya_vinculados:
                    logger.info(
                        "verificar_pago_pendiente: candidato %s descartado (ya vinculado a otra tienda)",
                        pa.get('id'),
                    )
                    continue
                # GET individual para obtener payer_email completo
                try:
                    det = req_lib.get(
                        f"https://api.mercadopago.com/preapproval/{pa['id']}",
                        headers=headers, timeout=15,
                    )
                    if not det.ok:
                        continue
                    det_data = det.json()
                    det_email = (
                        det_data.get('payer_email', '')
                        or det_data.get('payer', {}).get('email', '')
                    )
                    det_external_ref = str(det_data.get('external_reference', ''))
                    logger.info(
                        "verificar_pago_pendiente: candidato %s payer=%s external_ref=%s",
                        pa['id'], det_email, det_external_ref,
                    )
                    candidatos_authorized.append(det_data)
                    # Prioridad: external_reference (UUID de la tienda, sin ambigüedad posible)
                    # por sobre el email, que puede no coincidir con el login de Total Stock
                    # aunque sea la persona correcta pagando.
                    if det_external_ref == str(tienda.id):
                        encontrado = det_data
                        break
                    if payer_email and det_email.lower() == payer_email.lower():
                        encontrado = det_data
                        break
                except Exception:
                    pass
        except Exception as e:
            logger.warning("verificar_pago_pendiente: búsqueda MP falló: %s", e)

        # Fallback: si hay solo un preapproval authorized y no matcheó email, usarlo igual
        if not encontrado and len(candidatos_authorized) == 1:
            encontrado = candidatos_authorized[0]
            logger.info(
                "verificar_pago_pendiente: usando único candidato authorized %s (email no matcheó)",
                encontrado.get('id'),
            )

        if encontrado:
            preapproval_id = str(encontrado.get('id', ''))
            pa_email = (
                encontrado.get('payer_email', '')
                or encontrado.get('payer', {}).get('email', '')
            )
            fields = []
            if preapproval_id and suscripcion.mp_preapproval_id != preapproval_id:
                suscripcion.mp_preapproval_id = preapproval_id
                fields.append('mp_preapproval_id')
            if pa_email and not suscripcion.mp_payer_email:
                suscripcion.mp_payer_email = pa_email
                fields.append('mp_payer_email')
            if fields:
                suscripcion.save(update_fields=fields)
            datos_mp = encontrado
        else:
            return Response({'estado': suscripcion.estado, 'activa': False,
                             'mensaje': 'No encontramos tu pago en Mercado Pago. Si ya pagaste, esperá unos minutos y reintentá.'})
    else:
        try:
            datos_mp = obtener_preaprobacion(preapproval_id)
        except Exception as e:
            logger.error("verificar_pago_pendiente: error consultando MP %s: %s", preapproval_id, e)
            return Response({'estado': 'error_mp', 'activa': False,
                             'mensaje': 'No pudimos consultar Mercado Pago. Intentá de nuevo en unos minutos.'})

        # Si el preapproval almacenado está cancelado en MP y la suscripción
        # también está cancelada, puede haber una re-suscripción nueva. Limpiamos
        # el ID viejo y caemos al bloque de búsqueda por plan_id.
        if datos_mp.get('status') == 'cancelled' and suscripcion.estado == 'cancelada':
            logger.info(
                "verificar_pago_pendiente: preapproval_db %s está cancelled en MP — "
                "limpiando y buscando re-suscripción por plan",
                preapproval_id,
            )
            suscripcion.mp_preapproval_id = None
            suscripcion.save(update_fields=['mp_preapproval_id'])
            datos_mp = None   # forzar búsqueda abajo

    # Búsqueda de re-suscripción cuando el preapproval_db estaba cancelado
    if datos_mp is None:
        token_mp = getattr(django_settings, 'MP_ACCESS_TOKEN_SUSCRIPCIONES', '')
        mp_plan_id = suscripcion.plan.mp_plan_id if suscripcion.plan else ''
        payer_email = request.user.email or ''
        if not token_mp or not mp_plan_id:
            return Response({'estado': suscripcion.estado, 'activa': False,
                             'mensaje': 'No encontramos tu pago aún. Si ya pagaste, esperá unos minutos y reintentá.'})
        headers_mp = {'Authorization': f'Bearer {token_mp}', 'Content-Type': 'application/json'}
        candidatos = []
        try:
            r2 = req_lib.get(
                'https://api.mercadopago.com/preapproval/search',
                params={'preapproval_plan_id': mp_plan_id, 'limit': 100},
                headers=headers_mp, timeout=15,
            )
            r2.raise_for_status()
            for pa in r2.json().get('results', []):
                if pa.get('status') != 'authorized':
                    continue
                if str(pa.get('id', '')) in ids_ya_vinculados:
                    logger.info(
                        "verificar_pago_pendiente: candidato re-sub %s descartado (ya vinculado a otra tienda)",
                        pa.get('id'),
                    )
                    continue
                try:
                    det = req_lib.get(f"https://api.mercadopago.com/preapproval/{pa['id']}",
                                      headers=headers_mp, timeout=15)
                    if det.ok:
                        det_data = det.json()
                        det_email = det_data.get('payer_email', '') or det_data.get('payer', {}).get('email', '')
                        det_external_ref = str(det_data.get('external_reference', ''))
                        logger.info(
                            "verificar_pago_pendiente: candidato re-sub %s payer=%s external_ref=%s",
                            pa['id'], det_email, det_external_ref,
                        )
                        candidatos.append(det_data)
                        if det_external_ref == str(tienda.id):
                            datos_mp = det_data
                            break
                        if payer_email and det_email.lower() == payer_email.lower():
                            datos_mp = det_data
                            break
                except Exception:
                    pass
        except Exception as e:
            logger.warning("verificar_pago_pendiente: búsqueda re-sub falló: %s", e)

        if datos_mp is None and len(candidatos) == 1:
            datos_mp = candidatos[0]
            logger.info("verificar_pago_pendiente: usando único candidato re-sub %s", datos_mp.get('id'))

        if datos_mp is None:
            return Response({'estado': suscripcion.estado, 'activa': False,
                             'mensaje': 'No encontramos una nueva suscripción activa en Mercado Pago. '
                                        'Si ya te re-suscribiste, esperá unos minutos y reintentá.'})

    estado_mp = datos_mp.get('status', '')

    if estado_mp == 'authorized' and suscripcion.estado in ('pending', 'trial', 'pausada', 'gracia', 'cancelada'):
        new_preapproval_id = str(datos_mp.get('id', ''))
        if new_preapproval_id and suscripcion.mp_preapproval_id != new_preapproval_id:
            suscripcion.mp_preapproval_id = new_preapproval_id
            suscripcion.save(update_fields=['mp_preapproval_id'])
        activar_suscripcion(suscripcion)
        suscripcion.refresh_from_db()
        return Response({'estado': suscripcion.estado, 'activa': True,
                         'mensaje': '¡Suscripción activada! Ingresando al sistema...'})

    return Response({
        'estado': suscripcion.estado,
        'activa': False,
        'estado_mp': estado_mp,
        'mensaje': 'Tu pago aún está siendo procesado por Mercado Pago. Puede demorar unos minutos.',
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancelar_suscripcion_view(request):
    """
    Baja iniciada por el usuario desde el panel "Mi Plan".
    Cancela la preaprobación en MP y marca la suscripción como cancelada.
    Los datos permanecen 30 días antes del borrado automático.
    """
    from .models import Suscripcion
    from .services.suscripcion_service import (
        cancelar_preaprobacion_mp, cancelar_suscripcion,
    )

    tienda = _resolver_tienda_por_slug(request)
    try:
        suscripcion = tienda.suscripcion
    except (AttributeError, Suscripcion.DoesNotExist):
        return Response({'error': 'No se encontró suscripción activa.'}, status=404)

    if suscripcion.estado == 'cancelada':
        return Response({'error': 'La suscripción ya está cancelada.'}, status=400)

    # Cancelar primero en MP para que no siga cobrando
    if suscripcion.mp_preapproval_id:
        try:
            cancelar_preaprobacion_mp(suscripcion.mp_preapproval_id)
        except Exception as e:
            logger.error("Error cancelando en MP para suscripción %s: %s", suscripcion.id, e)
            return Response(
                {'error': 'No se pudo cancelar en Mercado Pago. Intentá nuevamente.'},
                status=502,
            )

    cancelar_suscripcion(suscripcion)
    logger.info(
        "Baja iniciada por usuario %s — tienda %s",
        request.user.username, tienda.nombre
    )
    return Response({
        'ok': True,
        'mensaje': 'Tu suscripción fue cancelada. Tus datos estarán disponibles por 30 días.',
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cambiar_plan(request):
    """
    Upgrade/downgrade de plan, o alta de un plan pago para una tienda Legacy
    (con o sin registro de Suscripcion todavía — una tienda legacy "por ausencia"
    de Suscripcion no tiene ninguna hasta que elige su primer plan acá).
    Cancela el preapproval anterior en MP (si había) y devuelve el checkout URL
    del nuevo plan para que el usuario complete la suscripción.
    Body: { plan: 'starter' | 'pro' | 'advanced', cuit?: str }
    El CUIT/CUIL es obligatorio: si la tienda todavía no tiene uno cargado, debe
    venir en el body (se guarda en la tienda antes de continuar).
    """
    import urllib.parse
    from django.conf import settings as dj_settings
    from .models import Plan, Suscripcion
    from .services.suscripcion_service import cancelar_preaprobacion_mp

    user = request.user
    tienda = _resolver_tienda_por_slug(request)
    if not tienda:
        return Response({'error': 'El usuario no tiene tienda asignada.'}, status=400)

    if not tienda.cuit or not tienda.cuit.strip():
        cuit_input = (request.data.get('cuit') or '').strip()
        if not cuit_input:
            return Response(
                {'error': 'Necesitamos el CUIT/CUIL de tu tienda para suscribirte.', 'requiere_cuit': True},
                status=400,
            )
        cuit_limpio = re.sub(r'[^0-9]', '', cuit_input)
        if len(cuit_limpio) != 11:
            return Response(
                {'error': 'El CUIT/CUIL debe tener 11 dígitos.', 'requiere_cuit': True},
                status=400,
            )
        tienda.cuit = cuit_input
        tienda.save(update_fields=['cuit'])

    plan_nombre = request.data.get('plan', '').lower()
    if plan_nombre == 'legacy':
        return Response({'error': f'Plan "{plan_nombre}" no existe.'}, status=400)
    try:
        plan_nuevo = Plan.objects.get(nombre=plan_nombre)
    except Plan.DoesNotExist:
        return Response({'error': f'Plan "{plan_nombre}" no existe.'}, status=400)

    try:
        suscripcion = tienda.suscripcion
    except Suscripcion.DoesNotExist:
        suscripcion = None

    if suscripcion is None:
        # Tienda legacy sin ningún registro de Suscripcion: se crea uno nuevo
        # apuntando directo al plan elegido, listo para completar el checkout.
        suscripcion = Suscripcion.objects.create(tienda=tienda, plan=plan_nuevo, estado='pending')
        logger.info(
            "Suscripción creada para tienda legacy %s → plan %s",
            tienda.nombre, plan_nuevo.nombre,
        )
    else:
        es_legacy_con_registro = suscripcion.plan.nombre == 'legacy'
        # Para re-suscripción desde estado cancelada, o desde 'pending' (el
        # usuario eligió el plan pero nunca completó el pago en MP y necesita
        # volver al checkout), o alta desde legacy con Suscripcion ya existente,
        # se permite elegir el mismo plan.
        if (
            plan_nuevo == suscripcion.plan
            and suscripcion.estado not in ('cancelada', 'pending')
            and not es_legacy_con_registro
        ):
            return Response({'error': 'Ya estás en ese plan.'}, status=400)

        # Cancelar preapproval anterior en MP para evitar cobro doble
        if suscripcion.mp_preapproval_id:
            try:
                cancelar_preaprobacion_mp(suscripcion.mp_preapproval_id)
                logger.info(
                    "Preapproval %s cancelado por upgrade de plan (%s → %s) — tienda %s",
                    suscripcion.mp_preapproval_id, suscripcion.plan.nombre,
                    plan_nuevo.nombre, tienda.nombre,
                )
            except Exception as e:
                logger.error("Error cancelando preapproval anterior en MP: %s", e)
                # Continuamos igual: el usuario debe poder hacer upgrade aunque falle la cancelación en MP

        # Actualizar plan y resetear estado para que el usuario complete el nuevo checkout
        suscripcion.plan = plan_nuevo
        suscripcion.estado = 'pending'
        suscripcion.mp_preapproval_id = None
        suscripcion.mp_payer_email = None
        suscripcion.fecha_proximo_cobro = None
        suscripcion.fecha_inicio_gracia = None
        suscripcion.save(update_fields=[
            'plan', 'estado', 'mp_preapproval_id', 'mp_payer_email',
            'fecha_proximo_cobro', 'fecha_inicio_gracia',
        ])

    # Construir checkout URL del nuevo plan
    checkout_url = None
    if plan_nuevo.mp_plan_id:
        frontend_url = getattr(dj_settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        backend_url  = getattr(dj_settings, 'BACKEND_URL', '').rstrip('/')
        params = {
            'preapproval_plan_id': plan_nuevo.mp_plan_id,
            'back_url':            f"{frontend_url}/",
            'external_reference':  str(tienda.id),
        }
        if backend_url:
            params['notification_url'] = f"{backend_url}/api/mp-webhook-suscripcion/"
        checkout_url = f"https://www.mercadopago.com.ar/subscriptions/checkout?{urllib.parse.urlencode(params)}"

    return Response({
        'mensaje':      f'Redirigiendo al checkout de Mercado Pago para el plan {plan_nuevo.get_nombre_display()}.',
        'plan':         plan_nuevo.nombre,
        'checkout_url': checkout_url,
    })


# ── Recupero de contraseña ────────────────────────────────────────────────────

@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def update_email(request):
    """
    Guarda o actualiza el email del usuario autenticado.
    Sólo relevante para administradores de tienda (is_superuser).
    Body: { email }
    """
    import re as _re
    email = (request.data.get('email') or '').strip().lower()

    if not email:
        return Response({'error': 'Email requerido.'}, status=400)

    if not _re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return Response({'error': 'Formato de email inválido.'}, status=400)

    from django.contrib.auth import get_user_model
    UserModel = get_user_model()

    if UserModel.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
        return Response({'error': 'Ese email ya está registrado en otra cuenta.'}, status=400)

    request.user.email = email
    request.user.save(update_fields=['email'])
    logger.info("update_email: usuario %s actualizó su email a %s", request.user.username, email)

    # El frontend arma `user` decodificando el JWT, no lo vuelve a leer de la DB
    # entre logins (el refresh token silencioso solo copia los claims del token
    # viejo). Sin reemitir el par de tokens acá, el email quedaba "congelado" en
    # el valor vacío del login original y el modal de "registrá tu email"
    # volvía a aparecer en la siguiente sesión aunque ya estuviera guardado.
    refresh = CustomTokenObtainPairSerializer.get_token(request.user)
    return Response({
        'ok': True,
        'email': email,
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, permissions.IsAdminUser])
def enviar_comunicado(request):
    """
    Envío manual de un comunicado por email a una lista de destinatarios. Es una
    herramienta administrativa genérica (solo superuser) para anuncios de producto
    puntuales -- el contenido (subject/text/html) lo arma quien lo llama, acá solo
    se resuelve el envío por SMTP reusando la configuración ya existente.

    Body: {
        emails: [str, ...],
        subject: str, text: str, html: str,
        imagen_base64: str (opcional, PNG en base64, se referencia en el html como
            src="cid:<imagen_cid>"),
        imagen_cid: str (opcional, default 'imagen1'),
        dry_run: bool (opcional, default false -- solo normaliza y cuenta destinatarios)
    }
    """
    if not request.user.is_superuser:
        return Response({'error': 'Solo superusuarios pueden enviar comunicados.'}, status=403)

    emails = request.data.get('emails') or []
    emails = sorted({str(e).strip().lower() for e in emails if e and '@' in str(e)})
    dry_run = bool(request.data.get('dry_run', False))

    if dry_run:
        return Response({'destinatarios': emails, 'total': len(emails)})

    subject = request.data.get('subject')
    text = request.data.get('text') or ''
    html = request.data.get('html')
    if not emails:
        return Response({'error': 'No se indicaron destinatarios.'}, status=400)
    if not subject or not html:
        return Response({'error': 'Faltan subject o html.'}, status=400)

    imagen_base64 = request.data.get('imagen_base64')
    imagen_cid = request.data.get('imagen_cid') or 'imagen1'

    from django.core.mail import EmailMultiAlternatives
    from email.mime.image import MIMEImage
    from django.conf import settings as dj_settings
    import base64 as base64_mod

    imagen_bytes = None
    if imagen_base64:
        try:
            imagen_bytes = base64_mod.b64decode(imagen_base64)
        except Exception:
            return Response({'error': 'imagen_base64 inválida.'}, status=400)

    enviados, fallidos = [], []
    for destinatario in emails:
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text,
                from_email=getattr(dj_settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
                to=[destinatario],
            )
            msg.attach_alternative(html, 'text/html')
            if imagen_bytes:
                msg.mixed_subtype = 'related'
                img = MIMEImage(imagen_bytes, 'png')
                img.add_header('Content-ID', f'<{imagen_cid}>')
                img.add_header('Content-Disposition', 'inline', filename='imagen.png')
                msg.attach(img)
            msg.send(fail_silently=False)
            enviados.append(destinatario)
        except Exception as e:
            logger.error("enviar_comunicado: error enviando a %s: %s", destinatario, e)
            fallidos.append({'email': destinatario, 'error': str(e)})

    return Response({'enviados': enviados, 'fallidos': fallidos, 'total': len(emails)})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    """
    Recibe { email } y envía un link de recuperación si el email está registrado.
    Devuelve error explícito si el email no corresponde a ningún usuario.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings as dj_settings

    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'error': 'Email requerido.'}, status=400)

    UserModel = get_user_model()
    usuarios = list(UserModel.objects.filter(email__iexact=email, is_active=True))

    if not usuarios:
        return Response(
            {'error': 'No encontramos una cuenta registrada con ese email.'},
            status=400,
        )

    frontend_url = getattr(dj_settings, 'FRONTEND_URL', 'https://www.totalstock.com.ar').rstrip('/')

    # Construir lista de cuentas con su link individual
    cuentas = []
    for user in usuarios:
        uid   = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f"{frontend_url}/?uid={uid}&token={token}"
        tienda_nombre = getattr(getattr(user, 'tienda', None), 'nombre', user.username)
        cuentas.append({
            'username':     user.username,
            'tienda':       tienda_nombre,
            'reset_url':    reset_url,
        })

    multi = len(cuentas) > 1

    # ── Texto plano ──────────────────────────────────────────────────────────
    if multi:
        intro = (
            f"Hola,\n\n"
            f"Recibimos una solicitud de recupero de contraseña para el email {email}.\n"
            f"Encontramos {len(cuentas)} cuentas asociadas. "
            f"Hacé clic en el enlace correspondiente a cada tienda:\n\n"
        )
        cuerpo_cuentas = ''
        for c in cuentas:
            cuerpo_cuentas += f"  🏪 {c['tienda']}  (usuario: {c['username']})\n  {c['reset_url']}\n\n"
        texto = intro + cuerpo_cuentas + (
            "Cada enlace expira en 72 horas.\n\n"
            "Si no solicitaste este cambio, ignorá este correo.\n\n"
            "— El equipo de Total Stock\nwww.totalstock.com.ar"
        )
    else:
        c = cuentas[0]
        texto = (
            f"Hola,\n\n"
            f"Recibimos una solicitud para restablecer la contraseña de tu cuenta en Total Stock.\n\n"
            f"Hacé clic en el siguiente enlace para crear una nueva contraseña:\n"
            f"{c['reset_url']}\n\n"
            f"Este enlace expira en 72 horas.\n\n"
            f"Si no solicitaste este cambio, podés ignorar este correo.\n\n"
            f"— El equipo de Total Stock\nwww.totalstock.com.ar"
        )

    # ── HTML ─────────────────────────────────────────────────────────────────
    CSS = """
  body{margin:0;padding:0;background:#f8fafc;font-family:'Helvetica Neue',Arial,sans-serif;}
  .wrap{max-width:560px;margin:40px auto;background:#fff;border-radius:16px;
        box-shadow:0 4px 24px rgba(0,0,0,.08);overflow:hidden;}
  .header{background:linear-gradient(135deg,#5dc87a 0%,#38a080 100%);
          padding:32px 40px;text-align:center;}
  .header h1{margin:0;color:#fff;font-size:22px;font-weight:700;}
  .header p{margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;}
  .body{padding:32px 40px;}
  .body p{color:#334155;font-size:15px;line-height:1.7;margin:0 0 14px;}
  .account{border:1.5px solid #e2e8f0;border-radius:12px;padding:18px 20px;
           margin:16px 0;background:#f8fafc;}
  .account-name{font-size:15px;font-weight:700;color:#1e3a8a;margin:0 0 4px;}
  .account-user{font-size:12px;color:#94a3b8;margin:0 0 14px;}
  .btn{display:inline-block;background:linear-gradient(135deg,#5dc87a,#38a080);
       color:#fff!important;text-decoration:none;padding:11px 28px;
       border-radius:9px;font-size:14px;font-weight:700;
       box-shadow:0 4px 14px rgba(93,200,122,.35);}
  .btn-solo{display:block;width:fit-content;margin:24px auto;padding:14px 36px;font-size:15px;}
  .note{font-size:12px;color:#94a3b8;text-align:center;margin-top:20px;}
  .footer{background:#f1f5f9;padding:18px 40px;text-align:center;
          color:#94a3b8;font-size:12px;border-top:1px solid #e2e8f0;}
  .footer a{color:#5dc87a;text-decoration:none;}
"""

    if multi:
        bloques_html = ''
        for c in cuentas:
            bloques_html += f"""
  <div class="account">
    <p class="account-name">🏪 {c['tienda']}</p>
    <p class="account-user">Usuario: <strong>{c['username']}</strong></p>
    <a href="{c['reset_url']}" class="btn">Restablecer contraseña</a>
  </div>"""

        html = f"""<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head>
<body><div class="wrap">
  <div class="header">
    <h1>Total Stock</h1>
    <p>Recupero de contraseña</p>
  </div>
  <div class="body">
    <p>Encontramos <strong>{len(cuentas)} cuentas</strong> asociadas a este email.<br>
    Seleccioná la tienda cuya contraseña querés restablecer:</p>
    {bloques_html}
    <p class="note">Cada enlace expira en <strong>72 horas</strong>.<br>
    Si no solicitaste este cambio, ignorá este correo.</p>
  </div>
  <div class="footer">&copy; {__import__('datetime').date.today().year} Total Stock &nbsp;·&nbsp;
    <a href="https://www.totalstock.com.ar">www.totalstock.com.ar</a></div>
</div></body></html>"""
        subject = f'[Total Stock] Recuperá tu contraseña — {len(cuentas)} cuentas encontradas'
    else:
        c = cuentas[0]
        html = f"""<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head>
<body><div class="wrap">
  <div class="header">
    <h1>Total Stock</h1>
    <p>Gestión de inventario para tu negocio</p>
  </div>
  <div class="body">
    <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en Total Stock.</p>
    <p>Hacé clic en el botón para crear una nueva contraseña:</p>
    <a href="{c['reset_url']}" class="btn btn-solo">Restablecer mi contraseña</a>
    <p class="note">Este enlace expira en <strong>72 horas</strong>.<br>
    Si no solicitaste este cambio, podés ignorar este correo.</p>
  </div>
  <div class="footer">&copy; {__import__('datetime').date.today().year} Total Stock &nbsp;·&nbsp;
    <a href="https://www.totalstock.com.ar">www.totalstock.com.ar</a></div>
</div></body></html>"""
        subject = '[Total Stock] Recuperá tu contraseña'

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=texto,
            from_email=getattr(dj_settings, 'DEFAULT_FROM_EMAIL', 'Total Stock <info@totalstock.com.ar>'),
            to=[email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
        usernames = ', '.join(c['username'] for c in cuentas)
        logger.info("password_reset_request: email enviado a %s (users=%s)", email, usernames)
    except Exception as e:
        logger.error("password_reset_request: error enviando email a %s: %s", email, e)

    return Response({
        'ok': True,
        'mensaje': 'Te enviamos las instrucciones a tu casilla de correo.',
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    """
    Recibe { uid, token, new_password } y actualiza la contraseña.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode

    uid          = (request.data.get('uid') or '').strip()
    token        = (request.data.get('token') or '').strip()
    new_password = (request.data.get('new_password') or '').strip()

    if not uid or not token or not new_password:
        return Response({'error': 'Datos incompletos.'}, status=400)

    if len(new_password) < 8:
        return Response({'error': 'La contraseña debe tener al menos 8 caracteres.'}, status=400)

    UserModel = get_user_model()
    try:
        pk   = force_str(urlsafe_base64_decode(uid))
        user = UserModel.objects.get(pk=pk)
    except Exception:
        return Response({'error': 'El enlace es inválido o ya expiró.'}, status=400)

    if not default_token_generator.check_token(user, token):
        return Response({'error': 'El enlace es inválido o ya expiró.'}, status=400)

    user.set_password(new_password)
    user.save()
    logger.info("password_reset_confirm: contraseña actualizada para user=%s", user.username)

    return Response({'ok': True, 'mensaje': 'Contraseña actualizada. Ya podés iniciar sesión.'})
