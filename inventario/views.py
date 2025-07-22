# BONITO_AMOR/backend/inventario/views.py

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncDay, TruncMonth, TruncYear, TruncDate
from django.utils import timezone
import datetime
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import Producto, Categoria, Venta, DetalleVenta
from .serializers import (
    ProductoSerializer, CategoriaSerializer,
    VentaSerializer, VentaCreateSerializer,
    DetalleVentaSerializer, UserSerializer, UserCreateSerializer
)

User = get_user_model()

# --- Vistas de Autenticación y Usuarios ---
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

# --- Vistas de Categoría ---
class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

# --- Vistas de Producto ---
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all().order_by('nombre')
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['categoria', 'talle']
    search_fields = ['nombre', 'codigo_barras', 'descripcion']

    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        barcode = request.query_params.get('barcode', None)
        if barcode:
            try:
                producto = Producto.objects.get(codigo_barras=barcode)
                serializer = self.get_serializer(producto)
                return Response(serializer.data)
            except Producto.DoesNotExist:
                return Response({'detail': 'Producto no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'Parámetro barcode es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

# --- Vistas de Venta ---
class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().order_by('-fecha_venta')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['usuario', 'anulada', 'metodo_pago', 'fecha_venta']
    serializer_class = VentaSerializer # <--- Added default serializer_class here

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return super().get_serializer_class() # <--- Use super() to get the default serializer

    # La acción 'anular' ahora acepta solicitudes PATCH
    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def anular(self, request, pk=None):
        try:
            venta = self.get_object()
            if venta.anulada:
                return Response({'detail': 'Esta venta ya ha sido anulada.'}, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                venta.anulada = True
                venta.save()

                for detalle in venta.detalles.all():
                    producto = detalle.producto
                    producto.stock += detalle.cantidad
                    producto.save()

            return Response({'detail': 'Venta anulada con éxito y stock revertido.'}, status=status.HTTP_200_OK)
        except Venta.DoesNotExist:
            return Response({'detail': 'Venta no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'detail': f'Error al anular la venta: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- NUEVA VISTA PARA MÉTRICAS DE VENTAS (Separada de VentaViewSet) ---
class MetricasVentasViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        if not request.user.is_superuser:
            return Response({"detail": "No tienes permisos para ver estas métricas."}, status=status.HTTP_403_FORBIDDEN)

        year = request.query_params.get('year')
        month = request.query_params.get('month')
        day = request.query_params.get('day')
        seller_id = request.query_params.get('seller_id')
        payment_method = request.query_params.get('payment_method')

        ventas_queryset = Venta.objects.all().filter(anulada=False)

        try:
            if year:
                ventas_queryset = ventas_queryset.filter(fecha_venta__year=int(year))
            if month:
                ventas_queryset = ventas_queryset.filter(fecha_venta__month=int(month))
            if day:
                ventas_queryset = ventas_queryset.filter(fecha_venta__day=int(day))
        except ValueError:
            return Response({'detail': 'Filtro de fecha inválido (año, mes o día).'}, status=status.HTTP_400_BAD_REQUEST)

        if seller_id:
            try:
                ventas_queryset = ventas_queryset.filter(usuario_id=int(seller_id))
            except ValueError:
                return Response({'detail': 'ID de vendedor inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        if payment_method:
            ventas_queryset = ventas_queryset.filter(metodo_pago__iexact=payment_method)


        total_ventas_periodo_agg = ventas_queryset.aggregate(
            total_monto=Sum('total_venta')
        )
        total_ventas_periodo = total_ventas_periodo_agg['total_monto'] or 0

        total_productos_vendidos_periodo_agg = DetalleVenta.objects.filter(venta__in=ventas_queryset)\
                                            .aggregate(total_cantidad=Sum('cantidad'))
        total_productos_vendidos_periodo = total_productos_vendidos_periodo_agg['total_cantidad'] or 0

        # --- Ventas agrupadas por período para la tendencia ---
        group_by_label = "Año" 
        trunc_level = TruncYear 

        if year and month and day:
            trunc_level = TruncDate 
            group_by_label = "Día"
        elif year and month:
            trunc_level = TruncDay 
            group_by_label = "Día"
        elif year:
            trunc_level = TruncMonth 
            group_by_label = "Mes"


        ventas_agrupadas = ventas_queryset.annotate(fecha_agrupada=trunc_level('fecha_venta')) \
                                     .values('fecha_agrupada') \
                                     .annotate(total_monto=Sum('total_venta'), cantidad_ventas=Count('id')) \
                                     .order_by('fecha_agrupada')

        ventas_agrupadas_data = []
        for item in ventas_agrupadas:
            fecha_label = ""
            if trunc_level == TruncDate or trunc_level == TruncDay:
                fecha_label = item['fecha_agrupada'].strftime('%Y-%m-%d')
            elif trunc_level == TruncMonth:
                fecha_label = item['fecha_agrupada'].strftime('%Y-%m')
            else: # TruncYear
                fecha_label = item['fecha_agrupada'].strftime('%Y')

            ventas_agrupadas_data.append({
                'fecha': fecha_label,
                'total_monto': float(item['total_monto'] or 0),
                'cantidad_ventas': item['cantidad_ventas'],
            })

        productos_mas_vendidos = DetalleVenta.objects.filter(venta__in=ventas_queryset)\
                                .values('producto__nombre')\
                                .annotate(
                                    cantidad_total=Sum('cantidad'),
                                    monto_total=Sum(ExpressionWrapper(F('cantidad') * F('precio_unitario_venta'), output_field=DecimalField()))
                                )\
                                .order_by('-cantidad_total')[:10]

        productos_mas_vendidos_data = [
            {'producto__nombre': item['producto__nombre'],
             'cantidad_total': item['cantidad_total'],
             'monto_total': float(item['monto_total'] or 0)}
            for item in productos_mas_vendidos
        ]

        ventas_por_usuario = ventas_queryset.values('usuario__username')\
                                 .annotate(monto_total_vendido=Sum('total_venta'), cantidad_ventas=Count('id'))\
                                 .order_by('-monto_total_vendido')

        ventas_por_usuario_data = [
            {'usuario__username': item['usuario__username'],
             'monto_total_vendido': float(item['monto_total_vendido'] or 0),
             'cantidad_ventas': item['cantidad_ventas']}
            for item in ventas_por_usuario
        ]

        # --- Ventas por Método de Pago ---
        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago') \
                                       .annotate(monto_total=Sum('total_venta'), cantidad_ventas=Count('id')) \
                                       .order_by('-monto_total')

        ventas_por_metodo_pago_data = [
            {'metodo_pago': item['metodo_pago'],
             'monto_total': float(item['monto_total'] or 0),
             'cantidad_ventas': item['cantidad_ventas']}
            for item in ventas_por_metodo_pago
        ]

        return Response({
            "total_ventas_periodo": float(total_ventas_periodo),
            "total_productos_vendidos_periodo": total_productos_vendidos_periodo,
            "ventas_agrupadas_por_periodo": {
                "label": group_by_label,
                "data": ventas_agrupadas_data
            },
            "productos_mas_vendidos": productos_mas_vendidos_data,
            "ventas_por_usuario": ventas_por_usuario_data,
            "ventas_por_metodo_pago": ventas_por_metodo_pago_data,
        })

# --- NUEVA VISTA PARA MÉTODOS DE PAGO (para cargar el select en el frontend) ---
class PaymentMethodListView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        all_methods = Venta.objects.values_list('metodo_pago', flat=True)

        unique_and_cleaned_methods = set() 
        for method in all_methods:
            if method: 
                cleaned_method = method.strip().title() 
                unique_and_cleaned_methods.add(cleaned_method)

        methods_list = list(unique_and_cleaned_methods)
        
        formatted_methods = sorted([{"value": m, "label": m} for m in methods_list], key=lambda x: x['label'])

        return Response(formatted_methods)


# --- Vistas de DetalleVenta ---
class DetalleVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['venta', 'producto']
