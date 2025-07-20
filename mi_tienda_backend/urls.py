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
# Eliminamos CurrentUserView y UserRegisterView de aquí porque son acciones o métodos
# manejados por el UserViewSet y el router.
from inventario.views import (
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentasViewSet, 
    PaymentMethodListView, 
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user') # Este ViewSet maneja la creación de usuarios (registro)
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') 
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') 

# Si DetalleVentaViewSet es un ViewSet independiente y quieres rutas para él,
# deberías registrarlo aquí. Si es parte de VentaViewSet (ej. como un serializer anidado),
# no necesita una entrada de router separada.
# router.register(r'detalle-ventas', DetalleVentaViewSet, basename='detalle-venta')


urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    # Esto es CRÍTICO para que funcionen las URLs de tus ViewSets (productos, ventas, users, metricas, metodos-pago)
    # La creación de usuarios (registro) se maneja con un POST a /api/users/
    # La obtención del usuario actual (me) se maneja con un GET a /api/users/me/
    # Las métricas se manejan con un GET a /api/metricas/metrics/
    # Los métodos de pago se manejan con un GET a /api/metodos-pago/
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    # Estas son las rutas estándar de Simple JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'), # Opcional

    # --- Rutas Específicas de Usuario ---
    # Eliminada la ruta 'api/register/' explícita. Ahora es manejada por el router
    # a través del método 'create' de UserViewSet (POST a /api/users/).
]
