from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter 
from django.views.generic.base import RedirectView # Importa RedirectView para la redirección

# --- Importaciones de Simple JWT ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# --- Importaciones de tus Vistas (AJUSTADO: Incluye TiendaViewSet) ---
from inventario.views import (
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentasViewSet, 
    PaymentMethodListView, 
    TiendaViewSet, 
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user') 
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') 
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') 
router.register(r'tiendas', TiendaViewSet, basename='tienda') 


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/api/', permanent=False)), # <--- NUEVA LÍNEA: Redirige el root a /api/
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
