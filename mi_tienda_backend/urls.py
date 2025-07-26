# BONITO_AMOR/backend/mi_tienda_backend/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter 
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from django.views.generic.base import RedirectView 

# Importaciones de Simple JWT
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

# Importa TODAS las vistas de tu aplicación inventario que se usarán en urls.py
# ¡Estos nombres deben coincidir con las clases en inventario/views.py!
from inventario.views import (
    UserViewSet, # Ya renombrado a UserViewSet
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentasViewSet, # Es un ViewSet
    PaymentMethodListView, # Es una APIView
    TiendaViewSet,
    CategoriaViewSet, 
    CustomTokenObtainPairView
)

# Configuración del Router para ViewSets
router = DefaultRouter()
router.register(r'users', UserViewSet) # Coincide con /api/users/
router.register(r'categorias', CategoriaViewSet)
router.register(r'productos', ProductoViewSet, basename='producto') 
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalleventa')
# router.register(r'metricas-ventas', MetricasVentasViewSet, basename='metricas-ventas') 
# ^^^ Comentado porque MetricasVentasViewSet se usará directamente con .as_view() para la ruta específica

router.register(r'tiendas', TiendaViewSet) # Coincide con /api/tiendas/

# Vista raíz de la API
@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'users': reverse('user-list', request=request, format=format),
        'categorias': reverse('categoria-list', request=request, format=format),
        'productos': reverse('producto-list', request=request, format=format),
        'ventas': reverse('venta-list', request=request, format=format),
        'detalles-venta': reverse('detalleventa-list', request=request, format=format),
        'metricas-ventas': reverse('metricas-metrics', request=request, format=format), # Nombre de la ruta ajustado
        'metodos-pago': reverse('metodos_pago', request=request, format=format), # Nombre de la ruta ajustado
        'tiendas': reverse('tienda-list', request=request, format=format),
        'token': reverse('token_obtain_pair', request=request, format=format),
        'token-refresh': reverse('token_refresh', request=request, format=format),
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/api/', permanent=False)),
    path('api/', api_root, name='api-root'),
    path('api/', include(router.urls)), # Incluye todas las rutas del router
    
    # --- Rutas específicas para APIViews o acciones personalizadas ---
    # Ruta para métricas de ventas (coincide con frontend: /api/metricas/metrics/)
    path('api/metricas/metrics/', MetricasVentasViewSet.as_view({'get': 'list'}), name='metricas-metrics'),
    
    # Ruta para métodos de pago (coincide con frontend: /api/metodos-pago/)
    path('api/metodos-pago/', PaymentMethodListView.as_view(), name='metodos_pago'),
    
    # Ruta para el perfil del usuario autenticado (coincide con frontend: /api/users/me/)
    path('api/users/me/', UserViewSet.as_view({'get': 'me'}), name='user-me'), # Nueva ruta para /me/
    
    # --- Rutas JWT (autenticación) ---
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'), 
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
