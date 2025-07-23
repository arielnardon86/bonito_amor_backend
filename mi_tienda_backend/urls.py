from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter 

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
    TiendaViewSet, # <--- ¡ASEGÚRATE DE QUE ESTA LÍNEA ESTÉ PRESENTE!
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user') 
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') 
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') 
router.register(r'tiendas', TiendaViewSet, basename='tienda') # <--- ¡ASEGÚRATE DE QUE ESTA LÍNEA ESTÉ PRESENTE!


urlpatterns = [
    path('admin/', admin.site.urls),

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
