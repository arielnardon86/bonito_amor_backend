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
        Permite a los superusuarios ver todos los productos.
        Los usuarios normales solo pueden ver productos de su tienda asignada.
        """
        user = self.request.user
        if user.is_superuser:
            return Producto.objects.all()
        elif user.is_authenticated and user.tienda:
            return Producto.objects.filter(tienda=user.tienda)
        return Producto.objects.none() # No autenticado o sin tienda asignada

    def perform_create(self, serializer):
        # Asegura que el producto se cree en la tienda del usuario autenticado
        # (a menos que sea superusuario y especifique una tienda)
        user = self.request.user
        if user.is_superuser and 'tienda' in self.request.data:
            serializer.save() # Permite al superusuario especificar la tienda
        elif user.is_authenticated and user.tienda:
            serializer.save(tienda=user.tienda)
        else:
            # Esto debería ser manejado por permisos, pero es una capa de seguridad extra
            raise serializers.ValidationError("No tienes permisos para crear productos o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        # Asegura que solo se puedan actualizar productos de la propia tienda
        user = self.request.user
        instance_tienda = serializer.instance.tienda
        if user.is_superuser or (user.is_authenticated and user.tienda == instance_tienda):
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar productos de esta tienda.")

    def perform_destroy(self, instance):
        # Asegura que solo se puedan eliminar productos de la propia tienda
        user = self.request.user
        instance_tienda = instance.tienda
        if user.is_superuser or (user.is_authenticated and user.tienda == instance_tienda):
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

    # Las categorías pueden ser globales o asociadas a una tienda.
    # Si son globales, no necesitan filtrado por tienda. Si son por tienda,
    # se necesitaría un campo 'tienda' en el modelo Categoria y un get_queryset similar.
    # Por ahora, asumimos que las categorías son globales.


class TiendaViewSet(viewsets.ReadOnlyModelViewSet): # ReadOnly porque la creación/edición de tiendas es más sensible
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    permission_classes = [AllowAny] # Las tiendas pueden ser listadas por cualquiera para el login


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('tienda') # Optimizar para cargar la tienda
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated] # Solo usuarios autenticados pueden ver esto
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tienda', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

    def get_queryset(self):
        """
        Permite a los superusuarios ver todos los usuarios.
        Los usuarios normales (staff) solo pueden ver usuarios de su propia tienda.
        """
        user = self.request.user
        if user.is_superuser:
            return User.objects.all().select_related('tienda')
        elif user.is_authenticated and user.is_staff and user.tienda:
            # Los usuarios staff solo pueden ver a otros usuarios de su misma tienda
            return User.objects.filter(tienda=user.tienda).select_related('tienda')
        return User.objects.none() # No autenticado, no staff, o sin tienda asignada

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            # Superusuario puede crear cualquier usuario y asignarle una tienda
            serializer.save()
        elif user.is_authenticated and user.is_staff and user.tienda:
            # Un staff puede crear usuarios, pero solo en su propia tienda
            # Y no puede crear superusuarios ni asignar tiendas diferentes
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para asignar usuarios a otra tienda."})
            if self.request.data.get('is_superuser', False):
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para crear superusuarios."})
            serializer.save(tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear usuarios.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda

        if user.is_superuser:
            # Superusuario puede actualizar cualquier usuario
            serializer.save()
        elif user.is_authenticated and user.is_staff and user.tienda:
            # Un staff solo puede actualizar usuarios de su propia tienda
            if instance_tienda != user.tienda:
                raise serializers.ValidationError("No tienes permiso para actualizar usuarios de otra tienda.")
            # Un staff no puede cambiar el estado de superusuario
            if 'is_superuser' in self.request.data and self.request.data['is_superuser'] != serializer.instance.is_superuser:
                raise serializers.ValidationError({"is_superuser": "No tienes permiso para cambiar el estado de superusuario."})
            # Un staff no puede cambiar la tienda de un usuario
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(instance_tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para cambiar la tienda de un usuario."})
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar usuarios.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda

        if user.is_superuser:
            # Superusuario puede eliminar cualquier usuario
            instance.delete()
        elif user.is_authenticated and user.is_staff and user.tienda:
            # Un staff solo puede eliminar usuarios de su propia tienda
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

    # Asumimos que los métodos de pago pueden ser globales o por tienda.
    # Si son por tienda, se necesitaría un campo 'tienda' en el modelo MetodoPago
    # y un get_queryset similar al de Producto. Por ahora, asumimos que son globales.


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().select_related('usuario', 'metodo_pago', 'tienda')
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'fecha_venta': ['gte', 'lte', 'exact__date'], # Permite filtrar por fecha exacta, rango
        'usuario': ['exact'],
        'metodo_pago': ['exact'],
        'anulada': ['exact'],
        'tienda': ['exact'], # Añadir filtro por tienda
    }
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action in ['create']:
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        """
        Permite a los superusuarios ver todas las ventas.
        Los usuarios normales (staff) solo pueden ver ventas de su tienda asignada.
        """
        user = self.request.user
        if user.is_superuser:
            return Venta.objects.all().select_related('usuario', 'metodo_pago', 'tienda')
        elif user.is_authenticated and user.tienda:
            return Venta.objects.filter(tienda=user.tienda).select_related('usuario', 'metodo_pago', 'tienda')
        return Venta.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            # Superusuario puede crear ventas para cualquier tienda
            serializer.save(usuario=user)
        elif user.is_authenticated and user.tienda:
            # Usuario normal solo puede crear ventas para su propia tienda
            # Asegurarse de que la tienda en la data (si se envía) coincida con la del usuario
            if 'tienda' in self.request.data and self.request.data['tienda'] != str(user.tienda.id):
                raise serializers.ValidationError({"tienda": "No tienes permiso para crear ventas en otra tienda."})
            serializer.save(usuario=user, tienda=user.tienda)
        else:
            raise serializers.ValidationError("No tienes permisos para crear ventas o no tienes una tienda asignada.")

    def perform_update(self, serializer):
        user = self.request.user
        instance_tienda = serializer.instance.tienda

        if user.is_superuser:
            serializer.save()
        elif user.is_authenticated and user.tienda == instance_tienda:
            serializer.save()
        else:
            raise serializers.ValidationError("No tienes permisos para actualizar ventas de otra tienda.")

    def perform_destroy(self, instance):
        user = self.request.user
        instance_tienda = instance.tienda

        if user.is_superuser:
            instance.delete()
        elif user.is_authenticated and user.tienda == instance_tienda:
            instance.delete()
        else:
            raise serializers.ValidationError("No tienes permisos para eliminar ventas de otra tienda.")


class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet): # Generalmente solo lectura, ya que se crean con la venta
    queryset = DetalleVenta.objects.all().select_related('venta__tienda', 'producto')
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'venta__id': ['exact'],
        'producto': ['exact'],
        'venta__tienda': ['exact'], # Añadir filtro por tienda de la venta
    }
    ordering_fields = ['fecha_creacion', 'subtotal']

    def get_queryset(self):
        """
        Permite a los superusuarios ver todos los detalles de venta.
        Los usuarios normales (staff) solo pueden ver detalles de venta de su tienda asignada.
        """
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all().select_related('venta__tienda', 'producto')
        elif user.is_authenticated and user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda).select_related('venta__tienda', 'producto')
        return DetalleVenta.objects.none() # Corregido de DetalleValla a DetalleVenta


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    # No se necesita lógica adicional aquí, ya que la validación de tienda
    # se hará en el frontend después de obtener el token y los datos del usuario.


class DashboardMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        tienda_id = request.query_params.get('tienda_id') # Opcional: para superusuarios que quieran ver métricas de una tienda específica

        # Filtrar ventas por tienda si el usuario no es superusuario o si se especifica una tienda_id
        ventas_queryset = Venta.objects.all()
        if not user.is_superuser:
            if user.tienda:
                ventas_queryset = ventas_queryset.filter(tienda=user.tienda)
            else:
                return Response({"detail": "No tienes una tienda asignada para ver métricas."}, status=status.HTTP_403_FORBIDDEN)
        elif tienda_id: # Superusuario puede filtrar por tienda_id
            ventas_queryset = ventas_queryset.filter(tienda__id=tienda_id)


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

        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago__nombre').annotate( # Usar metodo_pago__nombre
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
