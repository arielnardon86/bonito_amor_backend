# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Count, Value, Q # Importar Q para condiciones OR
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour # Nuevas funciones de extracción
from django.utils import timezone
from datetime import timedelta, datetime # Importar datetime
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
    MetodoPagoSerializer, # Asegurarse de que MetodoPagoSerializer esté importado
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
    ordering_fields = ['nombre', 'precio', 'stock']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Producto.objects.all()
        elif user.tienda:
            return Producto.objects.filter(tienda=user.tienda)
        return Producto.objects.none()

    def perform_create(self, serializer):
        # Asignar la tienda del usuario autenticado si no es superusuario
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
        return User.objects.filter(id=user.id) # Un usuario normal solo puede verse a sí mismo

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all()
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = VentaFilter # Usar el filtro personalizado
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
        # La lógica de usuario y tienda ya está en VentaCreateSerializer.create
        serializer.save()

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def anular(self, request, pk=None):
        try:
            venta = self.get_queryset().get(pk=pk)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if venta.anulada:
            return Response({"detail": "La venta ya está anulada."}, status=status.HTTP_400_BAD_REQUEST)

        # Revertir stock de todos los productos en la venta
        for detalle in venta.detalles.all():
            if not detalle.anulado_individualmente: # Solo revertir si no ha sido anulado individualmente
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
                detalle.anulado_individualmente = True # Marcar también el detalle como anulado
                detalle.save()

        venta.anulada = True
        venta.total = Decimal('0.00') # Establecer el total a 0
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

        # Revertir stock del producto
        producto = detalle.producto
        producto.stock += detalle.cantidad
        producto.save()

        # Marcar el detalle como anulado individualmente
        detalle.anulado_individualmente = True
        detalle.save()

        # Recalcular el total de la venta
        # Suma los subtotales de los detalles NO anulados individualmente
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
    permission_classes = [IsAuthenticated, IsAdminUser] # Solo superusuarios pueden ver métricas

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

        # Obtener filtros del request
        year_filter = request.query_params.get('year')
        month_filter = request.query_params.get('month')
        day_filter = request.query_params.get('day')
        seller_id_filter = request.query_params.get('seller_id')
        payment_method_filter = request.query_params.get('payment_method')

        # Construir el queryset base para ventas
        # Excluir ventas completamente anuladas (anulada=True)
        # Excluir ventas donde el total es 0 (lo que indica que todos los detalles fueron anulados individualmente)
        ventas_queryset = Venta.objects.filter(tienda=tienda).exclude(anulada=True).exclude(total=Decimal('0.00'))

        # Aplicar filtros de fecha
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

        # Aplicar filtro de vendedor
        if seller_id_filter:
            ventas_queryset = ventas_queryset.filter(usuario__id=seller_id_filter)

        # Aplicar filtro de método de pago
        if payment_method_filter:
            ventas_queryset = ventas_queryset.filter(metodo_pago=payment_method_filter)

        # --- Métricas de Resumen (Total Ventas y Total Productos Vendidos) ---
        total_ventas_periodo = ventas_queryset.aggregate(
            sum_total=Coalesce(Sum('total'), Value(Decimal('0.0')))
        )['sum_total']

        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, # Solo detalles de ventas no anuladas
            anulado_individualmente=False # Excluir detalles anulados individualmente
        ).aggregate(
            sum_cantidad=Coalesce(Sum('cantidad'), Value(0))
        )['sum_cantidad']

        # --- Ventas Agrupadas por Período (para el gráfico de barras) ---
        # Determinar el tipo de agrupación y la etiqueta del período
        if day_filter and month_filter and year_filter:
            # Agrupar por hora si se filtra por día específico
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractHour('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Hora del Día"
        elif month_filter and year_filter:
            # Agrupar por día si se filtra por mes específico
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractDay('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Día del Mes"
        elif year_filter:
            # Agrupar por mes si se filtra por año específico
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Mes del Año"
        else:
            # Por defecto, agrupar por mes del año actual si no hay filtros específicos de fecha
            # O puedes elegir otro default, como por año si no hay filtros de fecha
            # Para este caso, vamos a agrupar por mes si solo hay filtro de tienda
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('periodo')
            period_label = "Mes del Año" # Default si no hay filtros de fecha tan específicos


        # --- Productos Más Vendidos ---
        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset, # Solo detalles de ventas no anuladas
            anulado_individualmente=False # Excluir detalles anulados individualmente
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0)) 
        ).order_by('-cantidad_total')[:5]

        # --- Ventas por Usuario ---
        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            # CAMBIO: Contar solo ventas con total > 0 para 'cantidad_ventas'
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0)) 
        ).order_by('-monto_total_vendido')

        # --- Ventas por Método de Pago ---
        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago').annotate( 
            monto_total=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            # CAMBIO: Contar solo ventas con total > 0 para 'cantidad_ventas'
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

