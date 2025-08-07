# mi_tienda_backend/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventario.views import (
    ProductoViewSet, CategoriaViewSet, TiendaViewSet, UserViewSet,  # <-- Se ha añadido UserViewSet
    VentaViewSet, DetalleVentaViewSet, MetodoPagoViewSet, CompraViewSet,
    CustomTokenObtainPairView, MetricasAPIView
)
from rest_framework_simplejwt.views import TokenRefreshView


router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='productos')
router.register(r'categorias', CategoriaViewSet, basename='categorias')
router.register(r'tiendas', TiendaViewSet, basename='tiendas')
router.register(r'users', UserViewSet, basename='users') # <-- Se ha añadido el router para UserViewSet
router.register(r'ventas', VentaViewSet, basename='ventas')
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalles-venta')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodos-pago')
router.register(r'compras', CompraViewSet, basename='compras')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/metricas/metrics/', MetricasAPIView.as_view(), name='metricas-ventas-rentabilidad'),
]