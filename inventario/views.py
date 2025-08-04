# BONITO_AMOR/backend/inventario/views.py
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer
)

class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Permite a un superusuario ver todos los productos.
        if self.request.user.is_superuser:
            return Producto.objects.all()

        # Si no es superusuario, sólo puede ver los productos de su tienda asignada.
        if self.request.user.tienda:
            return Producto.objects.filter(tienda=self.request.user.tienda).order_by('nombre')
        
        # Si no tiene tienda asignada, no ve ningún producto.
        return Producto.objects.none()

    # Acción personalizada para buscar un producto por su código de barras
    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        barcode = request.query_params.get('barcode', None)
        if not barcode:
            return Response({'error': 'Parámetro de código de barras faltante.'}, status=status.HTTP_400_BAD_REQUEST)

        tienda_slug = request.query_params.get('tienda_slug', None)
        if not tienda_slug:
            return Response({'error': 'Parámetro de tienda faltante.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            return Response({'error': 'Tienda no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            producto = Producto.objects.get(codigo_barras=barcode, tienda=tienda)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({'error': 'Producto no encontrado en esta tienda.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Restringe la creación, actualización y eliminación
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

    # CAMBIO CLAVE AQUÍ: Modificar perform_create para la respuesta
    def perform_create(self, serializer):
        # Guarda la venta, lo que ejecuta el método create de VentaCreateSerializer
        venta_instance = serializer.save(usuario=self.request.user)
        
        # Después de que la venta y sus detalles se han creado,
        # recargamos la instancia de la venta con los detalles precargados
        # para asegurar que el VentaSerializer pueda acceder a ellos.
        # Esto es crucial para la serialización de la respuesta.
        venta_with_details = Venta.objects.select_related('tienda', 'usuario').prefetch_related('detalles__producto').get(id=venta_instance.id)
        
        # Establecemos la instancia serializada para la respuesta
        # Esto es lo que `serializer.data` usará para construir la respuesta HTTP
        serializer.instance = venta_with_details


    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        venta.anulada = True
        venta.save()

        # Restaurar el stock de los productos
        detalles = DetalleVenta.objects.filter(venta=venta)
        for detalle in detalles:
            if detalle.producto and not detalle.anulado_individualmente:
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
        
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

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

        # Comprobar si el usuario tiene permiso para anular este detalle
        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser:
            return Response({"error": "No tienes permiso para anular este detalle de venta."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "No se puede anular un detalle de una venta que ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        # Restaurar el stock del producto
        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            detalle.anulado_individualmente = True
            detalle.save()
            
            # Recalcular el total de la venta principal
            venta = detalle.venta
            total_recalculado = sum(d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente)
            venta.total = total_recalculado
            venta.save()
            
            return Response({"status": "Detalle de venta anulado con éxito y stock restaurado."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()
            return Response({"status": "Detalle de venta anulado con éxito, sin stock que restaurar."}, status=status.HTTP_200_OK)


class VentaPorUsuarioYFecha(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        fecha_str = request.query_params.get('fecha')
        if not fecha_str:
            return Response({"error": "Se requiere el parámetro 'fecha'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            fecha_obj = timezone.datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Formato de fecha inválido. Usa YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        ventas = Venta.objects.filter(
            usuario=request.user,
            fecha_venta__date=fecha_obj
        )
        serializer = VentaSerializer(ventas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

