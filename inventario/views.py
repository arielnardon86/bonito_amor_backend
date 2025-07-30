# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Count, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from decimal import Decimal
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
    CustomTokenObtainPairSerializer
)
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'talle']
    search_fields = ['nombre', 'codigo_barras', 'talle']
    ordering_fields = ['nombre', 'precio', 'stock', 'fecha_creacion']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return Producto.objects.filter(tienda=user.tienda)
        return Producto.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para crear productos en otra tienda."})
            serializer.save(tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear productos o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda
        if user.is_authenticated and user.tienda == instance_tienda:
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar productos de esta tienda.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda
        if user.is_authenticated and user.tienda == instance_tienda:
            instance.delete()
        else:
            raise serializers.ValidationError("No tienes permisos para eliminar productos de esta tienda.")


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'fecha_creacion']


class TiendaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    permission_classes = [AllowAny] 


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('tienda')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return User.objects.filter(tienda=user.tienda).select_related('tienda')
        return User.objects.none()

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para asignar usuarios a otra tienda."})
            
            if self.request.data.get('is_superuser', False) and not user.is_superuser:
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para crear superusuarios."})
            
            serializer.save(tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear usuarios o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda

        if user.is_authenticated and user.tienda:
            if instance_tienda != user.tienda:
                raise serializers.ValidationError("No tienes permiso para actualizar usuarios de otra tienda.")
            
            if 'is_superuser' in self.request.data and self.request.data['is_superuser'] != serializer.instance.is_superuser and not user.is_superuser:
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para cambiar el estado de superusuario."})
            
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(instance_tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para cambiar la tienda de un usuario."})
            
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar usuarios.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda

        if user.is_authenticated and user.tienda:
            if instance_tienda != user.tienda:
                raise serializers.ValidationError("No tienes permiso para eliminar usuarios de otra tienda.")
            instance.delete()
        else:
            raise serializers.ValidationError("No tienes permisos para eliminar usuarios.")


class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'fecha_creacion']


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().select_related('usuario', 'tienda') 
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = VentaFilter 
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action in ['create']:
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return Venta.objects.filter(tienda=user.tienda).select_related('usuario', 'tienda')
        return Venta.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para crear ventas en otra tienda."})
            serializer.save(usuario=user, tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear ventas o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda

        if user.is_authenticated and user.tienda == instance_tienda:
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar ventas de otra tienda.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda

        if user.is_authenticated and user.tienda == instance_tienda:
            instance.delete()
        else:
            raise serializers.ValidationError("No tienes permisos para eliminar ventas de otra tienda.")

    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        try:
            venta = self.get_queryset().get(pk=pk)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if venta.anulada:
            return Response({"detail": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        for detalle in venta.detalles.all():
            producto = detalle.producto
            if producto:
                producto.stock += detalle.cantidad
                producto.save()

        venta.anulada = True
        venta.save()
        return Response({"detail": "Venta anulada y stock revertido con éxito."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        logger.info(f"anular_detalle: Request received for venta ID: {pk}")
        logger.info(f"anular_detalle: Request data: {request.data}")

        try:
            venta = self.get_queryset().get(pk=pk)
            logger.info(f"anular_detalle: Venta found: {venta.id}")
        except Venta.DoesNotExist:
            logger.error(f"anular_detalle: Venta with ID {pk} not found.")
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if venta.anulada:
            logger.warning(f"anular_detalle: Attempt to annul detail on already annulled venta {venta.id}.")
            return Response({"detail": "La venta completa ya está anulada, no se pueden anular detalles individuales."}, status=status.HTTP_400_BAD_REQUEST)

        detalle_id = request.data.get('detalle_id')
        logger.info(f"anular_detalle: Received detalle_id: {detalle_id}")

        if not detalle_id:
            logger.error("anular_detalle: detalle_id missing or empty from request data.")
            return Response({"detail": "Se requiere el ID del detalle de venta."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            detalle = venta.detalles.get(id=detalle_id)
            logger.info(f"anular_detalle: DetalleVenta found: {detalle.id} for venta {venta.id}. Initial anulado_individualmente: {detalle.anulado_individualmente}")
        except DetalleVenta.DoesNotExist:
            logger.error(f"anular_detalle: DetalleVenta with ID {detalle_id} not found within venta {venta.id}.")
            return Response({"detail": "Detalle de venta no encontrado en esta venta."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"anular_detalle: Unexpected error finding DetalleVenta: {e}")
            return Response({"detail": "Error interno al buscar el detalle de venta."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if detalle.anulado_individualmente:
            logger.warning(f"anular_detalle: Detalle {detalle.id} already individually annulled. Returning 400.")
            return Response({"detail": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)

        # Revertir stock del producto
        producto = detalle.producto
        if producto:
            logger.info(f"anular_detalle: Product {producto.id} stock BEFORE update: {producto.stock}")
            producto.stock += detalle.cantidad
            producto.save()
            logger.info(f"anular_detalle: Product {producto.id} stock AFTER update: {producto.stock}")
        else:
            logger.warning(f"anular_detalle: Product for detail {detalle.id} is None. Stock not reverted.")

        detalle.anulado_individualmente = True
        detalle.save()
        logger.info(f"anular_detalle: Detalle {detalle.id} marked as individually annulled. Final anulado_individualmente: {detalle.anulado_individualmente}")

        # Recalcular el total de la venta
        # Es crucial que esta agregación NO incluya los detalles anulados individualmente
        venta.total = venta.detalles.filter(anulado_individualmente=False).aggregate(total=Coalesce(Sum('subtotal'), Value(Decimal('0.0'))))['total']
        venta.save()
        logger.info(f"anular_detalle: Venta {venta.id} total recalculated. New total: {venta.total}")

        return Response({"detail": "Detalle de venta anulado y stock revertido con éxito."}, status=status.HTTP_200_OK)


class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all().select_related('venta__tienda', 'producto')
    serializer_class = DetalleVentaSerializer 
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'venta__id': ['exact'],
        'producto': ['exact'],
        'venta__tienda': ['exact'],
    }
    ordering_fields = ['fecha_creacion', 'subtotal']

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda).select_related('venta__tienda', 'producto')
        return DetalleVeno.objects.none()


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class DashboardMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        ventas_queryset = Venta.objects.all()
        if user.is_authenticated and user.tienda:
            ventas_queryset = ventas_queryset.filter(tienda=user.tienda)
        else:
            return Response({"detail": "No tienes una tienda asignada o permisos suficientes para ver métricas."}, status=status.HTTP_403_FORBIDDEN)

        period = request.query_params.get('period', 'day') 
        end_date = timezone.now()
        start_date = end_date

        period_label = "Últimas 24 Horas" 

        if period == 'day':
            start_date = end_date - timedelta(days=1)
            period_label = "Últimas 24 Horas"
        elif period == 'week':
            start_date = end_date - timedelta(weeks=1)
            period_label = "Última Semana"
        elif period == 'month':
            start_date = end_date - timedelta(days=30)
            period_label = "Últimos 30 Días"
        elif period == 'year':
            start_date = end_date - timedelta(days=365)
            period_label = "Últimos 365 Días"

        ventas_queryset = ventas_queryset.filter(fecha_venta__range=[start_date, end_date], anulada=False)

        total_ventas_periodo_agg = ventas_queryset.aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.0'))))
        total_ventas_periodo = total_ventas_periodo_agg['total']

        total_productos_vendidos_periodo_agg = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, anulado_individualmente=False
        ).aggregate(total_cantidad=Coalesce(Sum('cantidad'), Value(0))) 
        total_productos_vendidos_periodo = total_productos_vendidos_periodo_agg['total_cantidad']


        if period == 'day':
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=F('fecha_venta__hour')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
        elif period == 'week':
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=F('fecha_venta__week_day')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
        elif period == 'month':
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=F('fecha_venta__day')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
        elif period == 'year':
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=F('fecha_venta__month')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
        else: # Default a semana
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=F('fecha_venta__week_day')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')


        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, anulado_individualmente=False
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0)) 
        ).order_by('-cantidad_total')[:5]

        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id'), Value(0))
        ).order_by('-monto_total_vendido')

        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago').annotate( 
            monto_total=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id'), Value(0))
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
            "ventas_por_metodo_pago": list(ventas_por_metodo_pago)
        }
        return Response(metrics, status=status.HTTP_200_OK)
