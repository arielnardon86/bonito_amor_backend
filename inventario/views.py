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
    ProductoSerializer, CategoriaSerializer,
    VentaSerializer, VentaCreateSerializer,
    DetalleVentaSerializer, UserSerializer, UserCreateSerializer,
    TiendaSerializer, CustomTokenObtainPairSerializer # Importa CustomTokenObtainPairSerializer
)
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda, UserProfile

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
            self.permission_classes = [AllowAny] # Permitir registro de usuarios
        elif self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Solo usuarios autenticados pueden ver la lista/detalle
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAdminUser] # Solo administradores pueden modificar/eliminar
        elif self.action == 'me':
            self.permission_classes = [IsAuthenticated] # Solo el propio usuario autenticado
        else:
            self.permission_classes = [IsAdminUser] # Por defecto, requiere admin
        return [permission() for permission in self.permission_classes]

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = serializer.save()
        # Asegura que se cree un UserProfile para el nuevo usuario si no existe
        UserProfile.objects.get_or_create(user=user)


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated] # Requiere autenticación para todas las acciones

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Todos los autenticados pueden listar/ver
        else:
            self.permission_classes = [IsStaffOrAdmin] # Solo staff/admin pueden crear/actualizar/eliminar
        return [permission() for permission in self.permission_classes]

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all().order_by('nombre')
    serializer_class = TiendaSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Todos los autenticados pueden listar/ver
        else:
            self.permission_classes = [IsSuperUser] # Solo superusuarios pueden crear/actualizar/eliminar
        return [permission() for permission in self.permission_classes]

class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Producto.objects.all().order_by('nombre')
        elif hasattr(user, 'profile') and user.profile.tienda:
            return Producto.objects.filter(tienda=user.profile.tienda).order_by('nombre')
        return Producto.objects.none() # Si no es superuser y no tiene tienda asignada, no ve productos

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Todos los autenticados pueden listar/ver
        else:
            self.permission_classes = [IsStaffOrAdmin] # Solo staff/admin pueden crear/actualizar/eliminar
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        # Asegura que el producto se cree en la tienda del usuario actual si no es superuser
        if not self.request.user.is_superuser and hasattr(self.request.user, 'profile') and self.request.user.profile.tienda:
            serializer.save(tienda=self.request.user.profile.tienda)
        else:
            serializer.save() # Si es superuser o no tiene tienda asignada, permite especificar la tienda

class VentaViewSet(viewsets.ModelViewSet):
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Venta.objects.all().order_by('-fecha_venta')
        elif hasattr(user, 'profile') and user.profile.tienda:
            return Venta.objects.filter(tienda=user.profile.tienda).order_by('-fecha_venta')
        return Venta.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Todos los autenticados pueden listar/ver
        elif self.action == 'create':
            self.permission_classes = [IsStaffOrAdmin] # Staff/admin pueden crear ventas
        else: # update, partial_update, destroy
            self.permission_classes = [IsAdminUser] # Solo administradores pueden modificar/eliminar
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    def perform_create(self, serializer):
        # Asegura que la venta se cree en la tienda del usuario actual si no es superuser
        if not self.request.user.is_superuser and hasattr(self.request.user, 'profile') and self.request.user.profile.tienda:
            serializer.save(tienda=self.request.user.profile.tienda)
        else:
            serializer.save() # Si es superuser o no tiene tienda asignada, permite especificar la tienda

class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        elif hasattr(user, 'profile') and user.profile.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.profile.tienda)
        return DetalleVenta.objects.none()

    def get_permissions(self):
        return [IsAuthenticated()] # Solo usuarios autenticados pueden ver detalles de venta

class MetricasVentasViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user = request.user
        tienda_queryset = Tienda.objects.all()

        if not user.is_superuser:
            if hasattr(user, 'profile') and user.profile.tienda:
                tienda_queryset = Tienda.objects.filter(id=user.profile.tienda.id)
            else:
                return Response({"detail": "No autorizado para ver métricas de ventas."}, status=status.HTTP_403_FORBIDDEN)

        # Filtro por período de tiempo (ej: últimos 7 días, 30 días, etc.)
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
        else: # Por defecto, últimos 7 días
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
        ).order_by('-total_vendido')[:5] # Top 5 productos más vendidos

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

# NUEVA VISTA: CustomTokenObtainPairView
class CustomTokenObtainPairView(SimpleJWTOBPView):
    serializer_class = CustomTokenObtainPairSerializer

