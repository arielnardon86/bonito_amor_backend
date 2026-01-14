# mi_tienda_backend/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventario.views import (
    ProductoViewSet, CategoriaViewSet, TiendaViewSet, UserViewSet,
    VentaViewSet, DetalleVentaViewSet, MetodoPagoViewSet, CompraViewSet,
    CustomTokenObtainPairView, MetricasAPIView, InventarioMetricsAPIView,
    ArancelMetodoTiendaViewSet, FacturaViewSet, ml_oauth_callback_public_view
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
# Importación condicional de CambioDevolucionViewSet
try:
    from inventario.views import CambioDevolucionViewSet
except (ImportError, AttributeError):
    CambioDevolucionViewSet = None
from rest_framework_simplejwt.views import TokenRefreshView


router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='productos')
router.register(r'categorias', CategoriaViewSet, basename='categorias')
router.register(r'tiendas', TiendaViewSet, basename='tiendas')
router.register(r'users', UserViewSet, basename='users')
router.register(r'ventas', VentaViewSet, basename='ventas')
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalles-venta')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodos-pago')
router.register(r'compras', CompraViewSet, basename='compras')
router.register(r'aranceles-tienda', ArancelMetodoTiendaViewSet, basename='aranceles-tienda') # NUEVA RUTA
router.register(r'facturas', FacturaViewSet, basename='facturas') # NUEVA RUTA
# Registrar CambioDevolucionViewSet solo si existe (migración aplicada)
if CambioDevolucionViewSet is not None:
    router.register(r'cambios-devoluciones', CambioDevolucionViewSet, basename='cambios-devoluciones') # NUEVA RUTA


urlpatterns = [
    path('admin/', admin.site.urls),
    # IMPORTANTE: Ruta manual del callback público DEBE ir ANTES de include(router.urls)
    # para que tenga prioridad sobre las rutas generadas por el router
    # Usamos una vista independiente (@api_view) en lugar de un método del ViewSet
    path('api/tiendas/mercadolibre/callback/', ml_oauth_callback_public_view, name='ml-oauth-callback-public'),
    path('api/', include(router.urls)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/metricas/metrics/', MetricasAPIView.as_view(), name='metricas-ventas-rentabilidad'),
    path('api/inventario/metrics/', InventarioMetricsAPIView.as_view(), name='inventario-metrics'),
]