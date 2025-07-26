# BONITO_AMOR/backend/inventario/views.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.views import APIView
from django.db.models import Sum, F
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from rest_framework_simplejwt.views import TokenObtainPairView as SimpleJWTOBPView
from .serializers import (
    ProductoSerializer, CategoriaSerializer, # CategoriaSerializer puede que ya no sea necesario si eliminaste categorías
    VentaSerializer, VentaCreateSerializer,
    DetalleVentaSerializer, UserSerializer, UserCreateSerializer,
    TiendaSerializer, CustomTokenObtainPairSerializer 
)
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda 

User = get_user_model()

# Permisos personalizados
class IsStaffOrAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        return request.user and (request.user.is_staff or request.user.is_superuser)

class IsSuperUser(IsAuthenticated):
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser

# ViewSets
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes = [IsStaffOrAdmin] 
        elif self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] 
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminUser] 
        elif self.action == 'me':
            self.permission_classes = [IsAuthenticated] 
        else:
            self.permission_classes = [IsAdminUser] 
        return [permission() for permission in self.permission_classes]

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = serializer.save()
        requesting_user = self.request.user
        
        if requesting_user.is_authenticated and \
           not requesting_user.is_superuser and \
           requesting_user.tienda: 
            
            user.tienda = requesting_user.tienda 
            user.save()


# Si eliminaste el modelo Categoria, este ViewSet ya no es necesario o debe ser ajustado
class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated] 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] 
        else:
            self.permission_classes = [IsStaffOrAdmin] 
        return [permission() for permission in self.permission_classes]

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all().order_by('nombre')
    serializer_class = TiendaSerializer
    def get_permissions(self):
        if self.action == 'list':
            self.permission_classes = [AllowAny] 
        elif self.action == 'retrieve':
            self.permission_classes = [IsAuthenticated] 
        else:
            self.permission_classes = [IsSuperUser] 
        return [permission() for permission in self.permission_classes]

class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Producto.objects.all().order_by('nombre')
        elif user.tienda: 
            return Producto.objects.filter(tienda=user.tienda).order_by('nombre')
        return Producto.objects.none() 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] 
        else:
            self.permission_classes = [IsStaffOrAdmin] 
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        requesting_user = self.request.user
        
        # CAMBIO CLAVE AQUÍ: Lógica unificada para asignar la tienda
        if not requesting_user.is_authenticated:
            raise serializers.ValidationError({"detail": "Autenticación requerida para crear productos."})
        
        # Si el usuario no tiene una tienda asignada, no puede crear productos.
        # Esto incluye superusuarios que no tienen una tienda asignada a su perfil.
        if not requesting_user.tienda:
            raise serializers.ValidationError({"detail": "No tienes una tienda asignada a tu usuario para crear productos. Por favor, asigna una tienda a tu perfil de usuario en el panel de administración."})
        
        # Si el usuario está autenticado y tiene una tienda, asigna esa tienda al producto
        serializer.save(tienda=requesting_user.tienda)

    def perform_update(self, serializer):
        requesting_user = self.request.user
        instance_tienda = serializer.instance.tienda 

        if requesting_user.is_superuser:
            serializer.save() 
        elif requesting_user.tienda == instance_tienda:
            serializer.save() 
        else:
            raise serializers.ValidationError({"detail": "No tienes permiso para actualizar productos de otra tienda."})


class VentaViewSet(viewsets.ModelViewSet):
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Venta.objects.all().order_by('-fecha_venta')
        elif user.tienda: 
            return Venta.objects.filter(tienda=user.tienda).order_by('-fecha_venta')
        return Venta.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] 
        elif self.action == 'create':
            self.permission_classes = [IsStaffOrAdmin] 
        else: 
            self.permission_classes = [IsAdminUser] 
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def perform_create(self, serializer):
        if not self.request.user.is_superuser and self.request.user.tienda: 
            serializer.save(tienda=self.request.user.tienda)
        else:
            serializer.save() 

class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        elif user.tienda: 
            return DetalleVenta.objects.filter(venta__tienda=user.tienda)
        return DetalleVenta.objects.none()

    def get_permissions(self):
        return [IsAuthenticated()] 

class MetricasVentasViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user = self.request.user
        tienda_queryset = Tienda.objects.all()

        if not user.is_superuser:
            if user.tienda: 
                tienda_queryset = Tienda.objects.filter(id=user.tienda.id)
            else:
                return Response({"detail": "No autorizado para ver métricas de ventas."}, status=status.HTTP_403_FORBIDDEN)

        period = request.query_params.get('period', '7d')
        end_date = timezone.now()
        
        if period == '7d':
            start_date = end_date - timedelta(days=7)
        elif period == '30d':
            start_date = end_date - timedelta(days=30)
        elif period == '90d':
            start_date = end_date - timedelta(days=90)
        elif period == '1y':
            start_date = end_date - timedelta(days=365)
        else: 
            start_date = end_date - timedelta(days=7)

        ventas_filtradas = Venta.objects.filter(
            tienda__in=tienda_queryset,
            fecha_venta__range=[start_date, end_date]
        )

        total_ventas = ventas_filtradas.aggregate(Sum('total'))['total__sum'] or 0
        cantidad_ventas = ventas_filtradas.count()

        productos_vendidos = DetalleVenta.objects.filter(
            venta__in=ventas_filtradas
        ).values('producto__nombre').annotate(
            total_vendido=Sum('cantidad')
        ).order_by('-total_vendido')[:5] 

        response_data = {
            'total_ventas': total_ventas,
            'cantidad_ventas': cantidad_ventas,
            'productos_mas_vendidos': list(productos_vendidos)
        }
        return Response(response_data)

class PaymentMethodListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        payment_methods = [
            {"name": "Efectivo", "value": "Efectivo"},
            {"name": "Tarjeta de Crédito", "value": "Tarjeta de Crédito"},
            {"name": "Tarjeta de Débito", "value": "Tarjeta de Débito"},
            {"name": "Transferencia Bancaria", "value": "Transferencia Bancaria"},
            {"name": "Mercado Pago", "value": "Mercado Pago"},
            {"name": "Otro", "value": "Otro"},
        ]
        return Response(payment_methods)

class CustomTokenObtainPairView(SimpleJWTOBPView):
    serializer_class = CustomTokenObtainPairSerializer

