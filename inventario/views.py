# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Count, Value, Q 
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour 
from django.utils import timezone
from datetime import timedelta, datetime 
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView # Importar TokenObtainPairView base

import logging
logger = logging.getLogger(__name__)


from .models import (
    Producto, Categoria, Tienda, User, Venta, DetalleVenta,
    MetodoPago
)
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, 
    MetodoPagoSerializer, 
    VentaCreateSerializer,
    CustomTokenObtainPairSerializer # Importar el serializer personalizado
)
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'talle']
    search_fields = ['nombre', 'codigo_barras', 'talle']
    ordering_fields = ['nombre', 'precio', 'stock']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Producto.objects.all()
        elif user.tienda:
            return Producto.objects.filter(tienda=user.tienda)
        return Producto.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            serializer.save(tienda=self.request.user.tienda)
        else:
            serializer.save()


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]


class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    permission_classes = [IsAuthenticated]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return User.objects.all()
        elif user.is_staff and user.tienda:
            return User.objects.filter(tienda=user.tienda)
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class DetalleVentaViewSet(viewsets.ModelViewSet): 
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        elif user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda)
        return DetalleVenta.objects.none()


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all()
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = VentaFilter 
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Venta.objects.all().order_by('-fecha_venta')
        elif user.tienda:
            return Venta.objects.filter(tienda=user.tienda).order_by('-fecha_venta')
        return Venta.objects.none()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def anular(self, request, pk=None):
        try:
            venta = self.get_queryset().get(pk=pk)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if venta.anulada:
            return Response({"detail": "La venta ya está anulada."}, status=status.HTTP_400_BAD_REQUEST)

        for detalle in venta.detalles.all():
            if not detalle.anulado_individualmente: 
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
                detalle.anulado_individualmente = True 
                detalle.save()

        venta.anulada = True
        venta.total = Decimal('0.00') 
        venta.save()
        
        serializer = self.get_serializer(venta)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def anular_detalle(self, request, pk=None):
        try:
            venta = self.get_queryset().get(pk=pk)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        detalle_id = request.data.get('detalle_id')
        if not detalle_id:
            return Response({"detail": "ID de detalle de venta no proporcionado."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            detalle = venta.detalles.get(id=detalle_id)
        except DetalleVenta.DoesNotExist:
            return Response({"detail": "Detalle de venta no encontrado en esta venta."}, status=status.HTTP_404_NOT_FOUND)

        if detalle.anulado_individualmente:
            logger.warning(f"anular_detalle: Detalle {detalle_id} already individually annulled. Returning 400.")
            return Response({"detail": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if venta.anulada:
            logger.warning(f"anular_detalle: Venta {pk} is already fully annulled. Cannot annul individual detail.")
            return Response({"detail": "La venta completa ya está anulada. No se puede anular un detalle individualmente."}, status=status.HTTP_400_BAD_REQUEST)

        producto = detalle.producto
        producto.stock += detalle.cantidad
        producto.save()

        detalle.anulado_individualmente = True
        detalle.save()

        total_venta_actualizado = sum(
            d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente
        )
        venta.total = total_venta_actualizado
        venta.save()

        serializer = self.get_serializer(venta)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    permission_classes = [IsAuthenticated]


class DashboardMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser] 

    def get(self, request, *args, **kwargs):
        user = request.user
        if not user.is_superuser:
            return Response({"detail": "Acceso denegado. Solo los superusuarios pueden ver las métricas."},
                            status=status.HTTP_403_FORBIDDEN)

        tienda_slug = request.query_params.get('tienda_slug')
        if not tienda_slug:
            return Response({"detail": "Se requiere el slug de la tienda."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({"detail": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        year_filter = request.query_params.get('year')
        month_filter = request.query_params.get('month')
        day_filter = request.query_params.get('day')
        seller_id_filter = request.query_params.get('seller_id')
        payment_method_filter = request.query_params.get('payment_method')

        ventas_queryset = Venta.objects.filter(tienda=tienda).exclude(anulada=True).exclude(total=Decimal('0.00'))

        if year_filter:
            try:
                year_filter = int(year_filter)
                ventas_queryset = ventas_queryset.filter(fecha_venta__year=year_filter)
            except ValueError:
                return Response({"detail": "Año inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if month_filter:
            try:
                month_filter = int(month_filter)
                ventas_queryset = ventas_queryset.filter(fecha_venta__month=month_filter)
            except ValueError:
                return Response({"detail": "Mes inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if day_filter:
            try:
                day_filter = int(day_filter)
                ventas_queryset = ventas_queryset.filter(fecha_venta__day=day_filter)
            except ValueError:
                return Response({"detail": "Día inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if seller_id_filter:
            ventas_queryset = ventas_queryset.filter(usuario__id=seller_id_filter)

        if payment_method_filter:
            ventas_queryset = ventas_queryset.filter(metodo_pago=payment_method_filter)

        total_ventas_periodo = ventas_queryset.aggregate(
            sum_total=Coalesce(Sum('total'), Value(Decimal('0.0')))
        )['sum_total']

        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, 
            anulado_individualmente=False 
        ).aggregate(
            sum_cantidad=Coalesce(Sum('cantidad'), Value(0))
        )['sum_cantidad']

        period_label = "Período" 
        
        if day_filter and month_filter and year_filter:
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractHour('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Hora del Día"
        elif month_filter and year_filter:
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractDay('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Día del Mes"
        elif year_filter:
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Mes del Año"
        else:
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Mes del Año"


        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, 
            anulado_individualmente=False 
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0)) 
        ).order_by('-cantidad_total')[:5]

        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0)) 
        ).order_by('-monto_total_vendido')

        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago').annotate( 
            monto_total=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0))
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


class CustomTokenObtainPairView(TokenObtainPairView): 
    """
    Vista personalizada para la obtención de tokens JWT.
    Utiliza un serializer personalizado para incluir más datos del usuario.
    """
    serializer_class = CustomTokenObtainPairSerializer
