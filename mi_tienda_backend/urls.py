from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter # Necesario para ViewSets

# --- Importaciones de Simple JWT ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    # TokenVerifyView, # Opcional si necesitas verificación de token
)

# --- Importaciones de tus Vistas (AJUSTADO: TODAS ASUMIENDO QUE ESTÁN EN 'inventario.views') ---
# Eliminamos CurrentUserView de aquí porque es una acción dentro de UserViewSet.
# Corregimos MetricasVentaView a MetricasVentasViewSet.
from inventario.views import (
    UserRegisterView,
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentasViewSet, # Nomenclatura corregida para coincidir con views.py
    PaymentMethodListView, # Añadido: para registrar con el router
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user')
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') # Registramos MetricasVentasViewSet
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') # Registramos PaymentMethodListView

# Si DetalleVentaViewSet es un ViewSet independiente y quieres rutas para él,
# deberías registrarlo aquí. Si es parte de VentaViewSet (ej. como un serializer anidado),
# no necesita una entrada de router separada.
# router.register(r'detalle-ventas', DetalleVentaViewSet, basename='detalle-venta')


urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    # Esto es CRÍTICO para que funcionen las URLs de tus ViewSets (productos, ventas, users, metricas, metodos-pago)
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    # Estas son las rutas estándar de Simple JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'), # Opcional

    # --- Rutas Específicas de Usuario ---
    # La ruta de registro generalmente no requiere autenticación.
    path('api/register/', UserRegisterView.as_view(), name='register'),
    # Eliminada la ruta 'api/users/me/' explícita. Ahora es manejada por el router
    # a través de la acción 'me' en UserViewSet (ej. /api/users/me/).

    # Eliminada la ruta de métricas explícita. Ahora es manejada por el router
    # a través de la acción 'metrics' en MetricasVentasViewSet (ej. /api/metricas/metrics/).
]
