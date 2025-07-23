from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter 
from django.views.generic.base import RedirectView 

# Importaciones necesarias para la raíz de la API personalizada
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.permissions import AllowAny # Importa AllowAny para la raíz de la API

# --- Importaciones de Simple JWT ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# --- Importaciones de tus Vistas ---
from inventario.views import (
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    MetricasVentasViewSet, 
    PaymentMethodListView, 
    TiendaViewSet, # Asegúrate de que TiendaViewSet esté importado
)

# --- Configuración del Router para ViewSets ---
router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'users', UserViewSet, basename='user') 
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') 
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') 
router.register(r'tiendas', TiendaViewSet, basename='tienda') # Asegúrate de que TiendaViewSet esté registrado

# --- Vista de la Raíz de la API Personalizada ---
# Esta vista permite que la URL /api/ sea accesible sin autenticación,
# lo cual es útil para la exploración de la API o para clientes que la visiten.
@api_view(['GET'])
@permission_classes([AllowAny]) # Permite acceso sin autenticación a la raíz de la API
def api_root(request, format=None):
    return Response({
        'users': reverse('user-list', request=request, format=format),
        'productos': reverse('producto-list', request=request, format=format),
        'ventas': reverse('venta-list', request=request, format=format),
        'metricas': reverse('metricas-list', request=request, format=format),
        'metodos-pago': reverse('metodo-pago-list', request=request, format=format),
        'tiendas': reverse('tienda-list', request=request, format=format), # Incluye la ruta de tiendas
        'token_obtain_pair': reverse('token_obtain_pair', request=request, format=format),
        'token_refresh': reverse('token_refresh', request=request, format=format),
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/api/', permanent=False)), # Redirige la raíz del dominio a /api/
    path('api/', api_root, name='api-root'), # Asigna la vista de la raíz de la API personalizada
    path('api/', include(router.urls)), # Incluye las URLs generadas por el router bajo /api/
    
    # --- Rutas JWT (autenticación) ---
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

# Opcional: Si usas sufijos de formato (ej. .json, .api) en tus URLs
# from rest_framework.urlpatterns import format_suffix_patterns
# urlpatterns = format_suffix_patterns(urlpatterns)
