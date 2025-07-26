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
    TiendaSerializer, CustomTokenObtainPairSerializer 
)
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda, UserProfile

User = get_user_model()

# Permisos personalizados
class IsStaffOrAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        # Un usuario es staff o superusuario
        return request.user and (request.user.is_staff or request.user.is_superuser)

class IsSuperUser(IsAuthenticated):
    def has_permission(self, request, view):
        # Un usuario es superusuario
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
            # CAMBIO CLAVE AQUÍ: Solo usuarios staff o superusuarios pueden crear nuevos usuarios
            self.permission_classes = [IsStaffOrAdmin] 
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
        # Guarda el nuevo usuario
        user = serializer.save()
        
        # Obtiene o crea el UserProfile para el nuevo usuario
        user_profile, created = UserProfile.objects.get_or_create(user=user)

        # Lógica para asignar la tienda al nuevo usuario
        requesting_user = self.request.user
        
        # Asegurarse de que el usuario que está creando esté autenticado
        if requesting_user.is_authenticated:
            # Solo si el usuario que está creando NO es un superusuario
            # Y si el usuario que está creando tiene un perfil
            # Y si ese perfil tiene una tienda asignada
            if not requesting_user.is_superuser and \
               hasattr(requesting_user, 'profile') and \
               requesting_user.profile.tienda:
                user_profile.tienda = requesting_user.profile.tienda
                user_profile.save()
                # print(f"DEBUG: Asignada tienda {requesting_user.profile.tienda.nombre} al nuevo usuario {user.username}") # Para depuración
            # else:
                # print(f"DEBUG: No se asignó tienda al nuevo usuario {user.username}. Superusuario: {requesting_user.is_superuser}, Tiene perfil: {hasattr(requesting_user, 'profile')}, Tienda del creador: {requesting_user.profile.tienda if hasattr(requesting_user, 'profile') else 'N/A'}") # Para depuración


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by('nombre')
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated] 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] # Todos los autenticados pueden listar/ver
        else:
            self.permission_classes = [IsStaffOrAdmin] # Solo staff/admin pueden crear/actualizar/eliminar
        return [permission() for permission in self.permission_classes]

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all().order_by('nombre')
    serializer_class = TiendaSerializer
    # Permitir acceso público a la lista de tiendas
    def get_permissions(self):
        if self.action == 'list':
            self.permission_classes = [AllowAny] # Cualquiera puede listar tiendas
        elif self.action == 'retrieve':
            self.permission_classes = [IsAuthenticated] # Autenticados pueden ver detalle de una tienda
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
        return Producto.objects.none() 

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            self.permission_classes = [IsAuthenticated] 
        else:
            self.permission_classes = [IsStaffOrAdmin] 
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        if not self.request.user.is_superuser and hasattr(self.request.user, 'profile') and self.request.user.profile.tienda:
            serializer.save(tienda=self.request.user.profile.tienda)
        else:
            serializer.save() 

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
        if not self.request.user.is_superuser and hasattr(self.request.user, 'profile') and self.request.user.profile.tienda:
            serializer.save(tienda=self.request.user.profile.tienda)
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
        elif hasattr(user, 'profile') and user.profile.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.profile.tienda)
        return DetalleVenta.objects.none()

    def get_permissions(self):
        return [IsAuthenticated()] 

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

