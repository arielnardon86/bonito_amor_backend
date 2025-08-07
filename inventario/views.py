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
from django.utils import timezone
from decimal import Decimal 

from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra 
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer 
)
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Producto.objects.all()

        tienda_slug = self.request.query_params.get('tienda_slug', None)
        if tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
        else:
            if not user.is_superuser and user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
            elif not user.is_superuser and not user.tienda:
                return Producto.objects.none()

        return queryset.order_by('nombre')

    @action(detail=False, methods=['get'])
    def productos_sin_codigo(self, request):
        productos = self.get_queryset().filter(codigo_barras__isnull=True)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def productos_por_codigo(self, request):
        codigo = request.query_params.get('codigo_barras', None)
        if codigo:
            try:
                producto = self.get_queryset().get(codigo_barras=codigo)
                serializer = self.get_serializer(producto)
                return Response(serializer.data)
            except Producto.DoesNotExist:
                return Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"detail": "Código de barras no proporcionado."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def productos_con_stock(self, request):
        productos = self.get_queryset().filter(stock__gt=0)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)


# Vistas de Categoría, Tienda, User, etc.
# ... (el resto de tus vistas) ...


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# --- NUEVAS VISTAS PARA REGISTRO DE COMPRAS SIMPLIFICADAS ---


class CompraViewSet(viewsets.ModelViewSet):
    serializer_class = CompraSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        user = self.request.user
        queryset = Compra.objects.all()
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug)
            return queryset.order_by('-fecha_compra')
        elif user.tienda:
            return queryset.filter(tienda=user.tienda).order_by('-fecha_compra')
        return Compra.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return CompraCreateSerializer
        return CompraSerializer
    
    def perform_create(self, serializer):
        tienda_obj = None
        if not self.request.user.is_superuser:
            tienda_obj = self.request.user.tienda
        
        serializer.save(usuario=self.request.user, tienda=tienda_obj)