# inventario/views.py - CÓDIGO COMPLETO Y CORREGIDO
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
from decimal import Decimal 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import DecimalField 
from django.db import close_old_connections # <-- Importado para el fix de conexión

# CAMBIO 1: Importar ArancelMetodoTienda
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda 
# CAMBIO 2: Importar ArancelMetodoTiendaSerializer
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer, ArancelMetodoTiendaSerializer 
)
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