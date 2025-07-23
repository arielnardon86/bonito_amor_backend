from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.response import Response # Importar Response
from rest_framework.decorators import api_view # Importar api_view
from rest_framework.reverse import reverse # Importar reverse

# --- Importaciones de Simple JWT ---
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    # TokenVerifyView, # Opcional si necesitas verificación de token
)

# --- Importaciones de tus Vistas (AJUSTADO: TODAS ASUMIENDO QUE ESTÁN EN 'inventario.views') ---
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
router.register(r'users', UserViewSet, basename='user')
router.register(r'metricas', MetricasVentasViewSet, basename='metricas') 
router.register(r'metodos-pago', PaymentMethodListView, basename='metodo-pago') 

# Si DetalleVentaViewSet es un ViewSet independiente y quieres rutas para él,
# deberías registrarlo aquí. Si es parte de VentaViewSet (ej. como un serializer anidado),
# no necesita una entrada de router separada.
# router.register(r'detalle-ventas', DetalleVentaViewSet, basename='detalle-venta')

# --- Función para la raíz de la API ---
# Esta función lista todos los endpoints disponibles en la API
@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'users': reverse('user-list', request=request, format=format),
        'productos': reverse('producto-list', request=request, format=format),
        'ventas': reverse('venta-list', request=request, format=format),
        # CORRECCIÓN CLAVE AQUÍ: Usar 'metricas-metrics' en lugar de 'metricas-list'
        'metricas': reverse('metricas-metrics', request=request, format=format), 
        'metodos-pago': reverse('metodo-pago-list', request=request, format=format),
        'token_obtain_pair': reverse('token_obtain_pair', request=request, format=format),
        'token_refresh': reverse('token_refresh', request=request, format=format),
        # Asumiendo que el registro se hace con un POST a la lista de usuarios
        'register': reverse('user-list', request=request, format=format), 
    })


urlpatterns = [
    path('admin/', admin.site.urls),

    # Ruta para la raíz de la API
    path('api/', api_root), # Asegúrate de que esta línea esté aquí para la raíz de la API

    # --- INCLUYE LAS RUTAS GENERADAS POR EL ROUTER ---
    # Esto es CRÍTICO para que funcionen las URLs de tus ViewSets (productos, ventas, users, metricas, metodos-pago)
    path('api/', include(router.urls)),

    # --- Rutas JWT (autenticación) ---
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'), # Opcional
]
