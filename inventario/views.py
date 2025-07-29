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
from decimal import Decimal # Importar Decimal!

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

# ... Otros ViewSets existentes ...

class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'talle']
    search_fields = ['nombre', 'codigo_barras', 'talle']
    ordering_fields = ['nombre', 'precio', 'stock', 'fecha_creacion']

    def get_queryset(self):
        """
        Todos los usuarios autenticados solo pueden ver productos de su tienda asignada.
        """
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return Producto.objects.filter(tienda=user.tienda)
        return Producto.objects.none() # No autenticado o sin tienda asignada

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            # Asegura que el producto se cree en la tienda del usuario autenticado
            # Si se intenta especificar una tienda diferente, lanzar error
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
    # Las categorías pueden ser gestionadas por staff/superusuarios, y son globales.
    # Si fueran por tienda, necesitarían un campo 'tienda' en el modelo Categoria
    # y un get_queryset similar al de Producto.
    permission_classes = [IsAuthenticated] # Ajusta si solo superusuarios deben gestionar categorías
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'fecha_creacion']


class TiendaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    permission_classes = [AllowAny] # Las tiendas pueden ser listadas por cualquiera para el login


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('tienda')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

    def get_queryset(self):
        """
        Todos los usuarios autenticados solo pueden ver usuarios de su propia tienda.
        """
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return User.objects.filter(tienda=user.tienda).select_related('tienda')
        return User.objects.none()

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Devuelve los detalles del usuario autenticado.
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            # Un usuario autenticado solo puede crear usuarios en su propia tienda
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para asignar usuarios a otra tienda."})
            
            # Solo superusuarios pueden crear otros superusuarios
            if self.request.data.get('is_superuser', False) and not user.is_superuser:
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para crear superusuarios."})
            
            serializer.save(tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear usuarios o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda

        if user.is_authenticated and user.tienda:
            # Un usuario autenticado solo puede actualizar usuarios de su propia tienda
            if instance_tienda != user.tienda:
                raise serializers.ValidationError("No tienes permiso para actualizar usuarios de otra tienda.")
            
            # Solo superusuarios pueden cambiar el estado de superusuario
            if 'is_superuser' in self.request.data and self.request.data['is_superuser'] != serializer.instance.is_superuser and not user.is_superuser:
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para cambiar el estado de superusuario."})
            
            # Un usuario autenticado no puede cambiar la tienda de un usuario
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(instance_tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para cambiar la tienda de un usuario."})
            
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar usuarios.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda

        if user.is_authenticated and user.tienda:
            # Un usuario autenticado solo puede eliminar usuarios de su propia tienda
            if instance_tienda != user.tienda:
                raise serializers.ValidationError("No tienes permiso para eliminar usuarios de otra tienda.")
            instance.delete()
        else:
            raise serializers.ValidationError("No tienes permisos para eliminar usuarios.")


class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    # Los métodos de pago son globales para todas las tiendas, pero gestionados por autenticados.
    permission_classes = [IsAuthenticated] # Ajusta si solo superusuarios deben gestionar métodos de pago
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'fecha_creacion']


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().select_related('usuario', 'metodo_pago', 'tienda')
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'fecha_venta': ['gte', 'lte', 'exact__date'],
        'usuario': ['exact'],
        'metodo_pago': ['exact'],
        'anulada': ['exact'],
        'tienda': ['exact'],
    }
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action in ['create']:
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        """
        Todos los usuarios autenticados solo pueden ver ventas de su tienda asignada.
        """
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return Venta.objects.filter(tienda=user.tienda).select_related('usuario', 'metodo_pago', 'tienda')
        return Venta.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated and user.tienda:
            # Usuario autenticado solo puede crear ventas para su propia tienda
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
        """
        Todos los usuarios autenticados solo pueden ver detalles de venta de su tienda asignada.
        """
        user = self.request.user
        if user.is_authenticated and user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda).select_related('venta__tienda', 'producto')
        return DetalleVenta.objects.none()


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class DashboardMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        # Las métricas siempre se filtran por la tienda del usuario autenticado
        ventas_queryset = Venta.objects.all()
        if user.is_authenticated and user.tienda:
            ventas_queryset = ventas_queryset.filter(tienda=user.tienda)
        else:
            return Response({"detail": "No tienes una tienda asignada o permisos suficientes para ver métricas."}, status=status.HTTP_403_FORBIDDEN)

        # Obtener el período de tiempo de los parámetros de la URL
        period = request.query_params.get('period', 'week') # default to 'week'
        end_date = timezone.now()
        start_date = end_date

        period_label = "Última Semana"

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

        total_ventas_periodo = Coalesce(ventas_queryset.aggregate(total=Sum('total'))['total'], Value(Decimal('0.0')))
        total_productos_vendidos_periodo = Coalesce(
            DetalleVenta.objects.filter(venta__in=ventas_queryset).aggregate(total_cantidad=Sum('cantidad'))['total_cantidad'],
            Value(0)
        )

        # Agregación de ventas por período (día, semana, mes)
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
            venta__in=ventas_queryset
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(Decimal('0.0')))
        ).order_by('-cantidad_total')[:5]

        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id'), Value(0))
        ).order_by('-monto_total_vendido')

        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago__nombre').annotate(
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
