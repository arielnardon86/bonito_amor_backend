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
from inventario.views import (
    UserViewSet,
    ProductoViewSet,
    VentaViewSet,
    DetalleVentaViewSet,
    # DashboardMetricsView, # ¡ELIMINADA ESTA LÍNEA!
    MetodoPagoViewSet,
    TiendaViewSet,
    CategoriaViewSet,
    CustomTokenObtainPairView
)

# Configuración del Router para ViewSets
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'categorias', CategoriaViewSet)
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'ventas', VentaViewSet, basename='venta')
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalleventa')
router.register(r'tiendas', TiendaViewSet)
router.register(r'metodos-pago', MetodoPagoViewSet)

# Vista raíz de la API
@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'users': reverse('user-list', request=request, format=format),
        'categorias': reverse('categoria-list', request=request, format=format),
        'productos': reverse('producto-list', request=request, format=format),
        'ventas': reverse('venta-list', request=request, format=format),
        'detalles-venta': reverse('detalleventa-list', request=request, format=format),
        # 'dashboard-metrics': reverse('dashboard_metrics', request=request, format=format), # ¡ELIMINADA ESTA LÍNEA!
        'metodos-pago': reverse('metodopago-list', request=request, format=format),
        'tiendas': reverse('tienda-list', request=request, format=format),
        'token': reverse('token_obtain_pair', request=request, format=format),
        'token-refresh': reverse('token_refresh', request=request, format=format),
        'user-me': reverse('user-me', request=request, format=format), # Mantener en api_root si lo necesitas para documentación
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/api/', permanent=False)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'), # Rutas JWT primero
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # --- RUTA EXPLÍCITA PARA USERS/ME/ ANTES DEL INCLUDE DEL ROUTER ---
    path('api/users/me/', UserViewSet.as_view({'get': 'me'}), name='user-me'), 

    path('api/', api_root, name='api-root'), # api_root después de las rutas específicas
    path('api/', include(router.urls)), # Incluye todas las rutas del router (después de las explícitas)

    # --- Rutas específicas para APIViews o acciones personalizadas (si no están en el router) ---
    path('api/ventas/<uuid:pk>/anular/', VentaViewSet.as_view({'patch': 'anular'}), name='venta-anular'),
    path('api/ventas/<uuid:pk>/anular_detalle/', VentaViewSet.as_view({'patch': 'anular_detalle'}), name='venta-anular-detalle'),
    # path('api/metricas/metrics/', DashboardMetricsView.as_view(), name='dashboard_metrics'), # ¡ELIMINADA ESTA LÍNEA!
    # 'metodos-pago' ya está en el router, no necesita una ruta explícita aquí
]
