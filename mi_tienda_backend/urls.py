from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

# --- Importaciones de Simple JWT ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    # TokenVerifyView, # Opcional: Descomenta si lo necesitas para verificar tokens
)

# --- Importaciones de tus Vistas desde 'inventario.views' ---
# Asegúrate de que todas estas vistas existan en tu archivo inventario/views.py
from inventario.views import (
    CurrentUserView,
    UserRegisterView,
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet, # Importado, pero no directamente usado en urlpatterns a menos que sea un ViewSet independiente
    MetricasVentaView,
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto') # Agregado basename para mayor claridad y evitar posibles conflictos
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user')

# Si DetalleVentaViewSet es un ViewSet independiente y quieres rutas para él,
# deberías registrarlo aquí. Si es parte de VentaViewSet (ej. como un serializer anidado),
# no necesita una entrada de router separada.
# router.register(r'detalle-ventas', DetalleVentaViewSet, basename='detalle-venta')


urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    # Esto es CRÍTICO para que funcionen las URLs de tus ViewSets (productos, ventas, users)
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    # Estas son las rutas estándar de Simple JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'), # Descomenta si necesitas verificar tokens

    # --- Rutas Específicas de Usuario ---
    # La ruta de registro generalmente no requiere autenticación.
    # La ruta de 'me' generalmente sí requiere autenticación.
    path('api/register/', UserRegisterView.as_view(), name='register'),
    path('api/users/me/', CurrentUserView.as_view(), name='current_user_me'),

    # --- RUTA DE MÉTRICAS ---
    path('api/metricas/', MetricasVentaView.as_view(), name='metricas_ventas'),
]