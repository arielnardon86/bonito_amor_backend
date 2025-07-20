from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter # Necesario para ViewSets

# --- Importaciones de Simple JWT (ya las tenías correctas) ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    # TokenVerifyView, # Opcional si necesitas verificación de token
)

# --- Importaciones de tus Vistas (AJUSTADO: ASUMIENDO QUE ESTÁN EN 'inventario.views') ---
# Si tus vistas de usuario están en una app llamada 'inventario':
from inventario.views import CurrentUserView, UserRegisterView, UserViewSet

# Si tus vistas de productos están en una app llamada 'inventario':
from inventario.views import ProductoViewSet

# Si tus vistas de ventas están en una app llamada 'inventario':
from inventario.views import VentaViewSet, DetalleVentaViewSet

# --- Importación de MetricasVentaView (ya la tenías correcta) ---
from inventario.views import MetricasVentaView

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet)
router.register(r'ventas', VentaViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # --- Rutas Específicas de Usuario ---
    path('api/users/me/', CurrentUserView.as_view(), name='current_user_me'),
    path('api/register/', UserRegisterView.as_view(), name='register'),

    # --- RUTA DE MÉTRICAS ---
    path('api/metricas/', MetricasVentaView.as_view(), name='metricas_ventas'),
]
