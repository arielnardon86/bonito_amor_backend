# BONITO_AMOR/backend/inventario/views.py
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value 
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from django.utils import timezone
from decimal import Decimal 

from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer
)
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Producto.objects.all()
        if self.request.user.tienda:
            return Producto.objects.filter(tienda=self.request.user.tienda).order_by('nombre')
        return Producto.objects.none()

    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        barcode = request.query_params.get('barcode', None)
        if not barcode:
            return Response({'error': 'Parámetro de código de barras faltante.'}, status=status.HTTP_400_BAD_REQUEST)

        tienda_slug = request.query_params.get('tienda_slug', None)
        if not tienda_slug:
            return Response({'error': 'Parámetro de tienda faltante.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({'error': 'Tienda no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            producto = Producto.objects.get(codigo_barras=barcode, tienda=tienda)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({'error': 'Producto no encontrado en esta tienda.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [permissions.IsAdminUser]
        return super().get_permissions()

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated]

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all().order_by('nombre')
    serializer_class = TiendaSerializer
    permission_classes = [permissions.AllowAny] 
    
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all().order_by('nombre')
    serializer_class = MetodoPagoSerializer
    permission_classes = [permissions.IsAuthenticated]

class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().order_by('-fecha_venta')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        self.perform_create(serializer)
        
        venta_instance = serializer.instance

        venta_with_details = Venta.objects.select_related('tienda', 'usuario').prefetch_related('detalles__producto').get(id=venta_instance.id)
        
        response_serializer = VentaSerializer(venta_with_details)

        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)


    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        venta.anulada = True
        venta.save()

        # Restaurar el stock de los productos
        detalles = DetalleVenta.objects.filter(venta=venta)
        for detalle in detalles:
            if detalle.producto and not detalle.anulado_individualmente:
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
        
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        venta = get_object_or_404(Venta, pk=pk)
        detalle_id = request.data.get('detalle_id')

        if not detalle_id:
            return Response({"error": "Se requiere el 'detalle_id' para anular un detalle de venta."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            detalle = DetalleVenta.objects.get(id=detalle_id, venta=venta)
        except DetalleVenta.DoesNotExist:
            return Response({"error": "Detalle de venta no encontrado para esta venta."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser:
            return Response({"error": "No tienes permiso para anular este detalle de venta."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "No se puede anular un detalle de una venta que ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        # Restaurar el stock del producto
        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            detalle.anulado_individualmente = True
            detalle.save()
            
            # Recalcular el subtotal de los ítems NO anulados individualmente
            subtotal_items_no_anulados = sum(d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente)
            
            # CAMBIO CLAVE AQUÍ: Aplicar el descuento_porcentaje de la venta al subtotal recalculado
            descuento_factor = Decimal('1') - (venta.descuento_porcentaje / Decimal('100'))
            venta.total = subtotal_items_no_anulados * descuento_factor
            
            venta.save()
            
            return Response({"status": "Detalle de venta anulado con éxito y stock restaurado."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()
            return Response({"status": "Detalle de venta anulado con éxito, sin stock que restaurar."}, status=status.HTTP_200_OK)


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


class VentaPorUsuarioYFecha(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        fecha_str = request.query_params.get('fecha')
        if not fecha_str:
            return Response({"error": "Se requiere el parámetro 'fecha'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha_obj = timezone.datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        ventas = Venta.objects.filter(
            usuario=request.user,
            fecha_venta__date=fecha_obj
        )
        serializer = VentaSerializer(ventas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class DashboardMetricsView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug')
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        day = request.query_params.get('day')
        seller_id = request.query_params.get('seller_id')
        payment_method = request.query_params.get('payment_method')

        if not tienda_slug:
            return Response({"error": "Se requiere el parámetro 'tienda_slug'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Base queryset para ventas de la tienda
        ventas_queryset = Venta.objects.filter(tienda=tienda, anulada=False)

        # Aplicar filtros de fecha
        if year:
            ventas_queryset = ventas_queryset.filter(fecha_venta__year=year)
        if month:
            ventas_queryset = ventas_queryset.filter(fecha_venta__month=month)
        if day:
            ventas_queryset = ventas_queryset.filter(fecha_venta__day=day)

        # Aplicar filtros de vendedor y método de pago
        if seller_id:
            ventas_queryset = ventas_queryset.filter(usuario__id=seller_id)
        if payment_method:
            ventas_queryset = ventas_queryset.filter(metodo_pago=payment_method)

        # 1. Total de ventas en el período
        total_ventas_periodo = ventas_queryset.aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.00'))))['total']

        # 2. Total de productos vendidos en el período
        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset,
            anulado_individualmente=False
        ).aggregate(total=Coalesce(Sum('cantidad'), Value(0)))['total']

        # 3. Ventas agrupadas por período (día, mes, hora)
        period_label = "Período"
        if day: # Agrupar por hora
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractHour('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Hora del Día"
        elif month: # Agrupar por día
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractDay('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Día del Mes"
        elif year: # Agrupar por mes
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Mes del Año"
        else: # Agrupar por año (si no se especifica nada más)
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractYear('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Año"

        # 4. Productos más vendidos
        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset,
            anulado_individualmente=False
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0))
        ).order_by('-cantidad_total')[:5] # Top 5

        # 5. Ventas por usuario
        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0)) 
        ).order_by('-monto_total_vendido')

        # 6. Ventas por método de pago
        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago').annotate( 
            monto_total=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0))\
        ).order_by('-monto_total')

        metrics = {
            "total_ventas_periodo": total_ventas_periodo, 
            "total_productos_vendidos_periodo": total_productos_vendidos_periodo, 
            "ventas_agrupadas_por_periodo": {
                "label": period_label,
                "data": list(ventas_agrupadas_por_periodo)
            },
            "productos_mas_vendidos": list(productos_mas_vendidos),
            "ventas_por_usuario": list(ventas_por_usuario),
            "ventas_por_metodo_pago": list(ventas_por_metodo_pago),
        }

        return Response(metrics, status=status.HTTP_200_OK)

