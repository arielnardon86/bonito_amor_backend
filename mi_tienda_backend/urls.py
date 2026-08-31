# mi_tienda_backend/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventario.views import (
    ProductoViewSet, CategoriaViewSet, TiendaViewSet, UserViewSet,
    VentaViewSet, DetalleVentaViewSet, MetodoPagoViewSet, CompraViewSet, CompraStockViewSet,
    CustomTokenObtainPairView, MetricasAPIView, InventarioMetricsAPIView, WidgetVentasHoyAPIView,
    ArancelMetodoTiendaViewSet, FacturaViewSet, NotaCreditoViewSet,
    CierreCajaViewSet, EgresoCajaViewSet, HistorialAccionViewSet,
    ClienteViewSet,
    ProveedorViewSet,
    RubroViewSet,
    PresupuestoViewSet,
)
# Importación condicional de ArancelMercadoLibreViewSet y ArancelMercadoLibreProductoViewSet
try:
    from inventario.views import ArancelMercadoLibreViewSet, ArancelMercadoLibreProductoViewSet
except (ImportError, AttributeError) as e:
    ArancelMercadoLibreViewSet = None
    ArancelMercadoLibreProductoViewSet = None
    print(f"⚠️ Warning: No se pudo importar ViewSets ML: {e}")
# Importación condicional del callback público de ML y endpoints Worker
try:
    from inventario.views import (
        ml_oauth_callback_public_view,
        ml_oauth_worker_credentials,
        ml_oauth_worker_save_tokens,
    )
except (ImportError, AttributeError) as e:
    ml_oauth_callback_public_view = None
    ml_oauth_worker_credentials = None
    ml_oauth_worker_save_tokens = None
    print(f"⚠️ Warning: No se pudo importar vistas ML OAuth: {e}")
from rest_framework.decorators import api_view
from rest_framework.response import Response
from inventario.views import (
    verificar_database_config, registrar_token_fcm, eliminar_token_fcm,
    planes_publicos, registro_publico, verificar_cuit_disponible, mp_webhook_suscripcion, cambiar_plan,
    mi_suscripcion, verificar_suscripcion_mp, cancelar_suscripcion_view,
    verificar_pago_pendiente, actualizar_datos_tienda, regenerar_widget_token,
    tn_instalar_iniciar, tn_instalar_completar_registro, tn_instalar_vincular_cuenta_existente,
    password_reset_request, password_reset_confirm, update_email,
    enviar_comunicado,
)
# Importación condicional de CambioDevolucionViewSet
try:
    from inventario.views import CambioDevolucionViewSet
except (ImportError, AttributeError):
    CambioDevolucionViewSet = None
from rest_framework_simplejwt.views import TokenRefreshView


router = DefaultRouter()
router.register(r'productos', ProductoViewSet, basename='productos')
router.register(r'categorias', CategoriaViewSet, basename='categorias')
router.register(r'tiendas', TiendaViewSet, basename='tiendas')
router.register(r'users', UserViewSet, basename='users')
router.register(r'ventas', VentaViewSet, basename='ventas')
router.register(r'detalles-venta', DetalleVentaViewSet, basename='detalles-venta')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodos-pago')
router.register(r'compras', CompraViewSet, basename='compras')
router.register(r'compras-stock', CompraStockViewSet, basename='compras-stock')
router.register(r'aranceles-tienda', ArancelMetodoTiendaViewSet, basename='aranceles-tienda') # NUEVA RUTA
# Aranceles ML por PRODUCTO (arancel % + costo envío) - nueva API principal
if ArancelMercadoLibreProductoViewSet is not None:
    router.register(r'aranceles-ml', ArancelMercadoLibreProductoViewSet, basename='aranceles-ml')
elif ArancelMercadoLibreViewSet is not None:
    router.register(r'aranceles-ml', ArancelMercadoLibreViewSet, basename='aranceles-ml')
else:
    print("⚠️ Warning: ViewSets ML no disponibles. Aplica la migración 0022_arancel_ml_producto.")
router.register(r'cierre-caja', CierreCajaViewSet, basename='cierre-caja')
router.register(r'egresos-caja', EgresoCajaViewSet, basename='egresos-caja')
router.register(r'facturas', FacturaViewSet, basename='facturas')
router.register(r'notas-credito', NotaCreditoViewSet, basename='notas-credito')
router.register(r'historial-acciones', HistorialAccionViewSet, basename='historial-acciones')
router.register(r'clientes', ClienteViewSet, basename='clientes')
router.register(r'proveedores', ProveedorViewSet, basename='proveedores')
router.register(r'rubros', RubroViewSet, basename='rubros')
router.register(r'presupuestos', PresupuestoViewSet, basename='presupuestos')
# Registrar CambioDevolucionViewSet solo si existe (migración aplicada)
if CambioDevolucionViewSet is not None:
    router.register(r'cambios-devoluciones', CambioDevolucionViewSet, basename='cambios-devoluciones') # NUEVA RUTA


urlpatterns = [
    path('admin/', admin.site.urls),
]

# Agregar ruta del callback público solo si la vista está disponible
if ml_oauth_callback_public_view is not None:
    urlpatterns.append(
        path('api/tiendas/mercadolibre/callback/', ml_oauth_callback_public_view, name='ml-oauth-callback-public')
    )
else:
    print("⚠️ Warning: ml_oauth_callback_public_view no disponible, la ruta /api/tiendas/mercadolibre/callback/ no estará disponible")

# Endpoints internos para Cloudflare Worker (proxy OAuth 403)
if ml_oauth_worker_credentials is not None and ml_oauth_worker_save_tokens is not None:
    urlpatterns += [
        path('api/internal/ml-oauth-credentials/', ml_oauth_worker_credentials, name='ml-oauth-worker-credentials'),
        path('api/internal/ml-oauth-save-tokens/', ml_oauth_worker_save_tokens, name='ml-oauth-worker-save-tokens'),
    ]

# Agregar el resto de las rutas
urlpatterns += [
    path('api/', include(router.urls)),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/metricas/metrics/', MetricasAPIView.as_view(), name='metricas-ventas-rentabilidad'),
    path('api/inventario/metrics/', InventarioMetricsAPIView.as_view(), name='inventario-metrics'),
    path('api/verificar-database/', verificar_database_config, name='verificar-database'),
    path('api/notificaciones/registrar-token/', registrar_token_fcm, name='registrar-token-fcm'),
    path('api/notificaciones/eliminar-token/', eliminar_token_fcm, name='eliminar-token-fcm'),
    # Suscripciones / registro público
    path('api/planes/', planes_publicos, name='planes-publicos'),
    path('api/registro/', registro_publico, name='registro-publico'),
    path('api/verificar-cuit/', verificar_cuit_disponible, name='verificar-cuit'),
    path('api/mp-webhook-suscripcion/', mp_webhook_suscripcion, name='mp-webhook-suscripcion'),
    path('api/suscripcion/cambiar-plan/', cambiar_plan, name='cambiar-plan'),
    path('api/suscripcion/mi-plan/', mi_suscripcion, name='mi-suscripcion'),
    path('api/suscripcion/verificar/', verificar_suscripcion_mp, name='verificar-suscripcion-mp'),
    path('api/suscripcion/cancelar/', cancelar_suscripcion_view, name='cancelar-suscripcion'),
    path('api/suscripcion/verificar-pago/', verificar_pago_pendiente, name='verificar-pago-pendiente'),
    path('api/tienda/actualizar-datos/', actualizar_datos_tienda, name='actualizar-datos-tienda'),
    path('api/tienda/widget-token/regenerar/', regenerar_widget_token, name='regenerar-widget-token'),
    path('api/widget/ventas-hoy/', WidgetVentasHoyAPIView.as_view(), name='widget-ventas-hoy'),
    # Instalación de Total Stock desde la App Store de Tienda Nube (sin cuenta previa)
    path('api/tiendanube/instalar/iniciar/', tn_instalar_iniciar, name='tn-instalar-iniciar'),
    path('api/tiendanube/instalar/completar-registro/', tn_instalar_completar_registro, name='tn-instalar-completar-registro'),
    path('api/tiendanube/instalar/vincular-cuenta-existente/', tn_instalar_vincular_cuenta_existente, name='tn-instalar-vincular-existente'),
    # Recupero de contraseña
    path('api/auth/password-reset/', password_reset_request, name='password-reset-request'),
    path('api/admin/enviar-comunicado/', enviar_comunicado, name='enviar-comunicado'),
    path('api/auth/password-reset/confirm/', password_reset_confirm, name='password-reset-confirm'),
    path('api/auth/update-email/', update_email, name='update-email'),
]
