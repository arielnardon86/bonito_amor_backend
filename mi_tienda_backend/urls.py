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
# Si tus vistas de usuario, productos y ventas están en 'inventario/views.py':
from inventario.views import (
    CurrentUserView,
    UserRegisterView,
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentaView, # Esta ya la tenías importada de inventario.views
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet)
router.register(r'ventas', VentaViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    # Esto es CRÍTICO para que funcionen las URLs de tus ViewSets (productos, ventas, users)
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    # Estas son las rutas estándar de Simple JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'), # Opcional

    # --- Rutas Específicas de Usuario ---
    # Asegúrate de que CurrentUserView y UserRegisterView existan en inventario/views.py
    path('api/users/me/', CurrentUserView.as_view(), name='current_user_me'),
    path('api/register/', UserRegisterView.as_view(), name='register'),

    # --- RUTA DE MÉTRICAS ---
    path('api/metricas/', MetricasVentaView.as_view(), name='metricas_ventas'),
]
