from django.contrib import admin
from django.urls import path, include 
# from rest_framework.routers import DefaultRouter # Ya no es necesario si no registras ViewSets

# --- ÚNICA IMPORTACIÓN DESDE inventario.views que es correcta y existe ---
from inventario.views import MetricasVentaView 

# --- VISTAS QUE NO SE HAN ENCONTRADO EN TU PROYECTO ---
# Si estas vistas (ProductoViewSet, VentaViewSet, DetalleVentaViewSet, CurrentUserView, UserRegisterView, UserViewSet)
# NO EXISTEN en otros archivos 'views.py' en tu proyecto (como 'productos/views.py', 'users/views.py', etc.),
# entonces NO DEBEN SER IMPORTADAS. Las mantendremos comentadas/eliminadas.

# from productos.views import ProductoViewSet
# from ventas.views import VentaViewSet, DetalleVentaViewSet
# from users.views import CurrentUserView, UserRegisterView, UserViewSet 

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

# Si no hay ViewSets que registrar, el router no es necesario.
# router = DefaultRouter()
# router.register(r'productos', ProductoViewSet)
# router.register(r'ventas', VentaViewSet)
# router.register(r'detalles_venta', DetalleVentaViewSet)
# router.register(r'users', UserViewSet)


urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- RUTAS DE DRF ROUTER ---
    # Comentamos esta línea porque no hay ViewSets registrados en el router actualmente.
    # Si en el futuro agregas ViewSets y los registras, deberás descomentarla.
    # path('api/', include(router.urls)), 

    # Rutas JWT (autenticación)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # --- RUTAS DE APIView/Función que NO SE HAN ENCONTRADO ---
    # Si UserRegisterView y CurrentUserView no existen en ningún 'views.py' de tu proyecto,
    # estas rutas no funcionarán y deben permanecer comentadas.
    # path('api/register/', UserRegisterView.as_view(), name='register'),
    # path('api/current_user/', CurrentUserView.as_view(), name='current_user'),
    
    # --- RUTA DE MÉTRICAS (Confirmado que esta vista existe en inventario/views.py) ---
    path('api/metricas/', MetricasVentaView.as_view(), name='metricas_ventas'),
]