# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, F, Count, Value
from django.db.models.functions import Coalesce # Para manejar valores nulos en agregaciones
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView # Importar APIView

from .models import (
    Producto, Categoria, Tienda, User, Venta, DetalleVenta, # Cambiado Usuario a User
    MetodoPago # Asegúrate de importar MetodoPago
)
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer, # Cambiado UsuarioSerializer a UserSerializer
    VentaSerializer, DetalleVentaSerializer,
    MetodoPagoSerializer, # Asegúrate de importar MetodoPagoSerializer
    VentaCreateSerializer # Para la creación de ventas
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
        queryset = super().get_queryset()
        tienda_slug = self.request.query_params.get('tienda_slug')
        if tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
        return queryset

    def perform_create(self, serializer):
        # Asigna automáticamente la tienda del usuario autenticado si no se proporciona
        if not serializer.validated_data.get('tienda'):
            if self.request.user.is_authenticated and self.request.user.tienda:
                serializer.save(tienda=self.request.user.tienda)
            else:
                # Si el usuario no tiene tienda y no se proporcionó, lanzar error
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
            # Busca el producto por código de barras y filtra por tienda
            producto = Producto.objects.get(codigo_barras=barcode, tienda__nombre=tienda_slug)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({"error": "Producto no encontrado con ese código de barras en la tienda especificada."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def imprimir_etiquetas(self, request):
        # Lógica para generar etiquetas, si es necesario.
        # Esto podría devolver una URL a un PDF generado o los datos para el frontend.
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
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nombre', 'direccion']
    ordering_fields = ['nombre', 'fecha_creacion']

class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username') # Cambiado de Usuario a User
    serializer_class = UserSerializer # Cambiado de UsuarioSerializer a UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']

class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all().order_by('-fecha_venta')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'fecha_venta': ['gte', 'lte', 'exact', 'date__gte', 'date__lte', 'date'],
        'tienda': ['exact'],
        'metodo_pago': ['exact'],
        'total': ['gte', 'lte'],
    }
    ordering_fields = ['fecha_venta', 'total']

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtra por la tienda del usuario si no es superusuario
        if not self.request.user.is_superuser and self.request.user.tienda:
            queryset = queryset.filter(tienda=self.request.user.tienda)
        
        # Filtrar por tienda_slug si se proporciona en los parámetros de consulta
        tienda_slug = self.request.query_params.get('tienda_slug')
        if tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
        
        return queryset

    def perform_create(self, serializer):
        # La tienda ya debería venir en validated_data desde el frontend
        # Si por alguna razón no viene, se puede intentar asignar desde el usuario autenticado
        if not serializer.validated_data.get('tienda'):
            if self.request.user.is_authenticated and self.request.user.tienda:
                serializer.save(tienda=self.request.user.tienda)
            else:
                raise serializers.ValidationError({"tienda": "La tienda es requerida para crear una venta."})
        else:
            serializer.save()

class DetalleVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['venta', 'producto']
    ordering_fields = ['cantidad', 'precio_unitario']

# --- NUEVO ViewSet: MetodoPagoViewSet ---
class MetodoPagoViewSet(viewsets.ModelViewSet):
    """
    API endpoint que permite a los métodos de pago ser vistos o editados.
    """
    queryset = MetodoPago.objects.all().order_by('nombre')
    serializer_class = MetodoPagoSerializer
    permission_classes = [IsAuthenticated] # O permisos más restrictivos si es necesario

    def get_queryset(self):
        queryset = super().get_queryset()
        # Puedes añadir un filtro por tienda si los métodos de pago son específicos de la tienda
        tienda_slug = self.request.query_params.get('tienda_slug')
        if tienda_slug:
            # Aquí asumo que MetodoPago no tiene una relación directa con Tienda.
            # Si lo tuviera, la lógica sería similar a ProductoViewSet.
            # Si los métodos de pago son globales, este filtro no aplicaría.
            # Por ahora, se mantiene sin filtrar por tienda si el modelo MetodoPago no tiene 'tienda'.
            pass 
        return queryset

# --- NUEVA APIView: VentasMetricasView ---
class VentasMetricasView(APIView):
    """
    API para obtener métricas de ventas por tienda, con filtros opcionales.
    Requiere 'tienda_slug' como parámetro de consulta.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug')
        year_filter = request.query_params.get('year')
        month_filter = request.query_params.get('month')
        day_filter = request.query_params.get('day')
        seller_id_filter = request.query_params.get('seller_id')
        payment_method_filter = request.query_params.get('payment_method')

        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_slug) # Usar 'nombre' para el slug
        except Tienda.DoesNotExist:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Construir el queryset base para las ventas
        ventas_queryset = Venta.objects.filter(tienda=tienda_obj)

        # Aplicar filtros de fecha
        if year_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__year=year_filter)
        if month_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__month=month_filter)
        if day_filter:
            ventas_queryset = ventas_queryset.filter(fecha_venta__day=day_filter)
        
        # Aplicar filtro de vendedor (asumiendo que Venta tiene un campo 'vendedor' o similar)
        # Si Venta no tiene un campo directo a User, necesitarás un campo en Venta o un StockMovimiento
        # Por ahora, asumo que Venta tiene un campo 'usuario' o 'vendedor' que apunta a User.
        # Si no es así, esta parte de la lógica necesitará ser ajustada.
        if seller_id_filter:
            ventas_queryset = ventas_queryset.filter(usuario_id=seller_id_filter) # Asumiendo campo 'usuario_id' en Venta

        # Aplicar filtro de método de pago
        if payment_method_filter:
            ventas_queryset = ventas_queryset.filter(metodo_pago=payment_method_filter)

        # --- Métricas principales ---
        total_ventas_periodo = ventas_queryset.aggregate(total=Coalesce(Sum('total'), Value(0.0)))['total']

        total_productos_vendidos_periodo = DetalleVenta.objects.filter(
            venta__in=ventas_queryset # Filtra detalles de venta para las ventas del queryset filtrado
        ).aggregate(total=Coalesce(Sum('cantidad'), Value(0)))['total']

        # --- Ventas agrupadas por período (para el Line Chart) ---
        # Determinar el nivel de agrupación (día, mes, año)
        if day_filter: # Si hay filtro de día, agrupar por hora (no implementado en el frontend, pero sería lo más granular)
            # Para simplificar, si hay día, se agrupa por día.
            period_label = "Día"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__date').annotate(
                total_monto=Coalesce(Sum('total'), Value(0.0))
            ).order_by('fecha_venta__date').values(fecha=F('fecha_venta__date'), total_monto=F('total_monto'))
        elif month_filter: # Si hay filtro de mes, agrupar por día
            period_label = "Día"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__date').annotate(
                total_monto=Coalesce(Sum('total'), Value(0.0))
            ).order_by('fecha_venta__date').values(fecha=F('fecha_venta__date'), total_monto=F('total_monto'))
        elif year_filter: # Si hay filtro de año, agrupar por mes
            period_label = "Mes"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__month', 'fecha_venta__year').annotate(
                total_monto=Coalesce(Sum('total'), Value(0.0))
            ).order_by('fecha_venta__year', 'fecha_venta__month').values(
                fecha=F('fecha_venta__month'), # Usar el número del mes
                year=F('fecha_venta__year'),
                total_monto=F('total_monto')
            )
            # Formatear el mes para el frontend (ej. "Enero", "Febrero")
            # Esto se puede hacer en el frontend o aquí. Lo haremos en el frontend para mantener la API limpia.
        else: # Si no hay filtros de fecha, agrupar por año
            period_label = "Año"
            ventas_agrupadas_por_periodo = ventas_queryset.values('fecha_venta__year').annotate(
                total_monto=Coalesce(Sum('total'), Value(0.0))
            ).order_by('fecha_venta__year').values(fecha=F('fecha_venta__year'), total_monto=F('total_monto'))

        # --- Productos más vendidos (top 5 por cantidad y monto) ---
        productos_mas_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_queryset
        ).values('producto__nombre', 'producto__talle').annotate(
            cantidad_total=Coalesce(Sum('cantidad'), Value(0)),
            monto_total=Coalesce(Sum(F('cantidad') * F('precio_unitario')), Value(0.0))
        ).order_by('-cantidad_total')[:5]

        # --- Ventas por usuario (vendedor) ---
        # Asumiendo que Venta tiene un ForeignKey a User (vendedor)
        ventas_por_usuario = ventas_queryset.values(
            'usuario__username', 'usuario__first_name', 'usuario__last_name' # Asumiendo que Venta tiene un campo 'usuario'
        ).annotate(
            monto_total_vendido=Coalesce(Sum('total'), Value(0.0)),
            cantidad_ventas=Coalesce(Count('id'), Value(0))
        ).order_by('-monto_total_vendido')

        # --- Ventas por método de pago ---
        ventas_por_metodo_pago = ventas_queryset.values('metodo_pago').annotate(
            monto_total=Coalesce(Sum('total'), Value(0.0)),
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
