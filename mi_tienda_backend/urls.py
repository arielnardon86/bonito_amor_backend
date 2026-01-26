# mi_tienda_backend/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventario.views import (
    ProductoViewSet, CategoriaViewSet, TiendaViewSet, UserViewSet,
    VentaViewSet, DetalleVentaViewSet, MetodoPagoViewSet, CompraViewSet,
    CustomTokenObtainPairView, MetricasAPIView, InventarioMetricsAPIView,
    ArancelMetodoTiendaViewSet, FacturaViewSet
)
# Importación condicional de ArancelMercadoLibreViewSet (puede no existir si la migración no se ha aplicado)
try:
    from inventario.views import ArancelMercadoLibreViewSet
except (ImportError, AttributeError) as e:
    ArancelMercadoLibreViewSet = None
    print(f"⚠️ Warning: No se pudo importar ArancelMercadoLibreViewSet: {e}")
# Importación condicional del callback público de ML
try:
    from inventario.views import ml_oauth_callback_public_view
except (ImportError, AttributeError) as e:
    ml_oauth_callback_public_view = None
    print(f"⚠️ Warning: No se pudo importar ml_oauth_callback_public_view: {e}")
from rest_framework.decorators import api_view
from rest_framework.response import Response
from inventario.views import verificar_database_config
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
# Registrar ArancelMercadoLibreViewSet solo si existe (migración aplicada)
if ArancelMercadoLibreViewSet is not None:
    router.register(r'aranceles-ml', ArancelMercadoLibreViewSet, basename='aranceles-ml') # NUEVA RUTA
else:
    print("⚠️ Warning: ArancelMercadoLibreViewSet no disponible, la ruta /api/aranceles-ml/ no estará disponible. Aplica la migración 0019_arancel_mercado_libre.")
router.register(r'facturas', FacturaViewSet, basename='facturas') # NUEVA RUTA
# Registrar CambioDevolucionViewSet solo si existe (migración aplicada)
if CambioDevolucionViewSet is not None:
    router.register(r'cambios-devoluciones', CambioDevolucionViewSet, basename='cambios-devoluciones') # NUEVA RUTA


urlpatterns = [
    path('admin/', admin.site.urls),
]

# Agregar ruta del callback público solo si la vista está disponible
if ml_oauth_callback_public_view is not None:
    urlpatterns.append(
        path('api/tiendas/mercadolibre/callback/', ml_oauth_callback_public_view, name='ml-oauth-callback-public')
    )
else:
    print("⚠️ Warning: ml_oauth_callback_public_view no disponible, la ruta /api/tiendas/mercadolibre/callback/ no estará disponible")

# Agregar el resto de las rutas
urlpatterns += [
    path('api/', include(router.urls)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/metricas/metrics/', MetricasAPIView.as_view(), name='metricas-ventas-rentabilidad'),
    path('api/inventario/metrics/', InventarioMetricsAPIView.as_view(), name='inventario-metrics'),
    path('api/verificar-database/', verificar_database_config, name='verificar-database'),  # Endpoint de verificación
]
