# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Count, Value, Q
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
from .filters import VentaFilter # Importar el nuevo filtro

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
        queryset = super().get_queryset()
        tienda_slug = self.request.query_params.get('tienda_slug')
        if tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
        return queryset

    def perform_create(self, serializer):
        if not serializer.validated_data.get('tienda'):
            if self.request.user.is_authenticated and self.request.user.tienda:
                serializer.save(tienda=self.request.user.tienda)
            else:
                raise serializers.ValidationError({"tienda": "La tienda es requerida o el usuario no tiene una tienda asignada."})
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        barcode = request.query_params.get('barcode', None)
        tienda_slug = request.query_params.get('tienda_slug', None)

        if not barcode:
            return Response({"error": "Parámetro 'barcode' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            producto = Producto.objects.get(codigo_barras=barcode, tienda__nombre=tienda_slug)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({"error": "Producto no encontrado con ese código de barras en la tienda especificada."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def imprimir_etiquetas(self, request):
        return Response({"message": "Endpoint para imprimir etiquetas."}, status=status.HTTP_200_OK)

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre', 'descripcion']
    ordering_fields = ['nombre', 'fecha_creacion']

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all().order_by('nombre')
    serializer_class = TiendaSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre', 'direccion']
    ordering_fields = ['nombre', 'fecha_creacion']

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

class UserViewSet(viewsets.ModelViewSet): 
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        if request.user.is_authenticated:
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        return Response({"detail": "No autenticado."}, status=status.HTTP_401_UNAUTHORIZED)


class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().order_by('-fecha_venta')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = VentaFilter 
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser and self.request.user.tienda:
            queryset = queryset.filter(tienda=self.request.user.tienda)
        
        tienda_slug = self.request.query_params.get('tienda_slug')
        if tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
        
        return queryset

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        """
        Anula una venta completa y revierte el stock de todos los productos.
        Esto se logra anulando cada detalle de la venta.
        Solo permitido para superusuarios.
        """
        if not request.user.is_superuser:
            return Response({"detail": "No tienes permisos para anular ventas."}, status=status.HTTP_403_FORBIDDEN)

        try:
            venta = self.get_object() # Obtiene la venta por PK
            tienda_slug = request.query_params.get('tienda_slug')

            if not tienda_slug:
                return Response({"error": "El parámetro 'tienda_slug' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

            if str(venta.tienda.nombre) != tienda_slug:
                 return Response({"detail": "La venta no pertenece a la tienda especificada."}, status=status.HTTP_400_BAD_REQUEST)

            if venta.anulada:
                return Response({"detail": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

            # Iterar sobre una copia de los detalles para evitar problemas al eliminarlos
            detalles_a_anular = list(venta.detalles.all())
            for detalle in detalles_a_anular:
                producto = detalle.producto
                producto.stock += detalle.cantidad # Revertir la cantidad completa
                producto.save()
                detalle.delete() # Eliminar el detalle de venta

            venta.total = Decimal('0.00') # El total de la venta es 0
            venta.anulada = True # Marcar la venta como anulada
            venta.save()
            
            return Response(VentaSerializer(venta).data, status=status.HTTP_200_OK)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Capturar cualquier otra excepción y devolver un mensaje de error genérico
            return Response({"detail": f"Error interno al anular la venta: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        """
        Anula una cantidad específica de un producto en un detalle de venta
        y revierte el stock.
        Solo permitido para superusuarios.
        """
        if not request.user.is_superuser:
            return Response({"detail": "No tienes permisos para anular detalles de venta."}, status=status.HTTP_403_FORBIDDEN)

        try:
            venta = self.get_object() # Obtiene la venta por PK
            detalle_id = request.data.get('detalle_id')
            cantidad_a_anular = request.data.get('cantidad_a_anular')
            tienda_slug = request.query_params.get('tienda_slug')

            if not tienda_slug:
                return Response({"error": "El parámetro 'tienda_slug' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
            if str(venta.tienda.nombre) != tienda_slug:
                 return Response({"detail": "La venta no pertenece a la tienda especificada."}, status=status.HTTP_400_BAD_REQUEST)

            if not detalle_id or not cantidad_a_anular:
                return Response({"error": "Los parámetros 'detalle_id' y 'cantidad_a_anular' son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                cantidad_a_anular = int(cantidad_a_anular)
                if cantidad_a_anular <= 0:
                    return Response({"error": "La cantidad a anular debe ser mayor que cero."}, status=status.HTTP_400_BAD_REQUEST)
            except ValueError:
                return Response({"error": "La cantidad a anular debe ser un número entero válido."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                detalle = venta.detalles.get(id=detalle_id)
            except DetalleVenta.DoesNotExist:
                return Response({"detail": "Detalle de venta no encontrado en esta venta."}, status=status.HTTP_404_NOT_FOUND)

            if detalle.cantidad < cantidad_a_anular:
                return Response({"error": f"No se puede anular {cantidad_a_anular} unidades. Solo quedan {detalle.cantidad} en este detalle."}, status=status.HTTP_400_BAD_REQUEST)

            # Revertir stock del producto
            producto = detalle.producto
            producto.stock += cantidad_a_anular
            producto.save()

            # Ajustar la cantidad en el detalle de venta
            detalle.cantidad -= cantidad_a_anular
            detalle.subtotal = detalle.precio_unitario * detalle.cantidad
            detalle.save()

            # Si la cantidad del detalle llega a cero, eliminar el detalle
            if detalle.cantidad == 0:
                detalle.delete()
            
            # Recalcular el total de la venta
            venta.total = sum(d.subtotal for d in venta.detalles.all())
            # Si no quedan detalles, la venta se considera anulada
            if venta.detalles.count() == 0:
                venta.anulada = True
            venta.save()

            return Response(VentaSerializer(venta).data, status=status.HTTP_200_OK)
        except Venta.DoesNotExist:
            return Response({"detail": "Venta no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": f"Error al anular el detalle de venta: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DetalleVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['venta', 'producto']
    ordering_fields = ['cantidad', 'precio_unitario']

class PaymentMethodListView(APIView):
    """
    API para listar todos los métodos de pago activos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        metodos_pago = MetodoPago.objects.filter(is_active=True).order_by('nombre')
        serializer = MetodoPagoSerializer(metodos_pago, many=True)
        return Response(serializer.data)

class MetricasVentasViewSet(viewsets.ViewSet):
    """
    API para obtener métricas de ventas por tienda, con filtros opcionales.
    Requiere 'tienda_slug' como parámetro de consulta.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        tienda_slug = request.query_params.get('tienda_slug')
        year_filter = request.query_params.get('year')
        month_filter = request.query_params.get('month')
        day_filter = request.query_params.get('day')
        seller_id_filter = request.query_params.get('seller_id')
        payment_method_filter = request.query_params.get('payment_method')

        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        ventas_queryset = Venta.objects.filter(tienda=tienda_obj)

        if year_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__year=year_filter)
        if month_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__month=month_filter)
        if day_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__day=day_filter)
        
        if seller_id_filter:
            ventas_queryset = ventas_queryset.filter(usuario_id=seller_id_filter) 

        # ... (resto de la lógica de métricas) ...
        total_ventas_periodo = ventas_queryset.aggregate(total=Coalesce(Sum('total'), Value(Decimal('0.0'))))['total']

        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset
        ).aggregate(total=Coalesce(Sum('cantidad'), Value(0)))['total']

        if day_filter: 
            period_label = "Día"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__date').annotate(
                total_monto=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('fecha_venta__date').values(fecha=F('fecha_venta__date'), total_monto=F('total_monto'))
        elif month_filter: 
            period_label = "Día"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__date').annotate(
                total_monto=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('fecha_venta__date').values(fecha=F('fecha_venta__date'), total_monto=F('total_monto'))
        elif year_filter: 
            period_label = "Mes"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__month', 'fecha_venta__year').annotate(
                total_monto=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('fecha_venta__year', 'fecha_venta__month').values(
                fecha=F('fecha_venta__month'), 
                year=F('fecha_venta__year'),
                total_monto=F('total_monto')
            )
        else: 
            period_label = "Año"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__year').annotate(
                total_monto=Coalesce(Sum('total'), Value(Decimal('0.0')))
            ).order_by('fecha_venta__year').values(fecha=F('fecha_venta__year'), total_monto=F('total_monto'))

        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset
        ).values('producto__nombre', 'producto__talle').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0)),
            monto_total=Coalesce(Sum(F('cantidad') * F('precio_unitario')), Value(Decimal('0.0')))
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

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Vista personalizada para obtener tokens JWT.
    Utiliza CustomTokenObtainPairSerializer para incluir datos adicionales del usuario.
    """
    serializer_class = CustomTokenObtainPairSerializer
