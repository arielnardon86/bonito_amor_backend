from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter # Necesario para ViewSets

# --- Importaciones de Simple JWT (ya las tenías correctas) ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    # TokenVerifyView, # Opcional si necesitas verificación de token
)

# --- Importaciones de tus Vistas (AJUSTA ESTAS RUTAS SEGÚN TU ESTRUCTURA REAL) ---
# Si tus vistas de usuario están en una app llamada 'users':
from users.views import CurrentUserView, UserRegisterView, UserViewSet

# Si tus vistas de productos están en una app llamada 'productos':
from productos.views import ProductoViewSet

# Si tus vistas de ventas están en una app llamada 'ventas':
from ventas.views import VentaViewSet, DetalleVentaViewSet

# --- Importación desde inventario.views (ya la tenías correcta) ---
from inventario.views import MetricasVentaView

# --- Configuración del Router para ViewSets ---
# Este router generará URLs para tus ViewSets (ej. /api/productos/, /api/users/, etc.)
router = DefaultRouter()
router.register(r'productos', ProductoViewSet)
router.register(r'ventas', VentaViewSet)
router.register(r'users', UserViewSet) # Esto creará /api/users/ y /api/users/{id}/

# Si tu UserViewSet tiene un método 'me' decorado con @action(detail=False, url_path='me'),
# entonces router.register(r'users', UserViewSet) ya creará /api/users/me/ automáticamente.
# Si no es el caso, o si prefieres una vista separada para 'me', usa la ruta explícita de abajo.


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

    # --- Rutas Específicas de Usuario (si no son manejadas por el router o Djoser) ---
    # Si tu frontend llama a /api/users/me/, esta ruta es necesaria.
    # Asegúrate de que CurrentUserView exista y sea importada correctamente.
    path('api/users/me/', CurrentUserView.as_view(), name='current_user_me'), # Ruta para obtener detalles del usuario actual
    path('api/register/', UserRegisterView.as_view(), name='register'), # Ruta para registro de usuarios

    # --- RUTA DE MÉTRICAS (Confirmado que esta vista existe en inventario/views.py) ---
    path('api/metricas/', MetricasVentaView.as_view(), name='metricas_ventas'),
]
