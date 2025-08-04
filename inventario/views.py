# BONITO_AMOR/backend/inventario/views.py
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value # Make sure to import Value and Q
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from django.utils import timezone
from decimal import Decimal # Import Decimal

from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer
)
from .filters import VentaFilter # Make sure this line is present and correct


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Allows a superuser to view all products.
        if self.request.user.is_superuser:
            return Producto.objects.all()

        # If not a superuser, they can only see products from their assigned store.
        if self.request.user.tienda:
            return Producto.objects.filter(tienda=self.request.user.tienda).order_by('nombre')
        
        # If no store is assigned, no products are visible.
        return Producto.objects.none()

    # Custom action to search for a product by its barcode
    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        barcode = request.query_params.get('barcode', None)
        if not barcode:
            return Response({'error': 'Barcode parameter missing.'}, status=status.HTTP_400_BAD_REQUEST)

        tienda_slug = request.query_params.get('tienda_slug', None)
        if not tienda_slug:
            return Response({'error': 'Store parameter missing.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({'error': 'Store not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            producto = Producto.objects.get(codigo_barras=barcode, tienda=tienda)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({'error': 'Product not found in this store.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Restricts creation, update, and deletion
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
            return Response({"error": "This sale has already been voided."}, status=status.HTTP_400_BAD_REQUEST)
        
        venta.anulada = True
        venta.save()

        # Restore product stock
        detalles = DetalleVenta.objects.filter(venta=venta)
        for detalle in detalles:
            if detalle.producto and not detalle.anulado_individualmente:
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
        
        return Response({"status": "Sale voided successfully"}, status=status.HTTP_200_OK)

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

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        detalle = get_object_or_404(DetalleVenta, pk=pk)

        # Check if the user has permission to void this detail
        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser:
            return Response({"error": "You do not have permission to void this sales detail."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "This sales detail has already been individually voided."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "Cannot void a detail from an already voided sale."}, status=status.HTTP_400_BAD_REQUEST)

        # Restore product stock
        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            detalle.anulado_individualmente = True
            detalle.save()
            
            # Recalculate total of the main sale
            venta = detalle.venta
            total_recalculado = sum(d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente)
            venta.total = total_recalculado
            venta.save()
            
            return Response({"status": "Sales detail voided successfully and stock restored."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()
            return Response({"status": "Sales detail voided successfully, no stock to restore."}, status=status.HTTP_200_OK)


class VentaPorUsuarioYFecha(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        fecha_str = request.query_params.get('fecha')
        if not fecha_str:
            return Response({"error": "The 'fecha' parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha_obj = timezone.datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        ventas = Venta.objects.filter(
            usuario=request.user,
            fecha_venta__date=fecha_obj
        )
        serializer = VentaSerializer(ventas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

# --- NEW VIEW FOR SALES METRICS ---
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
            return Response({"error": "The 'tienda_slug' parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({"error": "Store not found."}, status=status.HTTP_404_NOT_FOUND)

        # Base queryset for store sales
        ventas_queryset = Venta.objects.filter(tienda=tienda, anulada=False)

        # Apply date filters
        if year:
            ventas_queryset = ventas_queryset.filter(fecha_venta__year=year)
        if month:
            ventas_queryset = ventas_queryset.filter(fecha_venta__month=month)
        if day:
            ventas_queryset = ventas_queryset.filter(fecha_venta__day=day)

        # Apply seller and payment method filters
        if seller_id:
            ventas_queryset = ventas_queryset.filter(usuario__id=seller_id)
        if payment_method:
            ventas_queryset = ventas_queryset.filter(metodo_pago=payment_method)

        # 1. Total sales in the period
        total_ventas_periodo = ventas_queryset.aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.00'))))['total']

        # 2. Total products sold in the period
        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset,
            anulado_individualmente=False
        ).aggregate(total=Coalesce(Sum('cantidad'), Value(0)))['total']

        # 3. Sales grouped by period (day, month, hour)
        period_label = "Period"
        if day: # Group by hour
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractHour('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Hour of the Day"
        elif month: # Group by day
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractDay('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Day of the Month"
        elif year: # Group by month
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractMonth('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Month of the Year"
        else: # Group by year (if nothing else is specified)
            ventas_agrupadas_por_periodo = ventas_queryset.annotate(
                periodo=ExtractYear('fecha_venta')
            ).values('periodo').annotate(
                total_ventas=Coalesce(Sum('total'), Value(Decimal('0.00')))
            ).order_by('periodo')
            period_label = "Year"

        # 4. Top selling products
        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset,
            anulado_individualmente=False
        ).values('producto__nombre').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0))
        ).order_by('-cantidad_total')[:5] # Top 5

        # 5. Sales by user
        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' 
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(Decimal('0.0'))),
            cantidad_ventas=Coalesce(Count('id', filter=Q(total__gt=Decimal('0.00'))), Value(0)) 
        ).order_by('-monto_total_vendido')

        # 6. Sales by payment method
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

