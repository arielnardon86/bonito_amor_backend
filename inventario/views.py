# inventario/views.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/views.py
import logging
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value 
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import DecimalField 
from django.db import close_old_connections # <-- Importado para el fix de conexión
from django.http import HttpResponse
from io import BytesIO

logger = logging.getLogger(__name__)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# CAMBIO 1: Importar ArancelMetodoTienda
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda, Factura 
# CAMBIO 2: Importar ArancelMetodoTiendaSerializer
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer, ArancelMetodoTiendaSerializer,
    FacturaSerializer, EmitirFacturaSerializer
)
# Importar modelos de facturación
from .models import Factura
from .services.facturacion_service import FacturacionService
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nombre', 'talle', 'codigo_barras']

    def get_queryset(self):
        user = self.request.user
        queryset = Producto.objects.all()

        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug).order_by('nombre')
            return queryset.order_by('nombre')
        
        elif user.tienda:
            if tienda_slug and user.tienda.nombre != tienda_slug:
                return Producto.objects.none()
            
            return queryset.filter(tienda=user.tienda).order_by('nombre')
        
        return Producto.objects.none()

    def perform_create(self, serializer):
        serializer.save(tienda=self.request.user.tienda)

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

        try:
            producto = self.get_queryset().get(codigo_barras=codigo, tienda__nombre=tienda_slug)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)


    @action(detail=False, methods=['get'])
    def productos_con_stock(self, request):
        productos = self.get_queryset().filter(stock__gt=0)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)


class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    
    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    # FIX DE CONEXIÓN (Mantenido)
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.all().order_by('username')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug)
            return queryset
        
        elif user.tienda:
            return queryset.filter(tienda=user.tienda)
        
        return User.objects.none()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class VentaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        queryset = Venta.objects.all().order_by('-fecha_venta')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        if not user.is_superuser:
            if user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
            else:
                return Venta.objects.none()
        elif tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)

        fecha_venta_date = self.request.query_params.get('fecha_venta__date', None)
        if fecha_venta_date:
            queryset = queryset.filter(fecha_venta__date=fecha_venta_date)

        usuario = self.request.query_params.get('usuario', None)
        if usuario:
            queryset = queryset.filter(usuario=usuario)

        anulada = self.request.query_params.get('anulada', None)
        if anulada is not None:
            queryset = queryset.filter(anulada=anulada == 'true')
            
        return queryset

    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        venta.anulada = True
        venta.save()

        detalles = DetalleVenta.objects.filter(venta=venta)
        for detalle in detalles:
            if detalle.producto and not detalle.anulado_individualmente:
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
        
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        detalle_id = request.data.get('detalle_id')
        if not detalle_id:
            return Response({"error": "Se requiere el ID del detalle de venta."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            detalle = DetalleVenta.objects.get(id=detalle_id, venta__id=pk)
        except DetalleVenta.DoesNotExist:
            return Response({"error": "Detalle de venta no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser:
            return Response({"error": "No tienes permiso para anular este detalle de venta."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "No se puede anular un detalle de una venta que ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            detalle.anulado_individualmente = True
            detalle.save()
            
            venta = detalle.venta
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
            
            return Response({"status": "Detalle de venta anulado con éxito y stock restaurado."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()

            venta = detalle.venta
            if not venta.detalles.filter(anulado_individualmente=False).exists():
                venta.anulada = True
                venta.save()

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
        if not user.is_superuser and user.tienda != venta.tienda:
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


class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        elif user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda)
        return DetalleVenta.objects.none()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    permission_classes = [permissions.IsAuthenticated]

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


# CAMBIO CRUCIAL: NUEVO VIEWSET para aranceles
class ArancelMetodoTiendaViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArancelMetodoTiendaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Uso select_related para optimizar la consulta de tienda y método de pago
        queryset = ArancelMetodoTienda.objects.all().select_related('tienda', 'metodo_pago')
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
            # Limitar la respuesta si es superusuario y pide todos los aranceles
            return queryset.order_by('tienda__nombre', 'metodo_pago__nombre', 'nombre_plan')[:50] 
        
        elif user.tienda:
            # Solo muestra los aranceles de su tienda
            return queryset.filter(tienda=user.tienda).order_by('metodo_pago__nombre', 'nombre_plan')
        
        return ArancelMetodoTienda.objects.none()

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
                return queryset.filter(tienda__nombre=tienda_slug).order_by('-fecha_compra')
            return queryset.order_by('-fecha_compra')
        elif user.tienda:
            return queryset.filter(tienda=user.tienda).order_by('-fecha_compra')
        return Compra.objects.none()

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
        

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

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

        # Métrica de stock total (cantidad)
        total_stock = Producto.objects.filter(tienda=tienda_obj).aggregate(total_stock=Sum('stock'))['total_stock'] or 0

        # Métrica de monto total del stock (precio de venta)
        monto_total_stock_precio = Producto.objects.filter(tienda=tienda_obj).aggregate(
            total_monto_stock=Sum(F('stock') * Coalesce('precio', Value(0), output_field=DecimalField()))
        )['total_monto_stock'] or Decimal('0.00')
        
        # Métrica de monto total del stock (costo)
        monto_total_stock_costo = Producto.objects.filter(tienda=tienda_obj).aggregate(
            total_monto_stock_costo=Sum(F('stock') * Coalesce('costo', Value(0), output_field=DecimalField()))
        )['total_monto_stock_costo'] or Decimal('0.00')

        data = {
            'total_stock': total_stock,
            'total_monto_stock_precio': monto_total_stock_precio,
            'total_monto_stock_costo': monto_total_stock_costo,
        }

        return Response(data)

# --- VISTA PARA MÉTRICAS DE VENTAS (ACTUALIZADA) ---
class MetricasAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        year = request.query_params.get('year', None)
        month = request.query_params.get('month', None)
        day = request.query_params.get('day', None)
        seller_id = request.query_params.get('seller_id', None)
        payment_method = request.query_params.get('payment_method', None)

        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        
        # Filtramos las ventas para excluir las anuladas
        queryset_ventas = Venta.objects.filter(tienda=tienda_obj, anulada=False)
        queryset_compras = Compra.objects.filter(tienda=tienda_obj)

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


        total_ventas_periodo = queryset_ventas.aggregate(total_ventas=Sum('total'))['total_ventas'] or Decimal('0.00')
        
        # Filtramos los detalles de venta para excluir los anulados individualmente
        detalles_activos = DetalleVenta.objects.filter(venta__in=queryset_ventas, anulado_individualmente=False)
        total_productos_vendidos_periodo = detalles_activos.aggregate(total_productos_vendidos=Sum('cantidad'))['total_productos_vendidos'] or 0
        
        total_costo_vendido = detalles_activos.aggregate(total_costo_vendido=Sum(F('cantidad') * Coalesce('costo_unitario', Value(0), output_field=DecimalField())))['total_costo_vendido'] or Decimal('0.00')

        total_compras_periodo = queryset_compras.aggregate(total_egresos=Sum('total'))['total_egresos'] or Decimal('0.00')

        # CAMBIO 10: NUEVO CÁLCULO: Arancel Total de Ventas con Comisión
        total_arancel_ventas = queryset_ventas.aggregate(
            total_arancel=Sum(F('arancel_total') * Value(1), output_field=DecimalField())
        )['total_arancel'] or Decimal('0.00')


        # CAMBIO 11: La rentabilidad ahora resta el costo de los productos, los egresos Y los aranceles
        rentabilidad_bruta = total_ventas_periodo - total_costo_vendido - total_compras_periodo - total_arancel_ventas
        margen_rentabilidad = (rentabilidad_bruta / total_ventas_periodo * 100) if total_ventas_periodo > 0 else 0

        productos_mas_vendidos = detalles_activos.values(
            'producto__nombre', 'producto__talle'
        ).annotate(
            cantidad_total=Sum('cantidad')
        ).order_by('-cantidad_total')[:10]
        
        ventas_por_usuario = queryset_ventas.values('usuario__username').annotate(
            total_vendido=Sum('total'),
            cantidad_ventas=Count('id')
        ).order_by('-total_vendido')

        ventas_por_metodo_pago = queryset_ventas.values('metodo_pago').annotate(
            total_vendido=Sum('total')
        ).order_by('-total_vendido')

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
            'total_arancel_ventas': total_arancel_ventas, # NUEVA MÉTRICA
            'rentabilidad_bruta_periodo': rentabilidad_bruta,
            'margen_rentabilidad_periodo': margen_rentabilidad,
            'productos_mas_vendidos': list(productos_mas_vendidos),
            'ventas_por_usuario': list(ventas_por_usuario),
            'ventas_por_metodo_pago': list(ventas_por_metodo_pago),
            'egresos_por_mes': list(egresos_por_mes),
        }

        return Response(data)


class FacturaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar facturas emitidas"""
    serializer_class = FacturaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_comprobante', 'cliente_nombre', 'cliente_cuit', 'cae']
    ordering_fields = ['fecha_emision', 'numero_comprobante', 'total']
    ordering = ['-fecha_emision']
    
    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        """Anula una factura electrónica emitida"""
        factura = get_object_or_404(Factura, pk=pk)
        
        # Validar permisos
        user = request.user
        if not user.is_superuser and user.tienda != factura.tienda:
            return Response(
                {"error": "No tienes permiso para anular facturas de esta tienda."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar que la factura pueda ser anulada
        if factura.estado == 'ANULADA':
            return Response(
                {"error": "Esta factura ya está anulada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if factura.estado != 'EMITIDA':
            return Response(
                {"error": f"La factura no puede ser anulada. Estado actual: {factura.estado}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que tenga los datos necesarios
        if not factura.numero_comprobante or not factura.cae:
            return Response(
                {"error": "La factura no tiene los datos necesarios para anular (falta número de comprobante o CAE)."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            logger.info(f"=== Iniciando anulación de factura ===")
            logger.info(f"Factura ID: {factura.id}")
            logger.info(f"Punto de venta: {factura.punto_venta}, Número: {factura.numero_comprobante}")
            logger.info(f"CAE: {factura.cae}")
            
            # Inicializar servicio de facturación
            facturacion_service = FacturacionService(factura.tienda)
            
            # Anular factura
            exito, error = facturacion_service.anular_factura(factura)
            
            if not exito:
                return Response(
                    {"error": error or "Error al anular la factura"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Actualizar estado de la factura
            factura.estado = 'ANULADA'
            factura.save()
            
            logger.info(f"✅ Factura {factura.id} anulada exitosamente")
            
            return Response(
                {
                    "mensaje": "Factura anulada exitosamente",
                    "factura_id": str(factura.id),
                    "estado": "ANULADA"
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            error_msg = f"Error inesperado al anular factura: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return Response(
                {"error": error_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get_queryset(self):
        user = self.request.user
        
        queryset = Factura.objects.select_related('venta', 'tienda').all()
        
        # Filtrar por tienda si no es superusuario
        if user.is_superuser:
            tienda_id = self.request.query_params.get('tienda', None)
            if tienda_id:
                queryset = queryset.filter(tienda_id=tienda_id)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            queryset = Factura.objects.none()
        
        # Filtros opcionales
        estado = self.request.query_params.get('estado', None)
        if estado:
            queryset = queryset.filter(estado=estado)
        
        tipo_comprobante = self.request.query_params.get('tipo_comprobante', None)
        if tipo_comprobante:
            queryset = queryset.filter(tipo_comprobante=tipo_comprobante)
        
        # Filtrar por venta (UUID)
        venta_id = self.request.query_params.get('venta', None)
        if venta_id:
            queryset = queryset.filter(venta_id=venta_id)
        
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
        # Mostrar punto de venta y número juntos en una línea más abajo
        story.append(Paragraph(f"<b>Comprobante:</b> {factura.punto_venta:04d}-{factura.numero_comprobante:08d}", normal_style))
        if factura.cae:
            story.append(Paragraph(f"<b>CAE:</b> {factura.cae}", normal_style))
        if factura.fecha_vencimiento_cae:
            story.append(Paragraph(f"<b>CAE Vto:</b> {factura.fecha_vencimiento_cae.strftime('%d/%m/%Y')}", normal_style))
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
        
        # Subtotal sin IVA (después de descuentos/recargos)
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