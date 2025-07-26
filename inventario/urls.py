# BONITO_AMOR/backend/inventario/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductoViewSet, CategoriaViewSet, TiendaViewSet, UserViewSet, # ¡Cambiado a UserViewSet!
    VentaViewSet, DetalleVentaViewSet,
    # MetodoPagoViewSet, # Ya no se importa aquí, se usa PaymentMethodListView en el urls.py principal
    # MetricasVentasViewSet # Ya no se importa aquí, se usa MetricasVentasViewSet en el urls.py principal
)

router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='producto') # Añadido basename
router.register(r'categorias', CategoriaViewSet)
router.register(r'tiendas', TiendaViewSet)
router.register(r'users', UserViewSet) # Usar 'users' para que coincida con el router principal
router.register(r'ventas', VentaViewSet, basename='venta') # Añadido basename
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalleventa') # Añadido basename
# router.register(r'metodos-pago', MetodoPagoViewSet) # Ya no se registra aquí
# router.register(r'metricas-ventas', MetricasVentasViewSet) # Ya no se registra aquí

urlpatterns = [
    path('', include(router.urls)),
    # Rutas para funciones personalizadas
    path('productos/buscar_por_barcode/', ProductoViewSet.as_view({'get': 'buscar_por_barcode'}), name='producto-buscar-barcode'),
    path('productos/imprimir_etiquetas/', ProductoViewSet.as_view({'get': 'imprimir_etiquetas'}), name='producto-imprimir-etiquetas'),
    
    # Las rutas de métricas y métodos de pago ahora se definen en mi_tienda_backend/urls.py
]
