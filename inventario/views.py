# inventario/views.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/views.py
import logging
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value 
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import DecimalField 
from django.db import close_old_connections, models # <-- Importado para el fix de conexión y búsqueda de categorías
from django.http import HttpResponse
from io import BytesIO

logger = logging.getLogger(__name__)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import barcode
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

# CAMBIO 1: Importar ArancelMetodoTienda y ArancelMercadoLibre (con importación condicional)
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda, CategoriaMercadoLibre, Factura

# Importación condicional de ArancelMercadoLibre (puede no existir si la migración no se ha aplicado)
try:
    from .models import ArancelMercadoLibre
except ImportError:
    ArancelMercadoLibre = None
    logger.warning("⚠️ ArancelMercadoLibre no está disponible. Aplica la migración 0019_arancel_mercado_libre.")
# Importación condicional para CambioDevolucion
# Intentar importar directamente - si falla, los modelos no están disponibles
try:
    from .models import CambioDevolucion, DetalleCambioDevolucion
    logger.info("✅ Modelos CambioDevolucion y DetalleCambioDevolucion importados directamente")
except ImportError as e:
    logger.warning(f"⚠️ No se pudieron importar CambioDevolucion y DetalleCambioDevolucion: {e}")
    CambioDevolucion = None
    DetalleCambioDevolucion = None

def _get_cambio_devolucion_models():
    """
    Función auxiliar para obtener los modelos CambioDevolucion y DetalleCambioDevolucion.
    Se llama cuando se necesitan los modelos, no al momento de importar el módulo.
    """
    global CambioDevolucion, DetalleCambioDevolucion
    
    # Si ya están importados, retornarlos
    if CambioDevolucion is not None and DetalleCambioDevolucion is not None:
        return CambioDevolucion, DetalleCambioDevolucion
    
    # Intentar obtener usando apps.get_model() (la forma más segura)
    try:
        from django.apps import apps
        CambioDevolucion = apps.get_model('inventario', 'CambioDevolucion')
        DetalleCambioDevolucion = apps.get_model('inventario', 'DetalleCambioDevolucion')
        logger.info("✅ Modelos CambioDevolucion y DetalleCambioDevolucion obtenidos con apps.get_model()")
        return CambioDevolucion, DetalleCambioDevolucion
    except LookupError:
        logger.warning("⚠️ apps.get_model() falló - los modelos no están registrados en Django")
        # Si apps.get_model falla, los modelos no están registrados
        # Verificar si las tablas existen para dar un mensaje más útil
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                if connection.vendor == 'postgresql':
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name IN ('inventario_cambiodevolucion', 'inventario_detallecambiodevolucion')
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                else:
                    table_names = connection.introspection.table_names()
                    tables = [t for t in table_names if t in ('inventario_cambiodevolucion', 'inventario_detallecambiodevolucion')]
                
                if 'inventario_cambiodevolucion' in tables and 'inventario_detallecambiodevolucion' in tables:
                    logger.error("❌ CRÍTICO: Las tablas existen pero los modelos no están registrados en Django. Esto indica que los modelos no están siendo definidos correctamente en models.py o hay un error de sintaxis que impide su registro.")
                else:
                    logger.warning(f"⚠️ Tablas no encontradas. Ejecuta: python manage.py migrate inventario 0013")
        except Exception as e:
            logger.error(f"❌ Error verificando tablas: {e}", exc_info=True)
    
    return None, None
from django.core.exceptions import ObjectDoesNotExist 
# CAMBIO 2: Importar ArancelMetodoTiendaSerializer
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer, ArancelMetodoTiendaSerializer,
    FacturaSerializer, EmitirFacturaSerializer,
    UserCreateSerializer, UserUpdateSerializer, ChangePasswordSerializer,
    ArancelMetodoTiendaCreateSerializer
)
# Importación condicional de serializers de ArancelMercadoLibre
try:
    from .serializers import ArancelMercadoLibreSerializer, ArancelMercadoLibreCreateSerializer
except ImportError:
    ArancelMercadoLibreSerializer = None
    ArancelMercadoLibreCreateSerializer = None
    logger.warning("⚠️ Serializers de ArancelMercadoLibre no están disponibles. Aplica la migración 0019_arancel_mercado_libre.")
# Importación ArancelMercadoLibreProducto (por producto: arancel % + costo envío)
try:
    from .models import ArancelMercadoLibreProducto
    from .serializers import ArancelMercadoLibreProductoSerializer, ArancelMercadoLibreProductoCreateSerializer
except (ImportError, AttributeError):
    ArancelMercadoLibreProducto = None
    ArancelMercadoLibreProductoSerializer = None
    ArancelMercadoLibreProductoCreateSerializer = None
# Importación condicional de serializers de CambioDevolucion
# Primero importar normalmente
try:
    from .serializers import CambioDevolucionSerializer, CambioDevolucionCreateSerializer, DetalleCambioDevolucionSerializer
except (ImportError, AttributeError):
    CambioDevolucionSerializer = None
    CambioDevolucionCreateSerializer = None
    DetalleCambioDevolucionSerializer = None

# Si los modelos existen después de la importación, verificar y potencialmente forzar reimportación
if CambioDevolucion is not None and DetalleCambioDevolucion is not None:
    from rest_framework import serializers as drf_serializers
    try:
        # Verificar si los serializers son dummy (Serializer) en lugar de reales (ModelSerializer)
        if (CambioDevolucionSerializer is not None and
            not issubclass(CambioDevolucionSerializer, drf_serializers.ModelSerializer)):
            # Los serializers son dummy, necesitamos forzar reimportación
            logger.warning("Serializers de CambioDevolucion son dummy, forzando reimportación...")
            import importlib
            import inventario.serializers as serializers_module
            importlib.reload(serializers_module)
            # Reimportar después del reload
            from inventario.serializers import CambioDevolucionSerializer, CambioDevolucionCreateSerializer, DetalleCambioDevolucionSerializer
            logger.info("✅ Serializers de CambioDevolucion reimportados correctamente")
    except (TypeError, AttributeError, ImportError) as e:
        logger.warning(f"Error al verificar/reimportar serializers: {e}")
# Importar modelos de facturación
from .models import Factura
from .services.facturacion_service import FacturacionService
from .filters import VentaFilter 

# Clase de permiso personalizada que permite tanto is_superuser como is_staff
class IsAdminOrSuperUser(BasePermission):
    """
    Permiso personalizado que permite acceso a usuarios que sean superusuarios O staff.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and 
                   (request.user.is_superuser or request.user.is_staff))


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nombre', 'talle', 'codigo_barras']

    def get_queryset(self):
        user = self.request.user
        # Optimización: usar select_related para evitar consultas N+1 con tienda
        queryset = Producto.objects.select_related('tienda').all()

        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                return queryset.filter(tienda__nombre=tienda_slug).order_by('nombre')
            return queryset.order_by('nombre')
        
        elif user.tienda:
            if tienda_slug and user.tienda.nombre != tienda_slug:
                return Producto.objects.none()
            
            return queryset.filter(tienda=user.tienda).order_by('nombre')
        
        return Producto.objects.none()

    def perform_create(self, serializer):
        serializer.save(tienda=self.request.user.tienda)

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def productos_sin_codigo(self, request):
        productos = self.get_queryset().filter(codigo_barras__isnull=True)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def buscar_por_barcode(self, request):
        codigo = request.query_params.get('barcode', None)
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if not codigo or not tienda_slug:
            return Response({"detail": "Código de barras y slug de tienda son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            producto = self.get_queryset().get(codigo_barras=codigo, tienda__nombre=tienda_slug)
            serializer = self.get_serializer(producto)
            return Response(serializer.data)
        except Producto.DoesNotExist:
            return Response({"detail": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)


    @action(detail=False, methods=['get'])
    def productos_con_stock(self, request):
        productos = self.get_queryset().filter(stock__gt=0)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)


class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

# Vista independiente para el callback público de Mercado Libre (fuera del ViewSet)
@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
def ml_oauth_callback_public_view(request):
    """
    Vista independiente para recibir el callback de OAuth de Mercado Libre
    Este endpoint NO requiere {tienda_id} en la URL, permitiendo que Mercado Libre
    redirija a una URL fija como /api/tiendas/mercadolibre/callback/
    
    GET: Maneja la redirección desde Mercado Libre (obtiene el código)
    POST: Intercambia el código por tokens
    """
    from .models import Tienda
    from .services.mercadolibre_service import MercadoLibreService
    from django.conf import settings
    
    # Obtener tienda_id del request (puede venir en query params, body, o state)
    tienda_id = request.query_params.get('tienda_id') or (request.data.get('tienda_id') if hasattr(request, 'data') else None)
    tienda = None
    
    # Manejar GET (redirección desde Mercado Libre con code en query params)
    if request.method == 'GET':
        state = request.query_params.get('state')  # El state puede contener tienda_id
        
        # PRIORIDAD 1: Si viene state, extraer tienda_id de ahí (es lo más confiable)
        if state:
            try:
                # El state puede venir en formato "tienda_id:numero" (ej: "uuid:1")
                # Extraer solo la parte del UUID (antes del primer :)
                if ':' in state:
                    # Dividir por ':' y tomar la primera parte (el UUID)
                    tienda_id = state.split(':')[0]
                elif len(state) > 30:  # Probablemente es un UUID sin separador
                    tienda_id = state
                
                if tienda_id:
                    tienda = Tienda.objects.get(id=tienda_id)
                    logger.info(f"Tienda identificada desde state: {tienda_id}")
            except (ValueError, Tienda.DoesNotExist) as e:
                logger.warning(f"No se pudo extraer tienda_id del state '{state}': {e}")
    
    # Si aún no tenemos tienda, intentar otras formas
    if not tienda:
        if tienda_id:
            try:
                tienda = Tienda.objects.get(id=tienda_id)
            except Tienda.DoesNotExist:
                return Response(
                    {'error': f'Tienda con ID {tienda_id} no encontrada'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Como último recurso, buscar tiendas configuradas con ML
            # Solo funciona si hay exactamente una tienda configurada
            tiendas_ml = Tienda.objects.filter(
                plataforma_ecommerce='MERCADO_LIBRE'
            ).exclude(ml_app_id__isnull=True).exclude(ml_app_id='')
            
            if tiendas_ml.count() == 1:
                tienda = tiendas_ml.first()
                logger.info(f"Tienda identificada automáticamente (única configurada): {tienda.id}")
            elif tiendas_ml.count() == 0:
                return Response(
                    {'error': 'No hay tiendas configuradas para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                return Response(
                    {'error': 'No se pudo determinar la tienda. Múltiples tiendas configuradas. Proporciona tienda_id en el request o usa el parámetro state.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
    # Si llegamos aquí sin tienda, es un error
    if not tienda:
        return Response(
            {'error': 'No se pudo determinar la tienda'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verificar si ML está configurado
    if not hasattr(tienda, 'plataforma_ecommerce') or getattr(tienda, 'plataforma_ecommerce', 'NINGUNA') != 'MERCADO_LIBRE':
        return Response(
            {'error': 'La tienda no está configurada para Mercado Libre'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Manejar GET (redirección desde Mercado Libre con code en query params)
    if request.method == 'GET':
        code = request.query_params.get('code')
        
        if code:
            # Procesar el callback directamente
            ml_service = MercadoLibreService(tienda)
            
            if not settings.DEBUG:
                redirect_uri = 'https://bonito-amor-backend.onrender.com/api/tiendas/mercadolibre/callback/'
            else:
                scheme = request.scheme
                host = request.get_host()
                redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
            
            try:
                tokens = ml_service.exchange_code_for_token(code, redirect_uri)
                
                # Guardar tokens
                if hasattr(tienda, 'ml_access_token'):
                    tienda.ml_access_token = tokens['access_token']
                if hasattr(tienda, 'ml_refresh_token'):
                    tienda.ml_refresh_token = tokens.get('refresh_token')
                if hasattr(tienda, 'ml_user_id'):
                    tienda.ml_user_id = tokens.get('user_id')
                if hasattr(tienda, 'ml_token_expires_at'):
                    expires_in = tokens.get('expires_in', 21600)
                    tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                
                tienda.save()
                
                # Retornar HTML de éxito para el navegador con postMessage para comunicarse con la ventana padre
                return HttpResponse(
                    f'<html><head><title>Autenticación exitosa</title></head><body>'
                    f'<h1>✅ Autenticación exitosa</h1>'
                    f'<p>La integración con Mercado Libre se configuró correctamente para la tienda: {tienda.nombre}</p>'
                    f'<p>Puedes cerrar esta ventana.</p>'
                    f'<script>'
                    f'if (window.opener) {{'
                    f'  window.opener.postMessage({{'
                    f'    type: "ML_OAUTH_SUCCESS",'
                    f'    tienda_id: "{tienda.id}",'
                    f'    message: "Autenticación exitosa"'
                    f'  }}, "*");'
                    f'  setTimeout(function(){{window.close();}}, 2000);'
                    f'}} else {{'
                    f'  setTimeout(function(){{window.close();}}, 3000);'
                    f'}}'
                    f'</script></body></html>',
                    content_type='text/html'
                )
            except Exception as e:
                logger.error(f"Error procesando callback GET: {e}", exc_info=True)
                return HttpResponse(
                    f'<html><body><h1>❌ Error en autenticación</h1>'
                    f'<p>Error: {str(e)}</p></body></html>',
                    content_type='text/html',
                    status=400
                )
        else:
            return Response({
                'message': 'Endpoint de callback de Mercado Libre. Esperando código de autorización.'
            })
    
    # Manejar POST (intercambiar código por tokens)
    code = request.data.get('code') if hasattr(request, 'data') else None
    if not code:
        code = request.query_params.get('code')
    
    if not code:
        return Response(
            {'error': 'Código de autorización no proporcionado'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    ml_service = MercadoLibreService(tienda)
    
    # Usar la URL fija configurada en Mercado Libre
    if not settings.DEBUG:
        redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
    else:
        scheme = request.scheme
        host = request.get_host()
        redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
    
    try:
        tokens = ml_service.exchange_code_for_token(code, redirect_uri)
        
        # Guardar tokens en la tienda
        if hasattr(tienda, 'ml_access_token'):
            tienda.ml_access_token = tokens['access_token']
        if hasattr(tienda, 'ml_refresh_token'):
            tienda.ml_refresh_token = tokens.get('refresh_token')
        if hasattr(tienda, 'ml_user_id'):
            tienda.ml_user_id = tokens.get('user_id')
        
        # Calcular fecha de expiración
        if hasattr(tienda, 'ml_token_expires_at'):
            expires_in = tokens.get('expires_in', 21600)
            tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        
        tienda.save()
        
        return Response({
            'success': True,
            'message': 'Autenticación exitosa',
            'user_id': getattr(tienda, 'ml_user_id', None)
        })
    except Exception as e:
        logger.error(f"Error en callback OAuth público: {e}", exc_info=True)
        return Response(
            {'error': f'Error al procesar el callback: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [permissions.AllowAny]
        elif self.action == 'ml_webhook':
            # El webhook debe ser accesible sin autenticación para que Mercado Libre pueda validarlo
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """Optimización: Filtrar por nombre si se proporciona en query params"""
        queryset = super().get_queryset()
        nombre = self.request.query_params.get('nombre', None)
        if nombre:
            # Filtrar por nombre (case-insensitive)
            queryset = queryset.filter(nombre__iexact=nombre)
        return queryset

    # FIX DE CONEXIÓN (Mantenido)
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)
    
    # ========== MÉTODOS DE MERCADO LIBRE ==========
    
    def _ml_fields_exist(self, tienda):
        """Verifica si los campos de ML existen en el modelo Tienda"""
        return hasattr(tienda, 'plataforma_ecommerce')
    
    def _ml_configured(self, tienda):
        """Verifica si ML está configurado para la tienda"""
        if not self._ml_fields_exist(tienda):
            return False
        return getattr(tienda, 'plataforma_ecommerce', 'NINGUNA') == 'MERCADO_LIBRE'
    
    @action(detail=True, methods=['get'], url_path='mercadolibre/status')
    def ml_status(self, request, pk=None):
        """Verifica el estado de la conexión con Mercado Libre"""
        tienda = self.get_object()
        
        # Verificar si los campos de ML existen
        if not self._ml_fields_exist(tienda):
            return Response({
                'connected': False,
                'authenticated': False,
                'plataforma_ecommerce': 'NINGUNA',
                'message': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.',
                'migrations_required': True
            })
        
        if not self._ml_configured(tienda):
            return Response({
                'connected': False,
                'authenticated': False,
                'plataforma_ecommerce': getattr(tienda, 'plataforma_ecommerce', 'NINGUNA'),
                'message': 'La tienda no está configurada para Mercado Libre'
            })
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        has_token = bool(getattr(tienda, 'ml_access_token', None))
        has_app_id = bool(getattr(tienda, 'ml_app_id', None))
        has_client_secret = bool(getattr(tienda, 'ml_client_secret', None))
        
        return Response({
            'connected': has_token and has_app_id and has_client_secret,
            'authenticated': has_token and has_app_id and has_client_secret,
            'plataforma_ecommerce': getattr(tienda, 'plataforma_ecommerce', 'NINGUNA'),
            'has_token': has_token,
            'has_app_id': has_app_id,
            'has_client_secret': has_client_secret,
            'user_id': getattr(tienda, 'ml_user_id', None),
            'modo_test': getattr(tienda, 'ml_modo_test', True),
            'token_expires_at': getattr(tienda, 'ml_token_expires_at', None)
        })
    
    @action(detail=True, methods=['get'], url_path='mercadolibre/auth-url')
    def ml_auth_url(self, request, pk=None):
        """Genera la URL de autorización OAuth para Mercado Libre"""
        tienda = self.get_object()
        
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Obtener la URL de redirección desde el request o usar la URL fija configurada
        redirect_uri = request.query_params.get('redirect_uri')
        if not redirect_uri:
            # Usar la URL fija configurada en Mercado Libre (sin tienda_id)
            from django.conf import settings
            if not settings.DEBUG:
                # Producción: usar bonito-amor-backend.onrender.com
                redirect_uri = 'https://bonito-amor-backend.onrender.com/api/tiendas/mercadolibre/callback/'
            else:
                # Desarrollo: construirla dinámicamente
                scheme = request.scheme  # http o https
                host = request.get_host()  # dominio del servidor
                redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
        
        # Usar el tienda_id como state para poder identificarlo en el callback
        state = str(pk)
        
        try:
            auth_url = ml_service.get_authorization_url(redirect_uri, state=state)
            return Response({'auth_url': auth_url})
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/callback')
    def ml_oauth_callback(self, request, pk=None):
        """Procesa el callback de OAuth de Mercado Libre"""
        tienda = self.get_object()
        
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        code = request.data.get('code')
        if not code:
            return Response(
                {'error': 'Código de autorización no proporcionado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Obtener redirect_uri del request o construirla dinámicamente
        redirect_uri = request.data.get('redirect_uri')
        if not redirect_uri:
            # Construir la URL dinámicamente basándose en el request
            scheme = request.scheme  # http o https
            host = request.get_host()  # dominio del servidor
            redirect_uri = f"{scheme}://{host}/api/tiendas/{pk}/mercadolibre/callback/"
        
        try:
            tokens = ml_service.exchange_code_for_token(code, redirect_uri)
            
            # Guardar tokens en la tienda (usando getattr/setattr para seguridad)
            if hasattr(tienda, 'ml_access_token'):
                tienda.ml_access_token = tokens['access_token']
            if hasattr(tienda, 'ml_refresh_token'):
                tienda.ml_refresh_token = tokens.get('refresh_token')
            if hasattr(tienda, 'ml_user_id'):
                tienda.ml_user_id = tokens.get('user_id')
            
            # Calcular fecha de expiración
            if hasattr(tienda, 'ml_token_expires_at'):
                expires_in = tokens.get('expires_in', 21600)  # 6 horas por defecto
                tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            tienda.save()
            
            return Response({
                'success': True,
                'message': 'Autenticación exitosa',
                'user_id': getattr(tienda, 'ml_user_id', None)
            })
        except Exception as e:
            logger.error(f"Error en callback OAuth: {e}", exc_info=True)
            return Response(
                {'error': f'Error al procesar el callback: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get', 'post'], url_path='mercadolibre/callback', permission_classes=[permissions.AllowAny])
    def ml_oauth_callback_public(self, request):
        """
        Endpoint público para recibir el callback de OAuth de Mercado Libre
        Este endpoint NO requiere {tienda_id} en la URL, permitiendo que Mercado Libre
        redirija a una URL fija como /api/tiendas/mercadolibre/callback/
        
        GET: Maneja la redirección desde Mercado Libre (obtiene el código)
        POST: Intercambia el código por tokens
        """
        # Obtener tienda_id del request (puede venir en query params, body, o state)
        tienda_id = request.query_params.get('tienda_id') or request.data.get('tienda_id')
        tienda = None
        
        # Manejar GET (redirección desde Mercado Libre con code en query params)
        if request.method == 'GET':
            state = request.query_params.get('state')  # El state puede contener tienda_id
            
            # PRIORIDAD 1: Si viene state, extraer tienda_id de ahí (es lo más confiable)
            if state:
                try:
                    # El state puede venir en formato "tienda_id:numero" (ej: "uuid:1")
                    # Extraer solo la parte del UUID (antes del primer :)
                    if ':' in state:
                        # Dividir por ':' y tomar la primera parte (el UUID)
                        tienda_id = state.split(':')[0]
                    elif len(state) > 30:  # Probablemente es un UUID sin separador
                        tienda_id = state
                    
                    if tienda_id:
                        tienda = Tienda.objects.get(id=tienda_id)
                        logger.info(f"Tienda identificada desde state: {tienda_id}")
                except (ValueError, Tienda.DoesNotExist) as e:
                    logger.warning(f"No se pudo extraer tienda_id del state '{state}': {e}")
        
        # Si aún no tenemos tienda, intentar otras formas
        if not tienda:
            if tienda_id:
                try:
                    tienda = Tienda.objects.get(id=tienda_id)
                except Tienda.DoesNotExist:
                    return Response(
                        {'error': f'Tienda con ID {tienda_id} no encontrada'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Como último recurso, buscar tiendas configuradas con ML
                # Solo funciona si hay exactamente una tienda configurada
                tiendas_ml = Tienda.objects.filter(
                    plataforma_ecommerce='MERCADO_LIBRE'
                ).exclude(ml_app_id__isnull=True).exclude(ml_app_id='')
                
                if tiendas_ml.count() == 1:
                    tienda = tiendas_ml.first()
                    logger.info(f"Tienda identificada automáticamente (única configurada): {tienda.id}")
                elif tiendas_ml.count() == 0:
                    return Response(
                        {'error': 'No hay tiendas configuradas para Mercado Libre'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': 'No se pudo determinar la tienda. Múltiples tiendas configuradas. Proporciona tienda_id en el request o usa el parámetro state.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        
        # Si llegamos aquí sin tienda, es un error
        if not tienda:
            return Response(
                {'error': 'No se pudo determinar la tienda'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
            if code:
                # Si tenemos la tienda identificada, procesar directamente
                if tienda:
                    # Procesar el callback directamente
                    from .services.mercadolibre_service import MercadoLibreService
                    ml_service = MercadoLibreService(tienda)
                    
                    from django.conf import settings
                    if not settings.DEBUG:
                        redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
                    else:
                        scheme = request.scheme
                        host = request.get_host()
                        redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
                    
                    try:
                        tokens = ml_service.exchange_code_for_token(code, redirect_uri)
                        
                        # Guardar tokens
                        if hasattr(tienda, 'ml_access_token'):
                            tienda.ml_access_token = tokens['access_token']
                        if hasattr(tienda, 'ml_refresh_token'):
                            tienda.ml_refresh_token = tokens.get('refresh_token')
                        if hasattr(tienda, 'ml_user_id'):
                            tienda.ml_user_id = tokens.get('user_id')
                        if hasattr(tienda, 'ml_token_expires_at'):
                            expires_in = tokens.get('expires_in', 21600)
                            tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                        
                        tienda.save()
                        
                        # Retornar HTML de éxito para el navegador
                        return HttpResponse(
                            f'<html><body><h1>✅ Autenticación exitosa</h1>'
                            f'<p>La integración con Mercado Libre se configuró correctamente para la tienda: {tienda.nombre}</p>'
                            f'<p>Puedes cerrar esta ventana.</p>'
                            f'<script>setTimeout(function(){{window.close();}}, 3000);</script></body></html>',
                            content_type='text/html'
                        )
                    except Exception as e:
                        logger.error(f"Error procesando callback GET: {e}", exc_info=True)
                        return HttpResponse(
                            f'<html><body><h1>❌ Error en autenticación</h1>'
                            f'<p>Error: {str(e)}</p></body></html>',
                            content_type='text/html',
                            status=400
                        )
                else:
                    # No se pudo identificar la tienda, retornar info para POST manual
                    return Response({
                        'success': False,
                        'message': 'Código recibido pero no se pudo identificar la tienda. Usa POST con tienda_id.',
                        'code': code
                    })
            else:
                return Response({
                    'message': 'Endpoint de callback de Mercado Libre. Esperando código de autorización.'
                })
        
        # Manejar POST (intercambiar código por tokens)
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not self._ml_configured(tienda):
            return Response(
                {'error': 'La tienda no está configurada para Mercado Libre'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        code = request.data.get('code') or request.query_params.get('code')
        if not code:
            return Response(
                {'error': 'Código de autorización no proporcionado'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .services.mercadolibre_service import MercadoLibreService
        ml_service = MercadoLibreService(tienda)
        
        # Usar la URL fija configurada en Mercado Libre
        from django.conf import settings
        if not settings.DEBUG:
            redirect_uri = 'https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/'
        else:
            scheme = request.scheme
            host = request.get_host()
            redirect_uri = f"{scheme}://{host}/api/tiendas/mercadolibre/callback/"
        
        try:
            tokens = ml_service.exchange_code_for_token(code, redirect_uri)
            
            # Guardar tokens en la tienda
            if hasattr(tienda, 'ml_access_token'):
                tienda.ml_access_token = tokens['access_token']
            if hasattr(tienda, 'ml_refresh_token'):
                tienda.ml_refresh_token = tokens.get('refresh_token')
            if hasattr(tienda, 'ml_user_id'):
                tienda.ml_user_id = tokens.get('user_id')
            
            # Calcular fecha de expiración
            if hasattr(tienda, 'ml_token_expires_at'):
                expires_in = tokens.get('expires_in', 21600)
                tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            tienda.save()
            
            return Response({
                'success': True,
                'message': 'Autenticación exitosa',
                'user_id': getattr(tienda, 'ml_user_id', None)
            })
        except Exception as e:
            logger.error(f"Error en callback OAuth público: {e}", exc_info=True)
            return Response(
                {'error': f'Error al procesar el callback: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='mercadolibre/items')
    def ml_list_items(self, request, pk=None):
        """
        Lista los productos/publicaciones del vendedor en Mercado Libre para selección.
        GET /api/tiendas/{id}/mercadolibre/items/?limit=100&offset=0
        """
        try:
            tienda = self.get_object()
            if not self._ml_fields_exist(tienda) or not self._ml_configured(tienda):
                return Response({'error': 'Integración ML no configurada'}, status=status.HTTP_400_BAD_REQUEST)
            if not getattr(tienda, 'ml_access_token', None):
                return Response({'error': 'Complete el flujo OAuth primero.'}, status=status.HTTP_400_BAD_REQUEST)
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            limit = min(int(request.query_params.get('limit', 100)), 200)
            offset = int(request.query_params.get('offset', 0))
            data = ml_service.get_items_with_details(limit=limit, offset=offset)
            return Response(data, status=status.HTTP_200_OK)
        except MercadoLibreReconnectRequired as e:
            return Response({'error': str(e), 'reconnect_required': True}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error listando items ML: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/import-products')
    def ml_import_products(self, request, pk=None):
        """
        Importa productos desde Mercado Libre hacia Total Stock (sincronización inversa).
        POST /api/tiendas/{id}/mercadolibre/import-products/
        Body: {"solo_nuevos": true} - si true, solo importa no vinculados
              {"ml_item_ids": ["MLA123", ...]} - importar solo los items seleccionados
        """
        try:
            tienda = self.get_object()
            
            if not self._ml_fields_exist(tienda):
                return Response(
                    {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not self._ml_configured(tienda):
                return Response(
                    {'error': 'La tienda no está configurada para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not getattr(tienda, 'ml_access_token', None):
                return Response(
                    {'error': 'No hay token de acceso configurado. Complete el flujo OAuth primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            
            solo_nuevos = request.data.get('solo_nuevos', True)
            ml_item_ids = request.data.get('ml_item_ids', None)
            
            if ml_item_ids:
                all_item_ids = list(ml_item_ids)
            else:
                all_item_ids = []
                offset = 0
                limit = 50
                while True:
                    items_data = ml_service.get_items(limit=limit, offset=offset)
                    results = items_data.get('results', [])
                    if not results:
                        break
                    all_item_ids.extend(results)
                    offset += limit
                    if offset >= items_data.get('paging', {}).get('total', 0):
                        break
            
            import_results = {'success': 0, 'errors': 0, 'details': [], 'actualizados': 0}
            
            for ml_item_id in all_item_ids:
                try:
                    # Si solo_nuevos (y no es importación por selección) y ya existe vinculado, omitir
                    if not ml_item_ids and solo_nuevos and Producto.objects.filter(tienda=tienda, ml_item_id=ml_item_id).exists():
                        continue
                    
                    # Obtener datos completos del item
                    item_data = ml_service.get_item(ml_item_id)
                    if not item_data:
                        import_results['errors'] += 1
                        import_results['details'].append({
                            'ml_item_id': ml_item_id,
                            'nombre': ml_item_id,
                            'status': 'error',
                            'message': 'No se pudo obtener información del item'
                        })
                        continue
                    
                    producto_existia = Producto.objects.filter(tienda=tienda, ml_item_id=ml_item_id).exists()
                    producto = ml_service.create_producto_from_ml_item(tienda, item_data)
                    
                    if producto:
                        if producto_existia:
                            import_results['actualizados'] += 1
                            import_results['details'].append({
                                'producto_id': str(producto.id),
                                'ml_item_id': ml_item_id,
                                'nombre': producto.nombre,
                                'status': 'success',
                                'message': 'Producto actualizado'
                            })
                        else:
                            import_results['success'] += 1
                            import_results['details'].append({
                                'producto_id': str(producto.id),
                                'ml_item_id': ml_item_id,
                                'nombre': producto.nombre,
                                'status': 'success',
                                'message': 'Producto importado'
                            })
                    else:
                        import_results['errors'] += 1
                        import_results['details'].append({
                            'ml_item_id': ml_item_id,
                            'nombre': item_data.get('title', ml_item_id),
                            'status': 'error',
                            'message': 'No se pudo crear el producto'
                        })
                        
                except Exception as e:
                    import_results['errors'] += 1
                    import_results['details'].append({
                        'ml_item_id': ml_item_id,
                        'nombre': ml_item_id,
                        'status': 'error',
                        'message': str(e)[:200]
                    })
                    logger.error(f"Error importando item {ml_item_id}: {e}", exc_info=True)
            
            total = import_results['success'] + import_results['errors'] + import_results['actualizados']
            return Response({
                'message': f'Importación completada: {import_results["success"]} nuevos, {import_results["actualizados"]} actualizados, {import_results["errors"]} errores',
                'results': import_results,
                'total': total,
                'success': import_results['success'],
                'actualizados': import_results['actualizados'],
                'errors': import_results['errors']
            })
            
        except MercadoLibreReconnectRequired as e:
            return Response(
                {'error': str(e), 'reconnect_required': True},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al importar productos desde ML: {e}", exc_info=True)
            return Response(
                {'error': f'Error al importar productos: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/update-existing-products')
    def ml_update_existing_products(self, request, pk=None):
        """
        Actualiza precio y stock de productos que ya están vinculados con ML (desde ML hacia Total Stock).
        POST /api/tiendas/{id}/mercadolibre/update-existing-products/
        """
        try:
            tienda = self.get_object()
            if not self._ml_fields_exist(tienda) or not self._ml_configured(tienda):
                return Response({'error': 'Integración ML no configurada'}, status=status.HTTP_400_BAD_REQUEST)
            if not getattr(tienda, 'ml_access_token', None):
                return Response({'error': 'Complete el flujo OAuth primero.'}, status=status.HTTP_400_BAD_REQUEST)
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            ml_service = MercadoLibreService(tienda)
            
            productos = Producto.objects.filter(tienda=tienda, ml_item_id__isnull=False).exclude(ml_item_id='')
            results = {'success': 0, 'errors': 0, 'details': []}
            
            for producto in productos[:50]:
                try:
                    item_data = ml_service.get_item(producto.ml_item_id)
                    if not item_data:
                        results['errors'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': 'No se pudo obtener item'})
                        continue
                    out = ml_service.create_producto_from_ml_item(tienda, item_data)
                    if out:
                        results['success'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'success', 'message': 'Actualizado'})
                    else:
                        results['errors'] += 1
                        results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': 'Falló'})
                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({'nombre': producto.nombre, 'status': 'error', 'message': str(e)[:150]})
            
            return Response({
                'success': results['success'],
                'errors': results['errors'],
                'details': results['details']
            }, status=status.HTTP_200_OK)
        except MercadoLibreReconnectRequired as e:
            return Response({'error': str(e), 'reconnect_required': True}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error actualizando productos existentes: {e}", exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='mercadolibre/disconnect')
    def ml_disconnect(self, request, pk=None):
        """
        Desconecta la integración de Mercado Libre (borra tokens).
        Después el usuario puede volver a autorizar con la misma o otra cuenta/App.
        """
        tienda = self.get_object()
        if not self._ml_fields_exist(tienda):
            return Response(
                {'error': 'Los campos de Mercado Libre no están disponibles.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        tienda.ml_access_token = None
        tienda.ml_refresh_token = None
        if hasattr(tienda, 'ml_token_expires_at'):
            tienda.ml_token_expires_at = None
        tienda.save()
        return Response({
            'success': True,
            'message': 'Integración de Mercado Libre desconectada. Podés volver a conectar desde Configuración > Mercado Libre.'
        })

    @action(detail=True, methods=['post'], url_path='mercadolibre/sync-stock')
    def ml_sync_stock(self, request, pk=None):
        """
        Actualiza solo el stock de productos ya sincronizados con Mercado Libre
        POST /api/tiendas/{id}/mercadolibre/sync-stock/
        Body opcional: {"producto_ids": ["uuid1", "uuid2"]} - Si no se especifica, actualiza todos
        """
        try:
            tienda = self.get_object()
            
            if not self._ml_fields_exist(tienda):
                return Response(
                    {'error': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not self._ml_configured(tienda):
                return Response(
                    {'error': 'La tienda no está configurada para Mercado Libre'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not getattr(tienda, 'ml_access_token', None):
                return Response(
                    {'error': 'No hay token de acceso configurado. Complete el flujo OAuth primero.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
            
            ml_service = MercadoLibreService(tienda)
            
            # Obtener parámetros opcionales del request
            producto_ids = request.data.get('producto_ids', None)
            
            # Obtener productos que ya están sincronizados
            # Primero intentar con productos que tienen ml_item_id
            if producto_ids:
                productos = Producto.objects.filter(
                    tienda=tienda, 
                    id__in=producto_ids,
                    ml_item_id__isnull=False
                ).exclude(ml_item_id='')
            else:
                # Actualizar todos los productos sincronizados (que tengan ml_item_id)
                productos = Producto.objects.filter(
                    tienda=tienda,
                    ml_item_id__isnull=False
                ).exclude(ml_item_id='')
            
            # Inicializar sync_results primero
            sync_results = {
                'success': 0,
                'errors': 0,
                'details': [],
                'total_encontrados': 0
            }
            
            # Log para debugging
            total_productos = productos.count()
            logger.info(f"Productos encontrados para actualizar stock: {total_productos}")
            sync_results['total_encontrados'] = total_productos
            
            # Si no hay productos con ml_item_id, buscar productos sincronizados sin ml_item_id
            if total_productos == 0:
                productos_sin_item_id = Producto.objects.filter(
                    tienda=tienda,
                    ml_sincronizado=True
                ).filter(
                    Q(ml_item_id__isnull=True) | Q(ml_item_id='')
                )
                
                count_sin_item_id = productos_sin_item_id.count()
                logger.warning(f"No se encontraron productos con ml_item_id. "
                             f"Productos con ml_sincronizado=True pero sin ml_item_id: {count_sin_item_id}")
                
                # Intentar buscar el ml_item_id en Mercado Libre para estos productos
                if count_sin_item_id > 0:
                    logger.info(f"Intentando recuperar ml_item_id desde Mercado Libre para {count_sin_item_id} productos...")
                    productos_recuperados = 0
                    for prod in productos_sin_item_id[:10]:  # Limitar a 10 para no sobrecargar
                        try:
                            # Buscar el producto en ML por título (esto es aproximado)
                            # Nota: ML no tiene un endpoint directo de búsqueda por seller y título,
                            # así que esto es una aproximación. Mejor sería guardar el ml_item_id correctamente.
                            logger.warning(f"Producto {prod.nombre} (ID: {prod.id}) tiene ml_sincronizado=True pero no tiene ml_item_id. "
                                        f"Por favor, vuelve a sincronizar este producto para obtener el ml_item_id.")
                        except Exception as e:
                            logger.error(f"Error al intentar recuperar ml_item_id para {prod.nombre}: {e}")
                    
                    # Agregar estos productos a la lista pero con un mensaje de advertencia
                    sync_results['details'].append({
                        'status': 'warning',
                        'message': f'{count_sin_item_id} producto(s) tienen ml_sincronizado=True pero no tienen ml_item_id. '
                                 f'Por favor, vuelve a sincronizar estos productos para actualizar su stock.'
                    })
            
            # Actualizar cada producto (limitar a 20 productos por vez)
            productos_list = list(productos[:20])
            if total_productos > 20:
                logger.warning(f"Se actualizarán solo los primeros 20 de {total_productos} productos")
            
            for producto in productos_list:
                try:
                    logger.info(f"Actualizando stock de {producto.nombre} (ML Item: {producto.ml_item_id}): {producto.stock}")
                    updated_item = ml_service.sync_stock(producto)
                    
                    sync_results['success'] += 1
                    sync_results['details'].append({
                        'producto_id': str(producto.id),
                        'nombre': producto.nombre,
                        'ml_item_id': producto.ml_item_id,
                        'stock_actualizado': producto.stock,
                        'status': 'success',
                        'message': f'Stock actualizado a {producto.stock}'
                    })
                    
                except Exception as e:
                    sync_results['errors'] += 1
                    error_msg = str(e)
                    
                    # Extraer detalles del error
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_data = e.response.json()
                            error_msg = f"{e.response.status_code}: {error_data.get('message', str(error_data))}"
                        except:
                            error_msg = f"{e.response.status_code}: {e.response.text[:200]}"
                    
                    logger.error(f"Error al actualizar stock de {producto.nombre}: {error_msg}")
                    sync_results['details'].append({
                        'producto_id': str(producto.id),
                        'nombre': producto.nombre,
                        'ml_item_id': producto.ml_item_id,
                        'status': 'error',
                        'error': error_msg
                    })
            
            return Response(sync_results, status=status.HTTP_200_OK)
            
        except MercadoLibreReconnectRequired as e:
            return Response(
                {'error': str(e), 'reconnect_required': True},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al sincronizar stock: {e}", exc_info=True)
            return Response(
                {'error': f'Error al sincronizar stock: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get', 'post'], url_path='mercadolibre/webhook')
    def ml_webhook(self, request, pk=None):
        """
        Endpoint para recibir notificaciones de Mercado Libre cuando se vende un producto
        GET/POST /api/tiendas/{id}/mercadolibre/webhook/
        
        GET: Validación inicial de Mercado Libre (verifica que el endpoint existe)
        POST: Notificaciones reales de Mercado Libre
        
        Mercado Libre enviará notificaciones cuando:
        - Se crea una orden/pedido
        - Se confirma un pago
        - Se cancela una orden
        """
        try:
            # Intentar obtener la tienda usando pk del kwargs o del request
            tienda_id = pk or self.kwargs.get('pk')
            
            if not tienda_id:
                logger.warning("Webhook llamado sin ID de tienda")
                return Response({
                    'status': 'error',
                    'message': 'ID de tienda no proporcionado'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            try:
                tienda = Tienda.objects.get(pk=tienda_id)
            except Tienda.DoesNotExist:
                # Si no se encuentra la tienda, loguear y retornar 200 OK para que ML no reenvíe
                logger.warning(f"Tienda no encontrada para webhook: {tienda_id}")
                return Response({
                    'status': 'error',
                    'message': f'Tienda con ID {tienda_id} no encontrada en la base de datos'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            except Exception as e:
                logger.error(f"Error al obtener tienda {tienda_id}: {str(e)}")
                return Response({
                    'status': 'error',
                    'message': f'Error al obtener tienda: {str(e)}'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            # Verificar si los campos de ML existen
            if not self._ml_fields_exist(tienda):
                logger.warning(f"Campos de ML no disponibles para tienda {tienda.id}")
                return Response({
                    'status': 'error',
                    'message': 'Los campos de Mercado Libre no están disponibles. Por favor, aplica las migraciones primero.'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            if not self._ml_configured(tienda):
                logger.warning(f"Tienda {tienda.id} no está configurada para Mercado Libre")
                return Response({
                    'status': 'error',
                    'message': 'La tienda no está configurada para Mercado Libre'
                }, status=status.HTTP_200_OK)  # 200 OK para que ML no reenvíe
            
            # Manejar petición GET (validación de Mercado Libre)
            if request.method == 'GET':
                # Mercado Libre hace una petición GET para validar que el endpoint existe
                # Debe responder con 200 OK
                logger.info(f"Validación de webhook desde Mercado Libre para tienda {tienda.id}")
                return Response({
                    'status': 'ok',
                    'message': 'Webhook configurado correctamente',
                    'tienda_id': str(tienda.id)
                }, status=status.HTTP_200_OK)
            
            # Mercado Libre envía notificaciones en formato JSON
            # Topic "orders" (legacy) o "orders_v2" (recomendado desde 2019+)
            # Estructura: {"resource": "/orders/123456", "topic": "orders_v2"}
            resource = request.data.get('resource', '')
            topic = request.data.get('topic', '')
            
            # Aceptar ambos topics: orders (legacy) y orders_v2 (recomendado por ML)
            topic_orders = topic in ('orders', 'orders_v2')
            
            logger.info(f"Notificación recibida de ML: topic={topic}, resource={resource}")
            
            if topic_orders and resource and '/orders/' in resource:
                # Extraer el ID de la orden (soporta /orders/123 o /orders/123?params)
                order_id = resource.split('/orders/')[-1].split('?')[0].strip()
                
                try:
                    from .services.mercadolibre_service import MercadoLibreService, MercadoLibreReconnectRequired
                    
                    # Evitar procesar la misma orden dos veces
                    if Venta.objects.filter(tienda=tienda, origen_mercadolibre=True, ml_order_id=order_id).exists():
                        logger.info(f"Orden {order_id} ya procesada anteriormente, omitiendo")
                        return Response({
                            'status': 'success',
                            'message': 'Orden ya procesada',
                            'order_id': order_id
                        }, status=status.HTTP_200_OK)
                    
                    ml_service = MercadoLibreService(tienda)
                    
                    # Obtener información de la orden desde ML
                    order = ml_service.get_order(order_id)
                    
                    if order:
                        # Procesar la orden y actualizar stock
                        order_status = order.get('status', '')
                        
                        # Solo procesar órdenes confirmadas o pagadas
                        # paid = venta confirmada y cobrada (estado típico tras cobro)
                        if order_status in ['confirmed', 'payment_required', 'payment_in_process', 'paid']:
                            order_items = order.get('order_items') or order.get('items') or []
                            
                            # Obtener el método de pago "Mercado Libre"
                            try:
                                metodo_pago_ml = MetodoPago.objects.get(nombre='Mercado Libre', activo=True)
                            except MetodoPago.DoesNotExist:
                                logger.error(f"Método de pago 'Mercado Libre' no encontrado. Creando automáticamente...")
                                metodo_pago_ml = MetodoPago.objects.create(
                                    nombre='Mercado Libre',
                                    descripcion='Ventas realizadas a través de Mercado Libre',
                                    activo=True,
                                    es_financiero=True
                                )
                            
                            # Preparar detalles de venta y calcular totales (arancel + costo envío por producto)
                            detalles_venta = []
                            total_venta = Decimal('0.00')
                            total_arancel = Decimal('0.00')
                            total_costo_envio = Decimal('0.00')
                            
                            for item in order_items:
                                ml_item_id = item.get('item', {}).get('id')
                                quantity = item.get('quantity', 0)
                                
                                # Precio real de venta: unit_price es "después de descuentos" (ML)
                                # NO usar full_unit_price ni item.price como prioritario (son precio original)
                                unit_price = Decimal(str(item.get('unit_price', 0)))
                                if unit_price <= 0:
                                    # Fallback: total pagado por este ítem / cantidad
                                    item_total = Decimal(str(item.get('total_amount', 0)))
                                    if item_total > 0 and quantity > 0:
                                        unit_price = item_total / quantity
                                if unit_price <= 0:
                                    item_data = item.get('item', {})
                                    unit_price = Decimal(str(item_data.get('price', 0)))
                                if unit_price <= 0:
                                    try:
                                        producto_temp = Producto.objects.get(tienda=tienda, ml_item_id=ml_item_id)
                                        unit_price = producto_temp.precio
                                        logger.warning(f"Precio no en orden ML, usando sistema: ${unit_price} para {producto_temp.nombre}")
                                    except Producto.DoesNotExist:
                                        unit_price = Decimal('0.00')
                                        logger.error(f"No se pudo obtener precio para item {ml_item_id}")
                                
                                if ml_item_id and unit_price > 0:
                                    # Buscar el producto en nuestro sistema por ml_item_id
                                    # Si no existe, crearlo automáticamente desde los datos de ML (sincronización inversa)
                                    producto = None
                                    try:
                                        producto = Producto.objects.get(
                                            tienda=tienda,
                                            ml_item_id=ml_item_id
                                        )
                                    except Producto.DoesNotExist:
                                        # Producto no vinculado: importarlo desde ML para poder registrar la venta
                                        try:
                                            item_full = ml_service.get_item(ml_item_id)
                                            if item_full:
                                                producto = ml_service.create_producto_from_ml_item(tienda, item_full)
                                                if producto:
                                                    logger.info(f"Producto creado automáticamente desde orden ML: {producto.nombre} (ml_item_id: {ml_item_id})")
                                        except Exception as import_err:
                                            logger.error(f"No se pudo importar producto {ml_item_id} desde ML: {import_err}", exc_info=True)
                                    
                                    if producto:
                                        
                                        # Calcular subtotal del item
                                        subtotal_item = unit_price * quantity
                                        total_venta += subtotal_item
                                        
                                        # Calcular arancel y costo envío según ArancelMercadoLibreProducto
                                        arancel_item = Decimal('0.00')
                                        costo_envio_item = Decimal('0.00')
                                        if ArancelMercadoLibreProducto is not None:
                                            try:
                                                arancel_ml = ArancelMercadoLibreProducto.objects.filter(
                                                    tienda=tienda,
                                                    producto=producto
                                                ).first()
                                                if arancel_ml:
                                                    arancel_porcentaje = arancel_ml.arancel_porcentaje
                                                    arancel_item = subtotal_item * (arancel_porcentaje / Decimal('100'))
                                                    total_arancel += arancel_item
                                                    costo_envio_item = (arancel_ml.costo_envio or Decimal('0')) * quantity
                                                    total_costo_envio += costo_envio_item
                                                    logger.info(f"Arancel {arancel_porcentaje}% + envío ${costo_envio_item} para {producto.nombre}")
                                            except Exception as e:
                                                logger.error(f"Error al calcular arancel/envío para producto {producto.nombre}: {e}")
                                        
                                        # Agregar detalle de venta
                                        detalles_venta.append({
                                            'producto': producto.id,
                                            'cantidad': quantity,
                                            'precio_unitario': float(unit_price),
                                            'costo_unitario': float(producto.costo) if producto.costo else None,
                                            'subtotal': float(subtotal_item),
                                            'arancel_item': float(arancel_item)
                                        })
                                        
                                        # Actualizar stock: restar la cantidad vendida
                                        producto.stock = max(0, producto.stock - quantity)
                                        producto.save()
                                        
                                        logger.info(f"Stock actualizado para {producto.nombre}: -{quantity} unidades (nuevo stock: {producto.stock})")
                                    else:
                                        logger.warning(f"Producto con ml_item_id {ml_item_id} no encontrado y no se pudo importar desde ML")
                            
                            # Crear la venta en el sistema si hay detalles
                            if detalles_venta:
                                try:
                                    usuario_ml, created = User.objects.get_or_create(
                                        username='mercadolibre',
                                        defaults={
                                            'first_name': 'Mercado Libre',
                                            'is_staff': False,
                                            'is_active': True,
                                        }
                                    )
                                    if created:
                                        usuario_ml.set_unusable_password()
                                        usuario_ml.save()
                                    venta = Venta.objects.create(
                                        tienda=tienda,
                                        metodo_pago=metodo_pago_ml.nombre,
                                        total=total_venta,
                                        arancel_total=total_arancel,
                                        costo_envio_ml=total_costo_envio,
                                        origen_mercadolibre=True,
                                        ml_order_id=order_id,
                                        usuario=usuario_ml,
                                        fecha_venta=timezone.now()
                                    )
                                    
                                    # Crear los detalles de venta
                                    for detalle_data in detalles_venta:
                                        producto_obj = Producto.objects.get(id=detalle_data['producto'])
                                        DetalleVenta.objects.create(
                                            venta=venta,
                                            producto=producto_obj,
                                            cantidad=detalle_data['cantidad'],
                                            precio_unitario=Decimal(str(detalle_data['precio_unitario'])),
                                            costo_unitario=Decimal(str(detalle_data['costo_unitario'])) if detalle_data['costo_unitario'] else None,
                                            subtotal=Decimal(str(detalle_data['subtotal']))
                                        )
                                    
                                    logger.info(f"Venta de Mercado Libre registrada: ID {venta.id}, Total: ${total_venta}, Arancel: ${total_arancel}, Envío: ${total_costo_envio}")
                                    
                                    # Enviar notificación push (igual que en ventas manuales)
                                    try:
                                        from .services.notificaciones_service import NotificacionesService
                                        NotificacionesService.enviar_notificacion_venta(venta)
                                    except Exception as notif_err:
                                        logger.warning(f"Error al enviar notificación push por venta ML {venta.id}: {notif_err}")
                                    
                                    # Facturación automática: intentar emitir factura para ventas de ML
                                    if venta.tienda.tipo_facturacion and venta.tienda.tipo_facturacion != 'NINGUNA':
                                        try:
                                            # Preferir datos de facturación de ML (nombre, DNI, dirección) si existe el endpoint
                                            cliente_nombre = 'Consumidor Final'
                                            cliente_domicilio = ''
                                            cliente_cuit_dni = ''
                                            billing = ml_service.get_order_billing_info(order_id)
                                            # API ML v2: datos están en buyer.billing_info (name, last_name, identification, address)
                                            bi = {}
                                            if billing and isinstance(billing, dict):
                                                bi = billing.get('buyer', {}) or {}
                                                if isinstance(bi, dict):
                                                    bi = bi.get('billing_info', {}) or {}
                                            if not isinstance(bi, dict):
                                                bi = {}
                                            if bi:
                                                first = (bi.get('name') or bi.get('first_name') or '').strip()
                                                last = (bi.get('last_name') or '').strip()
                                                if first or last:
                                                    cliente_nombre = f"{first} {last}".strip()[:255] or cliente_nombre
                                                ident = bi.get('identification', {})
                                                if isinstance(ident, dict):
                                                    cliente_cuit_dni = (ident.get('number') or '').strip()
                                                elif isinstance(ident, str):
                                                    cliente_cuit_dni = ident.strip()
                                                addr = bi.get('address', {})
                                                if isinstance(addr, dict):
                                                    street = (addr.get('street_name') or addr.get('address_line') or '')
                                                    number = (addr.get('street_number') or '')
                                                    city = (addr.get('city_name') or (addr.get('city', {}).get('name') if isinstance(addr.get('city'), dict) else ''))
                                                    state = (addr.get('state', {}).get('name') if isinstance(addr.get('state'), dict) else '') or addr.get('state_name', '')
                                                    zipcode = addr.get('zip_code', '')
                                                    parts = [p for p in [street, number, city, state, zipcode] if p]
                                                    if parts:
                                                        cliente_domicilio = ' '.join(parts)[:255]
                                            # Fallback: datos desde la orden (buyer, shipment)
                                            if cliente_nombre == 'Consumidor Final' or not cliente_domicilio:
                                                buyer = order.get('buyer', {})
                                                if buyer and cliente_nombre == 'Consumidor Final':
                                                    nickname = buyer.get('nickname', '')
                                                    if nickname:
                                                        cliente_nombre = f"Comprador ML {nickname}"[:255]
                                                if not cliente_domicilio:
                                                    shipment = order.get('shipment', {}) or order.get('shipping', {})
                                                    if isinstance(shipment, dict):
                                                        receiver_addr = shipment.get('receiver_address', {}) or shipment.get('address', {})
                                                        if isinstance(receiver_addr, dict):
                                                            address_line = receiver_addr.get('address_line', '') or receiver_addr.get('street_name', '')
                                                            city = receiver_addr.get('city', {}).get('name', '') if isinstance(receiver_addr.get('city'), dict) else ''
                                                            if address_line or city:
                                                                cliente_domicilio = f"{address_line} {city}".strip()[:255]
                                            
                                            cliente_data = {
                                                'cliente_nombre': cliente_nombre,
                                                'cliente_cuit': cliente_cuit_dni,
                                                'cliente_domicilio': cliente_domicilio or 'Sin especificar',
                                                'cliente_tipo_documento': '99',
                                                'cliente_condicion_iva': 'CF'
                                            }
                                            exito, datos_factura, error = FacturacionService(venta.tienda).emitir_factura(venta, cliente_data)
                                            if exito:
                                                Factura.objects.create(
                                                    venta=venta,
                                                    tienda=venta.tienda,
                                                    numero_comprobante=datos_factura.get('numero_comprobante'),
                                                    punto_venta=datos_factura.get('punto_venta', venta.tienda.punto_venta),
                                                    tipo_comprobante=datos_factura.get('tipo_comprobante', 'B'),
                                                    cliente_nombre=cliente_data['cliente_nombre'],
                                                    cliente_cuit=cliente_data.get('cliente_cuit', ''),
                                                    cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                                                    cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                                                    cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                                                    subtotal=datos_factura.get('subtotal', venta.total),
                                                    impuesto_iva=datos_factura.get('impuesto_iva', Decimal('0.00')),
                                                    total=datos_factura.get('total', venta.total),
                                                    estado='EMITIDA',
                                                    sistema_facturacion=venta.tienda.tipo_facturacion,
                                                    cae=datos_factura.get('cae'),
                                                    fecha_vencimiento_cae=datos_factura.get('fecha_vencimiento_cae'),
                                                    numero_comprobante_afip=datos_factura.get('numero_comprobante_afip'),
                                                    respuesta_bruta=datos_factura.get('respuesta_bruta'),
                                                )
                                                venta.facturada = True
                                                venta.cliente_nombre = cliente_data['cliente_nombre']
                                                venta.cliente_cuit = cliente_data.get('cliente_cuit', '') or None
                                                venta.cliente_domicilio = cliente_data.get('cliente_domicilio', '')
                                                venta.save()
                                                logger.info(f"Factura emitida automáticamente para venta ML {venta.id}")
                                            else:
                                                Factura.objects.create(
                                                    venta=venta,
                                                    tienda=venta.tienda,
                                                    punto_venta=venta.tienda.punto_venta,
                                                    tipo_comprobante='B',
                                                    cliente_nombre=cliente_data['cliente_nombre'],
                                                    cliente_cuit='', cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                                                    cliente_tipo_documento='99', cliente_condicion_iva='CF',
                                                    subtotal=venta.total, impuesto_iva=Decimal('0.00'), total=venta.total,
                                                    estado='ERROR',
                                                    sistema_facturacion=venta.tienda.tipo_facturacion,
                                                    error_mensaje=error,
                                                )
                                                logger.warning(f"No se pudo facturar automáticamente venta ML {venta.id}: {error}")
                                        except Exception as fact_err:
                                            logger.warning(f"Error al facturar automáticamente venta ML {venta.id}: {fact_err}", exc_info=True)
                                    
                                except Exception as e:
                                    logger.error(f"Error al crear venta desde orden ML {order_id}: {e}", exc_info=True)
                        else:
                            logger.info(f"Orden {order_id} con estado '{order_status}' no procesada (solo: confirmed, payment_required, payment_in_process, paid)")
                        
                        return Response({
                            'status': 'success',
                            'message': 'Orden procesada correctamente',
                            'order_id': order_id
                        })
                    else:
                        logger.warning(f"No se pudo obtener información de la orden {order_id}")
                        return Response({
                            'status': 'warning',
                            'message': 'Orden no encontrada o no se pudo obtener información'
                        }, status=status.HTTP_200_OK)
                        
                except MercadoLibreReconnectRequired as e:
                    logger.warning(f"Webhook ML: integración requiere reconexión (orden {order_id}): {e}")
                    return Response({
                        'status': 'error',
                        'message': 'Integración de Mercado Libre desconectada. Reconectá desde Configuración.'
                    }, status=status.HTTP_200_OK)
                except Exception as e:
                    logger.error(f"Error al procesar orden de ML: {e}", exc_info=True)
                    # Retornar 200 para que ML no reenvíe la notificación
                    return Response({
                        'status': 'error',
                        'message': f'Error al procesar orden: {str(e)}'
                    }, status=status.HTTP_200_OK)
            
            # Si no es una notificación de orden, solo confirmar recepción
            return Response({
                'status': 'received',
                'message': 'Notificación recibida'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error en webhook de ML: {e}", exc_info=True)
            # Siempre retornar 200 para que ML no reenvíe la notificación
            return Response({
                'status': 'error',
                'message': f'Error: {str(e)}'
            }, status=status.HTTP_200_OK)

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.all().order_by('username')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        # Solo superusuarios pueden gestionar usuarios
        if not user.is_superuser:
            return User.objects.none()
        
        if tienda_slug:
            return queryset.filter(tienda__nombre=tienda_slug)
        
        return queryset

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        """Endpoint para cambiar la contraseña de un usuario"""
        if not request.user.is_superuser:
            return Response(
                {'error': 'No tienes permisos para cambiar contraseñas.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user = self.get_object()
        serializer = ChangePasswordSerializer(data=request.data)
        
        if serializer.is_valid():
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'status': 'Contraseña actualizada correctamente'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VentaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return VentaCreateSerializer
        return VentaSerializer

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        # Optimización: usar select_related para evitar consultas N+1
        # Nota: metodo_pago es CharField, no ForeignKey, por lo que no se puede usar en select_related
        queryset = Venta.objects.select_related('tienda', 'usuario', 'arancel_aplicado').order_by('-fecha_venta')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        # Para usuarios staff (no superuser), solo permitir ver ventas buscadas por ID
        if user.is_staff and not user.is_superuser:
            # Solo permitir ver ventas si se busca por ID o código de barras
            venta_id = self.request.query_params.get('id', None)
            if not venta_id:
                # Si no hay ID, retornar queryset vacío (no pueden ver todas las ventas)
                return Venta.objects.none()
            # Si hay ID, continuar con el filtro normal (se aplicará más abajo)
            if user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
            else:
                return Venta.objects.none()
        elif not user.is_superuser:
            if user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
            else:
                return Venta.objects.none()
        elif tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)

        fecha_venta_date = self.request.query_params.get('fecha_venta__date', None)
        if fecha_venta_date:
            queryset = queryset.filter(fecha_venta__date=fecha_venta_date)

        usuario = self.request.query_params.get('usuario', None)
        if usuario:
            queryset = queryset.filter(usuario=usuario)

        anulada = self.request.query_params.get('anulada', None)
        if anulada is not None:
            queryset = queryset.filter(anulada=anulada == 'true')

        # Buscar por ID de venta (puede venir con o sin guiones desde el código de barras)
        # También puede venir como código EAN13 (13 dígitos) que debemos convertir de vuelta al UUID
        venta_id = self.request.query_params.get('id', None)
        if venta_id:
            # Si es un código EAN13 (13 dígitos numéricos), buscar por los primeros caracteres del UUID
            # El código EAN13 se genera a partir de los primeros 12 caracteres hex del UUID
            # Conversión: a-f -> 0-5, 0-9 -> 0-9
            if len(venta_id) == 13 and venta_id.isdigit():
                # El código EAN13 tiene un dígito de control, así que usamos los primeros 12
                codigo_base = venta_id[:12]
                # Extraer el hash (los últimos 9 dígitos después del prefijo 779)
                if codigo_base.startswith('779'):
                    hash_9_digitos = codigo_base[3:]
                    # Buscar todas las ventas y verificar cuál genera este hash
                    # Como no podemos hacer búsqueda inversa fácil, iteramos sobre las ventas
                    ventas_match = []
                    for venta in queryset:
                        # Calcular el hash de esta venta (mismo algoritmo que en el frontend)
                        # Frontend usa: hash = (hash * 31 + char) % 1000000000
                        venta_id_str = str(venta.id).replace('-', '')
                        hash_calculado = 0
                        for char in venta_id_str:
                            hash_calculado = (hash_calculado * 31 + ord(char)) % 1000000000
                        hash_absoluto = abs(hash_calculado)
                        hash_str = str(hash_absoluto).zfill(9)[:9]  # zfill es como padStart en Python
                        if hash_str == hash_9_digitos:
                            ventas_match.append(venta.id)
                    
                    if ventas_match:
                        queryset = queryset.filter(id__in=ventas_match)
                    else:
                        queryset = queryset.none()
            else:
                # Si el ID viene sin guiones (del código de barras), intentar agregarlos en las posiciones correctas
                # Formato UUID: 8-4-4-4-12 caracteres
                cleaned_id = venta_id.replace('-', '')
                if len(cleaned_id) == 32:  # UUID sin guiones tiene 32 caracteres
                    # Formatear como UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
                    formatted_id = f"{cleaned_id[:8]}-{cleaned_id[8:12]}-{cleaned_id[12:16]}-{cleaned_id[16:20]}-{cleaned_id[20:]}"
                    try:
                        import uuid
                        # Validar que es un UUID válido
                        uuid.UUID(formatted_id)
                        queryset = queryset.filter(id=formatted_id)
                    except (ValueError, TypeError):
                        # Si no es un UUID válido, buscar por los primeros caracteres (para búsqueda parcial)
                        if len(cleaned_id) >= 8:
                            # Buscar ventas cuyo UUID empiece con estos caracteres
                            from django.db.models import Q
                            queryset = queryset.filter(Q(id__startswith=cleaned_id[:8]))
                elif len(cleaned_id) >= 8:
                    # Buscar por los primeros caracteres del UUID (viene del código de barras CODE128)
                    from django.db.models import Q
                    # Buscar ventas cuyo UUID (sin guiones) empiece con estos caracteres
                    queryset = queryset.filter(Q(id__startswith=cleaned_id[:8]) | Q(id__icontains=cleaned_id[:8]))
            
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """Sobrescribir retrieve para permitir acceso a ventas de nota de crédito relacionadas con cambios/devoluciones"""
        pk = kwargs.get('pk')
        user = request.user
        
        # Intentar obtener directamente por ID primero (sin filtros de queryset)
        try:
            instance = Venta.objects.get(pk=pk)
        except Venta.DoesNotExist:
            return Response(
                {'detail': 'No encontrado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error al obtener venta en retrieve: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Error al obtener la venta.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Verificar permisos básicos
        if not user.is_superuser:
            if not user.tienda or instance.tienda != user.tienda:
                # Si es una nota de crédito o diferencia pendiente relacionada con cambio/devolución, permitir acceso
                if instance.metodo_pago in ['Nota de Crédito', 'Pendiente'] and CambioDevolucion is not None:
                    try:
                        cambio_nota_credito = instance.nota_credito_origen.first()
                        cambio_diferencia = instance.cambio_devolucion_diferencia.first()
                    except:
                        cambio_nota_credito = None
                        cambio_diferencia = None
                    
                    # Si está relacionada con cambio/devolución, permitir acceso aunque sea de otra tienda
                    # (esto es necesario porque el cambio puede haberse procesado desde otra tienda)
                    if cambio_nota_credito or cambio_diferencia:
                        serializer = self.get_serializer(instance)
                        return Response(serializer.data)
                
                # Si no es nota de crédito relacionada o no tiene permisos, negar acceso
                return Response(
                    {'detail': 'No encontrado.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Para otras ventas o usuarios con permisos, usar el comportamiento estándar
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def anular(self, request, pk=None):
        # Verificar permisos: solo superusuarios pueden anular ventas
        if not request.user.is_superuser:
            return Response(
                {"error": "No tienes permiso para anular ventas. Solo los superusuarios pueden realizar esta acción."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Verificar si esta venta está relacionada con un cambio/devolución
        cambio_devolucion_afectado = None
        if CambioDevolucion is not None:
            try:
                # Verificar si es una nota de crédito
                cambio_nota_credito = venta.nota_credito_origen.first()
                if cambio_nota_credito:
                    cambio_devolucion_afectado = cambio_nota_credito
                    logger.info(f"⚠️ Anulando nota de crédito del cambio/devolución {cambio_nota_credito.id}")
                
                # Verificar si es una venta de diferencia pendiente
                if not cambio_devolucion_afectado:
                    cambio_diferencia = venta.cambio_devolucion_diferencia.first()
                    if cambio_diferencia:
                        cambio_devolucion_afectado = cambio_diferencia
                        logger.info(f"⚠️ Anulando venta de diferencia del cambio/devolución {cambio_diferencia.id}")
            except Exception as e:
                logger.warning(f"⚠️ Error al verificar cambio/devolución relacionado: {e}")
        
        # Anular la venta
        venta.anulada = True
        venta.save()

        # Si está relacionada con un cambio/devolución, revertir todos los cambios
        if cambio_devolucion_afectado:
            try:
                # Revertir el cambio/devolución completo:
                # 1. Restaurar stock de productos devueltos (que se habían restado del stock)
                # 2. Restar stock de productos nuevos que se habían agregado
                # 3. Restaurar los detalles de venta original que fueron marcados como anulados
                # 4. Marcar el cambio/devolución como cancelado
                
                for detalle_cambio in cambio_devolucion_afectado.detalles.all():
                    if detalle_cambio.accion == 'DEVOLVER':
                        # Cuando se devolvió un producto:
                        # - Se había restado del stock (restaurar)
                        # - El detalle de venta original fue marcado como anulado (restaurar)
                        if detalle_cambio.detalle_venta_original:
                            detalle_venta = detalle_cambio.detalle_venta_original
                            if detalle_venta.producto:
                                producto = detalle_venta.producto
                                producto.stock += detalle_cambio.cantidad
                                producto.save()
                                logger.info(f"✅ Stock restaurado para producto devuelto: {producto.nombre} (+{detalle_cambio.cantidad})")
                            
                            # Restaurar el detalle de venta original
                            if detalle_venta.anulado_individualmente:
                                detalle_venta.anulado_individualmente = False
                                # Restaurar la cantidad original si se había reducido
                                detalle_venta.cantidad += detalle_cambio.cantidad
                                detalle_venta.subtotal = detalle_venta.precio_unitario * detalle_venta.cantidad
                                detalle_venta.save()
                                logger.info(f"✅ Detalle de venta original restaurado: {detalle_venta.id}")
                    
                    elif detalle_cambio.accion == 'CAMBIAR':
                        # Cuando se cambió un producto:
                        # - El producto devuelto se había restado del stock (restaurar)
                        # - El producto nuevo se había agregado al stock (restar)
                        # - El detalle de venta original fue marcado como anulado (restaurar)
                        if detalle_cambio.detalle_venta_original:
                            detalle_venta = detalle_cambio.detalle_venta_original
                            if detalle_venta.producto:
                                producto_devuelto = detalle_venta.producto
                                producto_devuelto.stock += detalle_cambio.cantidad
                                producto_devuelto.save()
                                logger.info(f"✅ Stock restaurado para producto devuelto en cambio: {producto_devuelto.nombre} (+{detalle_cambio.cantidad})")
                            
                            # Restaurar el detalle de venta original
                            if detalle_venta.anulado_individualmente:
                                detalle_venta.anulado_individualmente = False
                                detalle_venta.cantidad += detalle_cambio.cantidad
                                detalle_venta.subtotal = detalle_venta.precio_unitario * detalle_venta.cantidad
                                detalle_venta.save()
                                logger.info(f"✅ Detalle de venta original restaurado en cambio: {detalle_venta.id}")
                        
                        if detalle_cambio.producto_nuevo:
                            producto_nuevo = detalle_cambio.producto_nuevo
                            producto_nuevo.stock -= detalle_cambio.cantidad
                            if producto_nuevo.stock < 0:
                                producto_nuevo.stock = 0
                            producto_nuevo.save()
                            logger.info(f"✅ Stock revertido para producto nuevo en cambio: {producto_nuevo.nombre} (-{detalle_cambio.cantidad})")
                    
                    elif detalle_cambio.accion == 'AGREGAR':
                        # Cuando se agregó un producto nuevo, se había restado del stock
                        # Al anular, debemos volver a agregarlo al stock
                        if detalle_cambio.producto_nuevo:
                            producto = detalle_cambio.producto_nuevo
                            producto.stock += detalle_cambio.cantidad
                            producto.save()
                            logger.info(f"✅ Stock restaurado para producto agregado: {producto.nombre} (+{detalle_cambio.cantidad})")
                
                # Recalcular el total de la venta original
                venta_original = cambio_devolucion_afectado.venta_original
                total_recalculado = sum(
                    d.subtotal for d in venta_original.detalles.all() 
                    if not d.anulado_individualmente
                )
                venta_original.total = total_recalculado
                venta_original.save()
                logger.info(f"✅ Total de venta original recalculado: ${total_recalculado}")
                
                # Marcar el cambio/devolución como cancelado
                cambio_devolucion_afectado.estado = 'CANCELADO'
                cambio_devolucion_afectado.save()
                logger.info(f"✅ Cambio/devolución {cambio_devolucion_afectado.id} marcado como CANCELADO")
                
            except Exception as e:
                logger.error(f"❌ Error al revertir cambio/devolución: {e}", exc_info=True)
        else:
            # Para ventas normales, solo restaurar el stock de los productos de esta venta
            detalles = DetalleVenta.objects.filter(venta=venta)
            for detalle in detalles:
                if detalle.producto and not detalle.anulado_individualmente:
                    producto = detalle.producto
                    producto.stock += detalle.cantidad
                    producto.save()
                    logger.info(f"✅ Stock restaurado para venta normal: {producto.nombre} (+{detalle.cantidad})")
        
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
        # Verificar permisos: solo superusuarios pueden anular detalles de venta
        if not request.user.is_superuser:
            return Response(
                {"error": "No tienes permiso para anular detalles de venta. Solo los superusuarios pueden realizar esta acción."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        detalle_id = request.data.get('detalle_id')
        if not detalle_id:
            return Response({"error": "Se requiere el ID del detalle de venta."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            detalle = DetalleVenta.objects.get(id=detalle_id, venta__id=pk)
        except DetalleVenta.DoesNotExist:
            return Response({"error": "Detalle de venta no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        
        if request.user.tienda != detalle.venta.tienda and not request.user.is_superuser:
            return Response({"error": "No tienes permiso para anular este detalle de venta."}, status=status.HTTP_403_FORBIDDEN)
        
        if detalle.anulado_individualmente:
            return Response({"error": "Este detalle de venta ya ha sido anulado individualmente."}, status=status.HTTP_400_BAD_REQUEST)
        
        if detalle.venta.anulada:
            return Response({"error": "No se puede anular un detalle de una venta que ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)

        if detalle.producto:
            producto = detalle.producto
            producto.stock += detalle.cantidad
            producto.save()
            detalle.anulado_individualmente = True
            detalle.save()
            
            venta = detalle.venta
            total_subtotal = sum(d.subtotal for d in venta.detalles.all() if not d.anulado_individualmente)
            
            # --- LÓGICA DE RECALCULO DE TOTAL CON DESCUENTO/RECARGO ---
            if venta.recargo_monto > 0:
                venta.total = total_subtotal + venta.recargo_monto
            elif venta.recargo_porcentaje > 0:
                venta.total = total_subtotal * (Decimal('1') + (venta.recargo_porcentaje / Decimal('100')))
            elif venta.descuento_monto > 0:
                venta.total = max(Decimal('0.00'), total_subtotal - venta.descuento_monto)
            elif venta.descuento_porcentaje > 0:
                venta.total = total_subtotal * (Decimal('1') - (venta.descuento_porcentaje / Decimal('100')))
            else:
                venta.total = total_subtotal
            # ---------------------------------------------------------

            # Recalcular arancel sobre el nuevo total si aplica
            if venta.arancel_aplicado:
                arancel_porcentaje = venta.arancel_aplicado.arancel_porcentaje
                venta.arancel_total = venta.total * (arancel_porcentaje / Decimal('100'))
            else:
                venta.arancel_total = Decimal('0.00') # Asegurar que es 0.00
            
            if not venta.detalles.filter(anulado_individualmente=False).exists():
                venta.anulada = True

            venta.save()
            
            return Response({"status": "Detalle de venta anulado con éxito y stock restaurado."}, status=status.HTTP_200_OK)
        else:
            detalle.anulado_individualmente = True
            detalle.save()

            venta = detalle.venta
            if not venta.detalles.filter(anulado_individualmente=False).exists():
                venta.anulada = True
                venta.save()

            return Response({"status": "Detalle de venta anulado con éxito, sin stock que restaurar."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def emitir_factura(self, request, pk=None):
        """Emitir una factura electrónica para una venta"""
        venta = get_object_or_404(Venta, pk=pk)
        
        # Validaciones
        if venta.anulada:
            return Response(
                {"error": "No se puede emitir factura para una venta anulada."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if venta.facturada:
            return Response(
                {"error": "Esta venta ya tiene una factura emitida."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar que la tienda tenga facturación configurada
        if venta.tienda.tipo_facturacion == 'NINGUNA':
            return Response(
                {"error": "La tienda no tiene configurado un sistema de facturación."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar permisos
        user = request.user
        if not user.is_superuser and user.tienda != venta.tienda:
            return Response(
                {"error": "No tienes permiso para emitir facturas de esta tienda."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar datos del cliente
        serializer = EmitirFacturaSerializer(data=request.data)
        if not serializer.is_valid():
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Error de validación en emitir_factura: {serializer.errors}")
            logger.error(f"Datos recibidos: {request.data}")
            return Response(
                {"error": "Error de validación", "detalles": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cliente_data = serializer.validated_data
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"=== Iniciando emisión de factura ===")
            logger.info(f"Venta ID: {venta.id}")
            logger.info(f"Tienda: {venta.tienda.nombre}")
            logger.info(f"Tipo facturación: {venta.tienda.tipo_facturacion}")
            logger.info(f"Datos del cliente: {cliente_data}")
            
            # Inicializar servicio de facturación
            facturacion_service = FacturacionService(venta.tienda)
            
            # Emitir factura
            logger.info(f"⚠️ Llamando a facturacion_service.emitir_factura...")
            exito, datos_factura, error = facturacion_service.emitir_factura(venta, cliente_data)
            logger.info(f"Resultado: exito={exito}, error={error}")
            
            if not exito:
                # Crear registro de factura con error
                factura = Factura.objects.create(
                    venta=venta,
                    tienda=venta.tienda,
                    punto_venta=venta.tienda.punto_venta,
                    tipo_comprobante='B',  # Por defecto Factura B
                    cliente_nombre=cliente_data.get('cliente_nombre', 'Consumidor Final'),
                    cliente_cuit=cliente_data.get('cliente_cuit', ''),
                    cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                    cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                    cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                    subtotal=venta.total,
                    impuesto_iva=Decimal('0.00'),
                    total=venta.total,
                    estado='ERROR',
                    sistema_facturacion=venta.tienda.tipo_facturacion,
                    error_mensaje=error,
                )
                
                return Response(
                    {
                        "error": error,
                        "factura_id": str(factura.id),
                        "estado": "ERROR"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Crear registro de factura exitosa
            factura = Factura.objects.create(
                venta=venta,
                tienda=venta.tienda,
                numero_comprobante=datos_factura.get('numero_comprobante'),
                punto_venta=datos_factura.get('punto_venta', venta.tienda.punto_venta),
                tipo_comprobante=datos_factura.get('tipo_comprobante', 'B'),
                cliente_nombre=cliente_data.get('cliente_nombre', 'Consumidor Final'),
                cliente_cuit=cliente_data.get('cliente_cuit', ''),
                cliente_domicilio=cliente_data.get('cliente_domicilio', ''),
                cliente_tipo_documento=cliente_data.get('cliente_tipo_documento', '99'),
                cliente_condicion_iva=cliente_data.get('cliente_condicion_iva', 'CF'),
                subtotal=datos_factura.get('subtotal', venta.total),
                impuesto_iva=datos_factura.get('impuesto_iva', Decimal('0.00')),
                total=datos_factura.get('total', venta.total),
                estado='EMITIDA',
                sistema_facturacion=venta.tienda.tipo_facturacion,
                cae=datos_factura.get('cae'),
                fecha_vencimiento_cae=datos_factura.get('fecha_vencimiento_cae'),
                numero_comprobante_afip=datos_factura.get('numero_comprobante_afip'),
                respuesta_bruta=datos_factura.get('respuesta_bruta'),
            )
            
            # Marcar venta como facturada y actualizar datos del cliente
            venta.facturada = True
            venta.cliente_nombre = cliente_data.get('cliente_nombre', '')
            venta.cliente_cuit = cliente_data.get('cliente_cuit', '')
            venta.cliente_domicilio = cliente_data.get('cliente_domicilio', '')
            venta.cliente_tipo_documento = cliente_data.get('cliente_tipo_documento', '')
            venta.save()
            
            # Serializar y retornar factura
            factura_serializer = FacturaSerializer(factura)
            
            return Response(
                {
                    "message": "Factura emitida exitosamente",
                    "factura": factura_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"❌ Excepción no capturada en emitir_factura: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                {"error": f"Error al emitir factura: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def ticket_cambio(self, request, pk=None):
        """
        Genera y retorna el PDF del ticket de cambio para una venta
        """
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        if not BARCODE_AVAILABLE:
            return Response(
                {"error": "python-barcode no está instalado. Instala con: pip install python-barcode"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        venta = get_object_or_404(Venta, pk=pk)
        
        # Verificar permisos
        user = request.user
        if not user.is_superuser and user.tienda != venta.tienda:
            return Response(
                {"error": "No tienes permiso para ver este ticket de cambio"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener nombre de la tienda
        nombre_tienda = venta.tienda.nombre if venta.tienda else 'N/A'
        
        # Crear buffer para el PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=(80*mm, 120*mm), topMargin=10*mm, bottomMargin=10*mm, leftMargin=5*mm, rightMargin=5*mm)
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=8,
            alignment=1  # Centrado
        )
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#000000'),
            spaceAfter=6,
            alignment=1  # Centrado
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.textColor = colors.HexColor('#000000')
        
        # Contenido del PDF
        story = []
        
        # Nombre de la tienda
        story.append(Paragraph(f"<b>{nombre_tienda}</b>", title_style))
        story.append(Spacer(1, 8))
        
        # Leyenda "Ticket para cambio"
        story.append(Paragraph("<b>TICKET PARA CAMBIO</b>", subtitle_style))
        story.append(Spacer(1, 12))
        
        # Fecha de compra
        fecha_str = venta.fecha_venta.strftime('%d/%m/%Y %H:%M')
        story.append(Paragraph(f"<b>Fecha de compra:</b> {fecha_str}", normal_style))
        story.append(Spacer(1, 12))
        
        # Generar código de barras
        try:
            # Crear código de barras Code128 con el ID de la venta
            venta_id_str = str(venta.id).replace('-', '')  # Remover guiones del UUID
            # Limitar a los primeros 40 caracteres (límite razonable para código de barras)
            venta_id_str = venta_id_str[:40]
            
            code128 = barcode.get_barcode_class('code128')
            barcode_instance = code128(venta_id_str, writer=ImageWriter())
            
            # Generar imagen del código de barras en memoria
            barcode_buffer = BytesIO()
            barcode_instance.write(barcode_buffer, options={
                'module_width': 0.3,
                'module_height': 15,
                'quiet_zone': 2,
                'font_size': 8,
                'text_distance': 3
            })
            barcode_buffer.seek(0)
            
            # Crear imagen de ReportLab desde el buffer
            barcode_image = Image(barcode_buffer, width=60*mm, height=15*mm)
            story.append(barcode_image)
            story.append(Spacer(1, 6))
            
            # ID de la venta debajo del código de barras
            story.append(Paragraph(f"<b>ID: {str(venta.id)}</b>", ParagraphStyle(
                'BarcodeText',
                parent=normal_style,
                fontSize=8,
                alignment=1  # Centrado
            )))
            
        except Exception as e:
            logger.error(f"Error al generar código de barras: {e}")
            # Si falla el código de barras, mostrar solo el ID
            story.append(Paragraph(f"<b>ID de Venta:</b> {str(venta.id)}", normal_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        
        # Crear respuesta HTTP con el PDF
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ticket_cambio_{venta.id}.pdf"'
        return response


class DetalleVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DetalleVenta.objects.all()
        elif user.tienda:
            return DetalleVenta.objects.filter(venta__tienda=user.tienda)
        return DetalleVenta.objects.none()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.all()
    serializer_class = MetodoPagoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Retorna todos los métodos de pago activos.
        Mercado Libre siempre se muestra para permitir ventas manuales con aranceles por producto.
        """
        return MetodoPago.objects.filter(activo=True).order_by('nombre')

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


# CAMBIO CRUCIAL: NUEVO VIEWSET para aranceles
class ArancelMetodoTiendaViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        """Permitir lectura a usuarios staff, pero solo superusuarios pueden crear/editar/eliminar"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ArancelMetodoTiendaCreateSerializer
        return ArancelMetodoTiendaSerializer

    def get_queryset(self):
        user = self.request.user
        # Uso select_related para optimizar la consulta de tienda y método de pago
        queryset = ArancelMetodoTienda.objects.all().select_related('tienda', 'metodo_pago')
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        # Superusuarios pueden ver todos los aranceles
        if user.is_superuser:
            if tienda_slug:
                result = queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
                logger.info(f"✅ Superuser - Aranceles para tienda '{tienda_slug}': {result.count()} aranceles")
                return result
            result = queryset.order_by('tienda__nombre', 'metodo_pago__nombre', 'nombre_plan')
            logger.info(f"✅ Superuser - Todos los aranceles: {result.count()} aranceles")
            return result
        
        # Usuarios staff solo pueden ver aranceles de su tienda
        elif user.is_staff and user.tienda:
            # Normalizar comparación (sin case sensitivity)
            tienda_nombre_usuario = user.tienda.nombre.strip() if user.tienda.nombre else None
            tienda_slug_normalizado = tienda_slug.strip() if tienda_slug else None
            
            logger.info(f"🔍 Staff user '{user.username}' - Verificando aranceles. Usuario.tienda='{tienda_nombre_usuario}', tienda_slug='{tienda_slug_normalizado}'")
            logger.info(f"🔍 Staff user '{user.username}' - user.tienda.id={user.tienda.id if user.tienda else 'None'}")
            
            # Si viene tienda_slug, verificar que coincida con la tienda del usuario (comparación flexible)
            if tienda_slug:
                # Comparar con y sin case sensitivity, y también comparar sin espacios
                if (tienda_nombre_usuario == tienda_slug_normalizado or 
                    tienda_nombre_usuario.lower() == tienda_slug_normalizado.lower()):
                    result = queryset.filter(tienda=user.tienda).order_by('metodo_pago__nombre', 'nombre_plan')
                    logger.info(f"✅ Staff user '{user.username}' - Aranceles para tienda '{tienda_nombre_usuario}': {result.count()} aranceles")
                    # Log detallado de los aranceles encontrados
                    if result.exists():
                        for arancel in result[:5]:  # Log primeros 5
                            logger.info(f"  📋 Arancel: {arancel.metodo_pago.nombre if arancel.metodo_pago else 'N/A'} - {arancel.nombre_plan}")
                    return result
                else:
                    logger.warning(f"⚠️ Staff user '{user.username}' - Tienda no coincide: usuario.tienda='{tienda_nombre_usuario}' vs tienda_slug='{tienda_slug_normalizado}'")
                    # Intentar buscar por ID también
                    try:
                        tienda_obj = Tienda.objects.get(nombre=tienda_slug_normalizado)
                        if tienda_obj.id == user.tienda.id:
                            logger.info(f"✅ Staff user '{user.username}' - Coincidencia encontrada por ID, retornando aranceles")
                            result = queryset.filter(tienda=user.tienda).order_by('metodo_pago__nombre', 'nombre_plan')
                            return result
                    except Tienda.DoesNotExist:
                        pass
                    return ArancelMetodoTienda.objects.none()
            # Si no viene tienda_slug, filtrar por la tienda del usuario
            result = queryset.filter(tienda=user.tienda).order_by('metodo_pago__nombre', 'nombre_plan')
            logger.info(f"✅ Staff user '{user.username}' - Aranceles para tienda '{tienda_nombre_usuario}' (sin slug): {result.count()} aranceles")
            return result
        
        # Si no es superuser ni staff, no puede ver aranceles
        logger.warning(f"⚠️ User '{user.username}' - No es superuser ni staff con tienda asignada. No puede ver aranceles.")
        return ArancelMetodoTienda.objects.none()

    def perform_create(self, serializer):
        """Al crear, usar la tienda del slug"""
        tienda_slug = self.request.data.get('tienda')
        if tienda_slug:
            try:
                tienda = Tienda.objects.get(nombre=tienda_slug)
                serializer.save(tienda=tienda)
            except Tienda.DoesNotExist:
                from rest_framework import serializers as drf_serializers
                raise drf_serializers.ValidationError({'tienda': 'Tienda no encontrada'})
        else:
            serializer.save()

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


class CompraViewSet(viewsets.ModelViewSet):
    serializer_class = CompraSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Compra.objects.all()
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        if user.is_superuser:
            if tienda_slug:
                queryset = queryset.filter(tienda__nombre=tienda_slug)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            return Compra.objects.none()

        # Filtro por rango de fechas
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        if date_from:
            queryset = queryset.filter(fecha_compra__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(fecha_compra__date__lte=date_to)

        # Búsqueda por concepto (proveedor)
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(proveedor__icontains=search)

        return queryset.order_by('-fecha_compra')

    def get_serializer_class(self):
        if self.action == 'create':
            return CompraCreateSerializer
        return CompraSerializer
    
    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


# VIEWSET: Aranceles Mercado Libre por Producto (arancel % + costo envío por producto)
# Reemplaza la configuración por categoría
if ArancelMercadoLibreProducto is not None and ArancelMercadoLibreProductoSerializer is not None:
    class ArancelMercadoLibreProductoViewSet(viewsets.ModelViewSet):
        permission_classes = [permissions.IsAuthenticated]
        
        def get_serializer_class(self):
            if self.action in ['create', 'update', 'partial_update']:
                return ArancelMercadoLibreProductoCreateSerializer
            return ArancelMercadoLibreProductoSerializer
        
        def get_queryset(self):
            user = self.request.user
            queryset = ArancelMercadoLibreProducto.objects.all().select_related('tienda', 'producto')
            
            if user.is_superuser:
                tienda_slug = self.request.query_params.get('tienda_slug', None)
                if tienda_slug:
                    queryset = queryset.filter(tienda__nombre=tienda_slug)
                return queryset.order_by('tienda__nombre', 'producto__nombre')
            
            elif user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
                return queryset.order_by('producto__nombre')
            
            return ArancelMercadoLibreProducto.objects.none()
        
        def perform_create(self, serializer):
            user = self.request.user
            if not user.is_superuser and user.tienda:
                serializer.save(tienda=user.tienda)
            else:
                serializer.save()
        
        def list(self, request, *args, **kwargs):
            close_old_connections()
            return super().list(request, *args, **kwargs)
else:
    ArancelMercadoLibreProductoViewSet = None

# VIEWSET: Aranceles Mercado Libre por Categoría (legacy - se mantiene por compatibilidad)
if ArancelMercadoLibre is not None and ArancelMercadoLibreSerializer is not None:
    class ArancelMercadoLibreViewSet(viewsets.ModelViewSet):
        permission_classes = [permissions.IsAuthenticated]
        
        def get_serializer_class(self):
            if self.action in ['create', 'update', 'partial_update']:
                return ArancelMercadoLibreCreateSerializer
            return ArancelMercadoLibreSerializer
        
        def get_queryset(self):
            if ArancelMercadoLibre is None:
                from rest_framework.exceptions import NotFound
                raise NotFound("ArancelMercadoLibre no está disponible.")
            
            user = self.request.user
            queryset = ArancelMercadoLibre.objects.all().select_related('tienda', 'categoria_ml')
            
            if user.is_superuser:
                tienda_slug = self.request.query_params.get('tienda_slug', None)
                if tienda_slug:
                    queryset = queryset.filter(tienda__nombre=tienda_slug)
                return queryset.order_by('tienda__nombre', 'categoria_ml__nombre')
            
            elif user.tienda:
                from .models import Producto
                categorias_usadas = Producto.objects.filter(
                    tienda=user.tienda,
                    ml_categoria_id__isnull=False
                ).exclude(ml_categoria_id='').values_list('ml_categoria_id', flat=True).distinct()
                queryset = queryset.filter(
                    tienda=user.tienda,
                    categoria_ml__id__in=categorias_usadas
                )
                return queryset.order_by('categoria_ml__nombre')
            
            return ArancelMercadoLibre.objects.none()
        
        def perform_create(self, serializer):
            user = self.request.user
            if not user.is_superuser and user.tienda:
                serializer.save(tienda=user.tienda)
            else:
                serializer.save()
        
        def list(self, request, *args, **kwargs):
            close_old_connections()
            return super().list(request, *args, **kwargs)
else:
    ArancelMercadoLibreViewSet = None
        

class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer

# --- ENDPOINT PARA NOTIFICACIONES PUSH (FCM) ---
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def registrar_token_fcm(request):
    """
    Endpoint para registrar un token FCM de un dispositivo.
    Se usa para recibir notificaciones push cuando se realizan ventas.
    """
    from .services.notificaciones_service import NotificacionesService
    
    token = request.data.get('token')
    device_info = request.data.get('device_info', None)
    
    if not token:
        return Response(
            {'error': 'El token FCM es requerido'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        fcm_token, created = NotificacionesService.registrar_token(
            user=request.user,
            token=token,
            device_info=device_info
        )
        
        return Response({
            'success': True,
            'message': 'Token registrado correctamente' if created else 'Token actualizado correctamente',
            'token_id': str(fcm_token.id)
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error al registrar token FCM: {str(e)}")
        return Response(
            {'error': f'Error al registrar token: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['DELETE', 'POST'])
@permission_classes([permissions.IsAuthenticated])
def eliminar_token_fcm(request):
    """
    Endpoint para eliminar/desactivar un token FCM.
    Útil cuando el usuario cierra sesión o desactiva notificaciones.
    """
    from .services.notificaciones_service import NotificacionesService
    
    token = request.data.get('token')
    
    if not token:
        return Response(
            {'error': 'El token FCM es requerido'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        success = NotificacionesService.eliminar_token(token)
        
        if success:
            return Response({
                'success': True,
                'message': 'Token eliminado correctamente'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Token no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        logger.error(f"Error al eliminar token FCM: {str(e)}")
        return Response(
            {'error': f'Error al eliminar token: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# --- NUEVA VISTA PARA MÉTRICAS DE INVENTARIO ---
class InventarioMetricsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Métrica de stock total (cantidad)
        total_stock = Producto.objects.filter(tienda=tienda_obj).aggregate(total_stock=Sum('stock'))['total_stock'] or 0

        # Métrica de monto total del stock (precio de venta)
        monto_total_stock_precio = Producto.objects.filter(tienda=tienda_obj).aggregate(
            total_monto_stock=Sum(F('stock') * Coalesce('precio', Value(0), output_field=DecimalField()))
        )['total_monto_stock'] or Decimal('0.00')
        
        # Métrica de monto total del stock (costo)
        monto_total_stock_costo = Producto.objects.filter(tienda=tienda_obj).aggregate(
            total_monto_stock_costo=Sum(F('stock') * Coalesce('costo', Value(0), output_field=DecimalField()))
        )['total_monto_stock_costo'] or Decimal('0.00')

        data = {
            'total_stock': total_stock,
            'total_monto_stock_precio': monto_total_stock_precio,
            'total_monto_stock_costo': monto_total_stock_costo,
        }

        return Response(data)

# --- VISTA PARA VERIFICAR CONFIGURACIÓN DE BASE DE DATOS ---
@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # Permitir acceso sin autenticación para diagnóstico
def verificar_database_config(request):
    """
    Endpoint para verificar qué base de datos está usando el sistema.
    Útil para diagnosticar si está usando la BD en la nube o la local.
    """
    from django.conf import settings
    from django.db import connection
    import os
    
    db_config = settings.DATABASES['default']
    environment = os.environ.get('DJANGO_ENVIRONMENT', 'development').lower()
    
    # Información de la base de datos (sin credenciales sensibles)
    db_info = {
        'environment': environment,
        'engine': db_config.get('ENGINE', 'N/A'),
        'database_name': db_config.get('NAME', 'N/A'),
        'host': db_config.get('HOST', 'N/A'),
        'port': db_config.get('PORT', 'N/A'),
        'user': db_config.get('USER', 'N/A'),
        'has_database_url': 'DATABASE_URL' in os.environ,
        'is_sqlite': 'sqlite3' in db_config.get('ENGINE', ''),
        'is_postgresql': 'postgresql' in db_config.get('ENGINE', ''),
    }
    
    # Intentar hacer una consulta simple para verificar la conexión
    try:
        with connection.cursor() as cursor:
            if db_info['is_postgresql']:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]
                db_info['database_version'] = version
                db_info['connection_status'] = '✅ Conectado a PostgreSQL'
                
                # Contar usuarios para verificar que está usando la BD correcta
                cursor.execute("SELECT COUNT(*) FROM inventario_user;")
                user_count = cursor.fetchone()[0]
                db_info['user_count'] = user_count
                
                # Obtener lista de usernames (solo los primeros 10)
                cursor.execute("SELECT username FROM inventario_user ORDER BY username LIMIT 10;")
                usernames = [row[0] for row in cursor.fetchall()]
                db_info['sample_usernames'] = usernames
                
            elif db_info['is_sqlite']:
                cursor.execute("SELECT sqlite_version();")
                version = cursor.fetchone()[0]
                db_info['database_version'] = version
                db_info['connection_status'] = '⚠️ Usando SQLite (local)'
                
                # Contar usuarios
                cursor.execute("SELECT COUNT(*) FROM inventario_user;")
                user_count = cursor.fetchone()[0]
                db_info['user_count'] = user_count
                
                # Obtener lista de usernames
                cursor.execute("SELECT username FROM inventario_user ORDER BY username LIMIT 10;")
                usernames = [row[0] for row in cursor.fetchall()]
                db_info['sample_usernames'] = usernames
            else:
                db_info['connection_status'] = '❓ Tipo de base de datos desconocido'
                
    except Exception as e:
        db_info['connection_status'] = f'❌ Error de conexión: {str(e)}'
        db_info['error'] = str(e)
    
    # Advertencia si está en producción pero usando SQLite
    if environment == 'production' and db_info['is_sqlite']:
        db_info['warning'] = '⚠️ ADVERTENCIA: Estás en PRODUCCIÓN pero usando SQLite local. Debes usar PostgreSQL en la nube.'
    
    return Response(db_info, status=status.HTTP_200_OK)

# --- VISTA PARA MÉTRICAS DE VENTAS (ACTUALIZADA) ---
class MetricasAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        year = request.query_params.get('year', None)
        month = request.query_params.get('month', None)
        day = request.query_params.get('day', None)
        date_from = request.query_params.get('date_from', None)
        date_to = request.query_params.get('date_to', None)
        seller_id = request.query_params.get('seller_id', None)
        payment_method = request.query_params.get('payment_method', None)

        if not tienda_slug:
            return Response({"error": "Parámetro 'tienda_slug' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except:
            return Response({"error": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        
        # Filtramos las ventas para excluir las anuladas, notas de crédito y ventas pendientes
        queryset_ventas = Venta.objects.filter(tienda=tienda_obj, anulada=False).exclude(
            metodo_pago__in=['Nota de Crédito', 'Pendiente']
        )
        queryset_compras = Compra.objects.filter(tienda=tienda_obj)

        use_date_range = date_from and date_to
        if use_date_range:
            try:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                if dt_from > dt_to:
                    return Response({"error": "'date_from' debe ser anterior o igual a 'date_to'."}, status=status.HTTP_400_BAD_REQUEST)
                queryset_ventas = queryset_ventas.filter(
                    fecha_venta__date__gte=dt_from,
                    fecha_venta__date__lte=dt_to
                )
                queryset_compras = queryset_compras.filter(
                    fecha_compra__date__gte=dt_from,
                    fecha_compra__date__lte=dt_to
                )
            except ValueError:
                return Response({"error": "Formato de fecha inválido. Use YYYY-MM-DD para date_from y date_to."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if year:
                queryset_ventas = queryset_ventas.filter(fecha_venta__year=year)
                queryset_compras = queryset_compras.filter(fecha_compra__year=year)
            if month:
                queryset_ventas = queryset_ventas.filter(fecha_venta__month=month)
                queryset_compras = queryset_compras.filter(fecha_compra__month=month)
            if day:
                queryset_ventas = queryset_ventas.filter(fecha_venta__day=day)
                queryset_compras = queryset_compras.filter(fecha_compra__day=day)
        if seller_id:
            queryset_ventas = queryset_ventas.filter(usuario__id=seller_id)
        if payment_method:
            queryset_ventas = queryset_ventas.filter(metodo_pago=payment_method)

        # Calcular el total de ventas, pero para ventas que vienen de cambios/devoluciones,
        # usar solo la diferencia en lugar del total completo
        # Las ventas relacionadas con cambios/devoluciones tienen diferencia_pendiente=True
        # y necesitamos usar el monto_diferencia del cambio/devolución relacionado
        
        # Optimización: obtener todas las ventas con relaciones optimizadas
        # Usar select_related para ForeignKeys y prefetch_related para relaciones reversas
        # Nota: metodo_pago es CharField, no ForeignKey, por lo que no se puede usar en select_related
        if CambioDevolucion is not None:
            ventas_list = list(queryset_ventas.select_related(
                'tienda', 'usuario', 'arancel_aplicado'
            ).prefetch_related(
                'cambio_devolucion_diferencia',
                'nota_credito_origen'
            ))
        else:
            ventas_list = list(queryset_ventas.select_related(
                'tienda', 'usuario', 'arancel_aplicado'
            ))
        
        # Optimización: crear diccionarios para acceso rápido a relaciones
        cambio_diferencia_map = {}
        nota_credito_map = {}
        if CambioDevolucion is not None:
            # Pre-cargar todas las relaciones en una sola consulta
            for venta in ventas_list:
                # Acceder a las relaciones prefetch para cachearlas
                cambio_dif = list(venta.cambio_devolucion_diferencia.all())
                if cambio_dif:
                    cambio_diferencia_map[venta.id] = cambio_dif[0]
                
                nota_cred = list(venta.nota_credito_origen.all())
                if nota_cred:
                    nota_credito_map[venta.id] = nota_cred[0]
        
        total_ventas_periodo = Decimal('0.00')
        
        # Iterar una sola vez procesando todo
        for venta in ventas_list:
            # Excluir notas de crédito primero (más rápido)
            if venta.id in nota_credito_map:
                continue
            
            # Si la venta viene de un cambio/devolución (tiene diferencia pendiente),
            # usar el monto_diferencia del cambio/devolución en lugar del total de la venta
            if venta.id in cambio_diferencia_map:
                cambio_diferencia = cambio_diferencia_map[venta.id]
                if cambio_diferencia.monto_diferencia > 0:
                    # Solo contar la diferencia pagada, no el total completo de la venta
                    total_ventas_periodo += cambio_diferencia.monto_diferencia
                    continue
            
            # Para ventas normales (no de diferencia ni notas de crédito), usar el total
            total_ventas_periodo += venta.total
        
        # Filtramos los detalles de venta para excluir los anulados individualmente
        # Pero para ventas que vienen de cambios/devoluciones, solo contamos los productos nuevos
        # Optimización: usar select_related para evitar consultas N+1 con producto
        detalles_activos = DetalleVenta.objects.filter(
            venta__in=queryset_ventas, 
            anulado_individualmente=False
        ).select_related('producto', 'venta')
        total_productos_vendidos_periodo = detalles_activos.aggregate(total_productos_vendidos=Sum('cantidad'))['total_productos_vendidos'] or 0
        
        # Calcular costo vendido: para ventas normales usar todos los detalles,
        # para ventas de diferencia solo contar productos nuevos (ya están en los detalles de la venta)
        total_costo_vendido = detalles_activos.aggregate(total_costo_vendido=Sum(F('cantidad') * Coalesce('costo_unitario', Value(0), output_field=DecimalField())))['total_costo_vendido'] or Decimal('0.00')
        
        # Ajustar costo vendido si hay ventas que vienen de cambios/devoluciones
        # (en este caso, los productos ya están correctamente en los detalles, así que no hay que ajustar)

        total_compras_periodo = queryset_compras.aggregate(total_egresos=Sum('total'))['total_egresos'] or Decimal('0.00')

        # CAMBIO 10: NUEVO CÁLCULO: Arancel Total de Ventas con Comisión
        # Calcular arancel considerando solo la diferencia para ventas de cambio/devolución
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        total_arancel_ventas = Decimal('0.00')
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            if venta.id in cambio_diferencia_map:
                cambio_diferencia = cambio_diferencia_map[venta.id]
                if cambio_diferencia.monto_diferencia > 0:
                    # Para ventas de diferencia, calcular arancel solo sobre la diferencia
                    # (el arancel ya debería estar calculado sobre el total de la venta, pero lo ajustamos proporcionalmente)
                    if venta.arancel_total and venta.total > 0:
                        factor_proporcion = cambio_diferencia.monto_diferencia / venta.total
                        total_arancel_ventas += venta.arancel_total * factor_proporcion
                    else:
                        total_arancel_ventas += venta.arancel_total or Decimal('0.00')
                else:
                    total_arancel_ventas += venta.arancel_total or Decimal('0.00')
            else:
                total_arancel_ventas += venta.arancel_total or Decimal('0.00')

        # Costo de envío ML: descontar de métricas (webhook + ventas manuales con pago ML)
        total_costo_envio_ml = sum(
            (v.costo_envio_ml or Decimal('0.00'))
            for v in ventas_list
            if v.id not in nota_credito_map and (v.costo_envio_ml or Decimal('0.00')) > Decimal('0.00')
        )

        # CAMBIO 11: La rentabilidad resta costo productos, egresos, aranceles Y costo envío ML
        rentabilidad_bruta = total_ventas_periodo - total_costo_vendido - total_compras_periodo - total_arancel_ventas - total_costo_envio_ml
        margen_rentabilidad = (rentabilidad_bruta / total_ventas_periodo * 100) if total_ventas_periodo > 0 else 0

        # Filtrar detalles que tienen producto (excluir notas de crédito y detalles sin producto)
        productos_mas_vendidos = detalles_activos.filter(producto__isnull=False).values(
            'producto__nombre', 'producto__talle'
        ).annotate(
            cantidad_total=Sum('cantidad')
        ).order_by('-cantidad_total')[:10]
        
        # Para ventas por usuario, también aplicar la lógica de diferencia
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        ventas_por_usuario_dict = {}
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            username = venta.usuario.username if venta.usuario else 'Sin usuario'
            
            # Usar el mapa ya creado para acceso rápido
            if venta.id in cambio_diferencia_map:
                cambio_diferencia = cambio_diferencia_map[venta.id]
                monto_venta = cambio_diferencia.monto_diferencia if cambio_diferencia.monto_diferencia > 0 else venta.total
            else:
                monto_venta = venta.total
            
            if username not in ventas_por_usuario_dict:
                ventas_por_usuario_dict[username] = {'total_vendido': Decimal('0.00'), 'cantidad_ventas': 0}
            ventas_por_usuario_dict[username]['total_vendido'] += monto_venta
            ventas_por_usuario_dict[username]['cantidad_ventas'] += 1
        
        ventas_por_usuario = [
            {'usuario__username': username, 'total_vendido': float(data['total_vendido']), 'cantidad_ventas': data['cantidad_ventas']}
            for username, data in ventas_por_usuario_dict.items()
        ]
        ventas_por_usuario.sort(key=lambda x: x['total_vendido'], reverse=True)
        
        # Para ventas por método de pago, también aplicar la lógica de diferencia
        # Optimización: usar el mapa ya creado en lugar de hacer .first() en cada iteración
        ventas_por_metodo_pago_dict = {}
        for venta in ventas_list:
            # Excluir notas de crédito
            if venta.id in nota_credito_map:
                continue
                
            metodo_pago = venta.metodo_pago or 'Sin método'
            
            # Usar el mapa ya creado para acceso rápido
            if venta.id in cambio_diferencia_map:
                cambio_diferencia = cambio_diferencia_map[venta.id]
                monto_venta = cambio_diferencia.monto_diferencia if cambio_diferencia.monto_diferencia > 0 else venta.total
            else:
                monto_venta = venta.total
            
            if metodo_pago not in ventas_por_metodo_pago_dict:
                ventas_por_metodo_pago_dict[metodo_pago] = Decimal('0.00')
            ventas_por_metodo_pago_dict[metodo_pago] += monto_venta
        
        ventas_por_metodo_pago = [
            {'metodo_pago': metodo, 'total_vendido': float(monto)}
            for metodo, monto in ventas_por_metodo_pago_dict.items()
        ]
        ventas_por_metodo_pago.sort(key=lambda x: x['total_vendido'], reverse=True)

        egresos_por_mes = queryset_compras.annotate(
            year=ExtractYear('fecha_compra'),
            mes=ExtractMonth('fecha_compra')
        ).values('year', 'mes').annotate(
            total_egresos=Sum('total')
        ).order_by('year', 'mes')

        data = {
            'total_ventas_periodo': total_ventas_periodo,
            'total_productos_vendidos_periodo': total_productos_vendidos_periodo,
            'total_costo_vendido_periodo': total_costo_vendido,
            'total_compras_periodo': total_compras_periodo,
            'total_arancel_ventas': total_arancel_ventas,
            'total_costo_envio_ml': total_costo_envio_ml,
            'rentabilidad_bruta_periodo': rentabilidad_bruta,
            'margen_rentabilidad_periodo': margen_rentabilidad,
            'productos_mas_vendidos': list(productos_mas_vendidos),
            'ventas_por_usuario': list(ventas_por_usuario),
            'ventas_por_metodo_pago': list(ventas_por_metodo_pago),
            'egresos_por_mes': list(egresos_por_mes),
        }

        return Response(data)


class FacturaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para consultar facturas emitidas"""
    serializer_class = FacturaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['numero_comprobante', 'cliente_nombre', 'cliente_cuit', 'cae']
    ordering_fields = ['fecha_emision', 'numero_comprobante', 'total']
    ordering = ['-fecha_emision']
    def get_queryset(self):
        user = self.request.user
        
        queryset = Factura.objects.select_related('venta', 'tienda').all()
        
        # Filtrar por tienda si no es superusuario
        if user.is_superuser:
            tienda_id = self.request.query_params.get('tienda', None)
            if tienda_id:
                queryset = queryset.filter(tienda_id=tienda_id)
        elif user.tienda:
            queryset = queryset.filter(tienda=user.tienda)
        else:
            queryset = Factura.objects.none()
        
        # Filtros opcionales
        estado = self.request.query_params.get('estado', None)
        if estado:
            queryset = queryset.filter(estado=estado)
        
        tipo_comprobante = self.request.query_params.get('tipo_comprobante', None)
        if tipo_comprobante:
            queryset = queryset.filter(tipo_comprobante=tipo_comprobante)
        
        # Filtrar por venta (UUID)
        venta_id = self.request.query_params.get('venta', None)
        if venta_id:
            queryset = queryset.filter(venta_id=venta_id)
        
        return queryset
    
    @action(detail=True, methods=['get'], url_path='pdf', url_name='pdf')
    def generar_pdf(self, request, pk=None):
        """
        Genera y retorna el PDF de la factura
        """
        if not REPORTLAB_AVAILABLE:
            return Response(
                {"error": "reportlab no está instalado. Instala con: pip install reportlab"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        factura = self.get_object()
        
        # Verificar permisos
        user = request.user
        if not user.is_superuser and user.tienda != factura.tienda:
            return Response(
                {"error": "No tienes permiso para ver esta factura"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Asegurar que la relación tienda esté cargada correctamente
        # Recargar desde la base de datos si es necesario
        try:
            factura.refresh_from_db()
            # Forzar la carga de la relación tienda
            tienda_obj = factura.tienda
            if tienda_obj:
                tienda_obj.refresh_from_db()
        except Exception as e:
            logger.warning(f"⚠️ Error al recargar factura o tienda: {e}")
        
        # Obtener detalles de la venta
        venta = factura.venta
        detalles = venta.detalles.all()
        
        # Obtener el nombre de la tienda con fallback
        nombre_tienda = 'N/A'
        try:
            # Intentar obtener desde la relación
            if factura.tienda_id:
                # Recargar tienda desde DB
                from inventario.models import Tienda
                tienda_obj = Tienda.objects.get(id=factura.tienda_id)
                nombre_tienda = tienda_obj.nombre or 'N/A'
                logger.info(f"✅ Nombre de tienda obtenido desde DB: {nombre_tienda}")
            elif factura.tienda:
                nombre_tienda = factura.tienda.nombre or 'N/A'
                logger.info(f"✅ Nombre de tienda obtenido desde relación: {nombre_tienda}")
            else:
                logger.warning(f"⚠️ La factura {factura.id} no tiene tienda asignada")
        except Exception as e:
            logger.warning(f"⚠️ Error al obtener nombre de tienda: {e}")
            import traceback
            logger.warning(traceback.format_exc())
        
        logger.info(f"📄 Generando PDF para factura {factura.id}, tienda: '{nombre_tienda}'")
        
        # Crear buffer para el PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#000000'),
            spaceAfter=12,
            alignment=1  # Centrado
        )
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        normal_style.textColor = colors.HexColor('#000000')
        
        # Contenido del PDF
        story = []
        
        # Título - Usar nombre de la tienda (ya obtenido arriba)
        # Manejar tanto tipo_comprobante como letra (A, B, C) como número (1, 6, 11)
        tipo_comprobante_para_texto = factura.tipo_comprobante
        if isinstance(tipo_comprobante_para_texto, (int, str)) and str(tipo_comprobante_para_texto) in ['1', '6', '11']:
            # Convertir número a letra
            tipo_map = {'1': 'A', '6': 'B', '11': 'C'}
            tipo_comprobante_para_texto = tipo_map.get(str(tipo_comprobante_para_texto), 'B')
        
        tipo_factura_text = dict(Factura.TIPO_FACTURA_CHOICES).get(tipo_comprobante_para_texto, tipo_comprobante_para_texto)
        story.append(Paragraph(f"<b>{nombre_tienda}</b>", title_style))
        story.append(Paragraph(f"FACTURA {tipo_factura_text}", ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#000000'),
            spaceAfter=8,
            alignment=1  # Centrado
        )))
        story.append(Spacer(1, 12))
        
        # Datos de la tienda
        if factura.tienda.cuit:
            story.append(Paragraph(f"<b>CUIT:</b> {factura.tienda.cuit}", normal_style))
        if factura.tienda.direccion:
            story.append(Paragraph(f"<b>Domicilio:</b> {factura.tienda.direccion}", normal_style))
        story.append(Spacer(1, 12))
        
        # Datos de la factura (mover punto de venta y número más abajo, no justo después del nombre)
        # Primero mostrar fecha
        story.append(Paragraph(f"<b>Fecha de Emisión:</b> {factura.fecha_emision.strftime('%d/%m/%Y %H:%M')}", normal_style))
        # Generar código numérico de 13 dígitos desde el UUID de la venta (mismo que lee el código de barras)
        venta_id_sin_guiones = str(venta.id).replace('-', '')
        hash_num = 0
        for char in venta_id_sin_guiones:
            hash_num = (hash_num * 31 + ord(char)) % 1000000000
        hash_9_digitos = str(abs(hash_num)).zfill(9)[:9]
        codigo_base = '779' + hash_9_digitos
        # Calcular dígito de control para EAN13
        suma = sum(int(codigo_base[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
        checksum = (10 - (suma % 10)) % 10
        codigo_numerico = codigo_base + str(checksum)
        # Mostrar código numérico de 13 dígitos debajo de la fecha (mismo que lee el código de barras)
        story.append(Paragraph(f"<b>ID de Venta:</b> {codigo_numerico}", normal_style))
        # Mostrar punto de venta y número juntos en una línea más abajo
        story.append(Paragraph(f"<b>Comprobante:</b> {factura.punto_venta:04d}-{factura.numero_comprobante:08d}", normal_style))
        if factura.cae:
            story.append(Paragraph(f"<b>CAE:</b> {factura.cae}", normal_style))
        if factura.fecha_vencimiento_cae:
            story.append(Paragraph(f"<b>CAE Vto:</b> {factura.fecha_vencimiento_cae.strftime('%d/%m/%Y')}", normal_style))
        story.append(Spacer(1, 12))
        
        # Datos del cliente
        story.append(Paragraph("<b>DATOS DEL CLIENTE</b>", normal_style))
        story.append(Paragraph(f"<b>Nombre:</b> {factura.cliente_nombre}", normal_style))
        if factura.cliente_cuit:
            story.append(Paragraph(f"<b>CUIT/DNI:</b> {factura.cliente_cuit}", normal_style))
        if factura.cliente_domicilio:
            story.append(Paragraph(f"<b>Domicilio:</b> {factura.cliente_domicilio}", normal_style))
        condicion_iva_text = dict(Factura.CONDICION_IVA_CHOICES).get(factura.cliente_condicion_iva, factura.cliente_condicion_iva)
        story.append(Paragraph(f"<b>Condición IVA:</b> {condicion_iva_text}", normal_style))
        story.append(Spacer(1, 12))
        
        # IMPORTANTE: Los precios de los productos ya tienen IVA incluido (21%)
        # Necesitamos calcular el subtotal SIN IVA
        # Si precio_con_iva = precio_sin_iva * 1.21, entonces precio_sin_iva = precio_con_iva / 1.21
        
        # Tabla de productos
        data = [['Cant.', 'Descripción', 'Precio Unit.', 'Subtotal']]
        subtotal_sin_iva = Decimal('0.00')
        total_iva_calculado = Decimal('0.00')
        
        for detalle in detalles:
            if not detalle.anulado_individualmente:
                producto_nombre = detalle.producto.nombre if detalle.producto else 'Producto eliminado'
                # El precio_unitario ya tiene IVA incluido
                precio_con_iva = Decimal(str(detalle.precio_unitario))
                # Calcular precio sin IVA: precio_con_iva / 1.21
                precio_sin_iva = precio_con_iva / Decimal('1.21')
                # Calcular subtotal sin IVA
                subtotal_item_sin_iva = precio_sin_iva * Decimal(str(detalle.cantidad))
                # Calcular IVA del item
                iva_item = subtotal_item_sin_iva * Decimal('0.21')
                
                subtotal_sin_iva += subtotal_item_sin_iva
                total_iva_calculado += iva_item
                
                # Mostrar precio con IVA (el precio original del producto)
                data.append([
                    str(detalle.cantidad),
                    producto_nombre,
                    f"${precio_con_iva:.2f}",
                    f"${detalle.subtotal:.2f}"
                ])
        
        # IMPORTANTE: El total de la venta YA tiene descuentos/recargos aplicados
        # No debemos recalcular descuentos/recargos aquí, solo mostrar los valores correctos
        # El total de la venta ya incluye IVA y descuentos/recargos aplicados sobre el total con IVA
        
        # Calcular el subtotal y IVA a partir del total final (que ya tiene descuentos aplicados)
        total_final = Decimal(str(venta.total))
        subtotal_final_sin_iva = (total_final / Decimal('1.21')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        iva_final = (total_final - subtotal_final_sin_iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Calcular el descuento/recargo que se aplicó (para mostrarlo en el PDF)
        # El descuento/recargo se aplicó sobre el total CON IVA
        subtotal_inicial_con_iva = sum(
            Decimal(str(d.precio_unitario)) * Decimal(str(d.cantidad))
            for d in detalles if not d.anulado_individualmente
        )
        
        descuento_monto_calc = Decimal('0.00')
        recargo_monto_calc = Decimal('0.00')
        
        # Calcular descuento aplicado (sobre el total con IVA)
        if venta.descuento_porcentaje and venta.descuento_porcentaje > 0:
            descuento_porc = venta.descuento_porcentaje / Decimal('100')
            descuento_monto_calc = subtotal_inicial_con_iva * descuento_porc
        elif venta.descuento_monto and venta.descuento_monto > 0:
            descuento_monto_calc = venta.descuento_monto
        
        # Calcular recargo aplicado (sobre el total con IVA después del descuento)
        if venta.recargo_porcentaje and venta.recargo_porcentaje > 0:
            recargo_base = subtotal_inicial_con_iva - descuento_monto_calc
            recargo_porc = venta.recargo_porcentaje / Decimal('100')
            recargo_monto_calc = recargo_base * recargo_porc
        elif venta.recargo_monto and venta.recargo_monto > 0:
            recargo_monto_calc = venta.recargo_monto
        
        # Agregar línea separadora antes de totales
        data.append(['', '', '', ''])  # Línea vacía
        
        # Subtotal inicial con IVA (antes de descuentos/recargos)
        subtotal_inicial_con_iva = sum(
            Decimal(str(d.precio_unitario)) * Decimal(str(d.cantidad))
            for d in detalles if not d.anulado_individualmente
        )
        data.append(['', '', '<b>Subtotal:</b>', f"${subtotal_inicial_con_iva:.2f}"])
        
        # Descuentos (mostrar sobre el total con IVA)
        if descuento_monto_calc > 0:
            descuento_label = f'<b>Descuento'
            if venta.descuento_porcentaje and venta.descuento_porcentaje > 0:
                descuento_label += f' ({venta.descuento_porcentaje}%)'
            descuento_label += ':</b>'
            data.append(['', '', descuento_label, f"-${descuento_monto_calc:.2f}"])
        
        # Recargos (mostrar sobre el total con IVA)
        if recargo_monto_calc > 0:
            recargo_label = '<b>Recargo'
            if venta.recargo_porcentaje and venta.recargo_porcentaje > 0:
                recargo_label += f' ({venta.recargo_porcentaje}%)'
            recargo_label += ':</b>'
            data.append(['', '', recargo_label, f"+${recargo_monto_calc:.2f}"])
        
        # Si es una venta de diferencia de cambio/devolución, mostrar el monto devuelto
        monto_devuelto_mostrar = Decimal('0.00')
        if CambioDevolucion is not None:
            try:
                cambio_diferencia = venta.cambio_devolucion_diferencia.first()
                if cambio_diferencia:
                    # Mostrar el monto devuelto (productos devueltos)
                    monto_devuelto_mostrar = cambio_diferencia.monto_devolucion
                    if monto_devuelto_mostrar > 0:
                        data.append(['', '', '<b>Monto devuelto (cambio/devolución):</b>', f"-${monto_devuelto_mostrar:.2f}"])
                        # Ajustar el subtotal y total para reflejar el monto devuelto
                        subtotal_final_sin_iva = subtotal_final_sin_iva - (monto_devuelto_mostrar / Decimal('1.21'))
                        total_final = total_final - monto_devuelto_mostrar
                        iva_final = subtotal_final_sin_iva * Decimal('0.21')
            except Exception as e:
                logger.warning(f"⚠️ Error al obtener cambio_devolucion para mostrar monto devuelto: {e}")
        
        # Subtotal sin IVA (después de descuentos/recargos y monto devuelto)
        data.append(['', '', '<b>Subtotal (sin IVA):</b>', f"${subtotal_final_sin_iva:.2f}"])
        
        # IVA
        if iva_final > 0:
            data.append(['', '', '<b>IVA 21%:</b>', f"${iva_final:.2f}"])
        
        # Total
        data.append(['', '', '<b>TOTAL:</b>', f"<b>${total_final:.2f}</b>"])
        
        table = Table(data, colWidths=[20*mm, 100*mm, 30*mm, 30*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -4), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (2, -3), (-1, -1), 'RIGHT'),
            ('FONTNAME', (2, -3), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, -3), (-1, -1), 10),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Pie de página
        story.append(Paragraph("<i>Gracias por su compra</i>", normal_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        
        # Crear respuesta HTTP con el PDF
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="factura_{factura.punto_venta:04d}-{factura.numero_comprobante:08d}.pdf"'
        
        return response

# Siempre definir CambioDevolucionViewSet, pero hacer que verifique los modelos dinámicamente
# Intentar obtener los modelos dinámicamente - puede que Django no los haya cargado todavía en este punto
try:
    _CambioDevolucion, _DetalleCambioDevolucion = _get_cambio_devolucion_models()
    if _CambioDevolucion is not None and _DetalleCambioDevolucion is not None:
        CambioDevolucion = _CambioDevolucion
        DetalleCambioDevolucion = _DetalleCambioDevolucion
except Exception as e:
    logger.warning(f"⚠️ Error al obtener modelos CambioDevolucion en tiempo de definición: {e}")
    CambioDevolucion = None
    DetalleCambioDevolucion = None

# Siempre definir el ViewSet real, verificará los modelos dinámicamente cuando se necesiten
# Crear un serializer temporal para evitar AssertionError de DRF
from rest_framework import serializers as drf_serializers
class _TempSerializer(drf_serializers.Serializer):
    pass

class CambioDevolucionViewSet(viewsets.ModelViewSet):
        """ViewSet para gestionar cambios y devoluciones"""
        permission_classes = [permissions.IsAuthenticated]
        # Usar un serializer temporal, get_serializer_class() lo reemplazará con el correcto
        serializer_class = _TempSerializer
        
        def get_serializer_class(self):
            # Obtener los modelos dinámicamente si aún no están disponibles
            global CambioDevolucion, DetalleCambioDevolucion
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                try:
                    CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                except Exception as e:
                    logger.error(f"Error obteniendo modelos en get_serializer_class: {e}")
                    raise ImportError("CambioDevolucion models not available. Please restart the server after running migrations.")
            
            # Intentar obtener los serializers reales, reimportando si es necesario
            from rest_framework import serializers as drf_serializers
            
            # Obtener referencias locales a los serializers
            serializer = CambioDevolucionSerializer
            create_serializer = CambioDevolucionCreateSerializer
            
            # Si los serializers son dummy, intentar reimportar
            try:
                if (serializer is not None and 
                    not issubclass(serializer, drf_serializers.ModelSerializer)):
                    logger.warning("Serializers son dummy, intentando reimportar...")
                    import importlib
                    import inventario.serializers as serializers_module
                    importlib.reload(serializers_module)
                    from inventario.serializers import CambioDevolucionSerializer as NewSerializer, CambioDevolucionCreateSerializer as NewCreateSerializer
                    serializer = NewSerializer
                    create_serializer = NewCreateSerializer
            except Exception as e:
                logger.error(f"Error al reimportar serializers: {e}")
            
            # Verificar que los serializers son válidos
            try:
                if (serializer is not None and
                    create_serializer is not None and
                    issubclass(serializer, drf_serializers.ModelSerializer) and
                    issubclass(create_serializer, drf_serializers.ModelSerializer) and
                    hasattr(serializer, 'Meta') and
                    hasattr(serializer.Meta, 'model') and
                    serializer.Meta.model == CambioDevolucion):
                    
                    if self.action == 'create':
                        return create_serializer
                    return serializer
            except (TypeError, AttributeError) as e:
                logger.error(f"Error verificando serializers: {e}")
            
            # Si llegamos aquí, los serializers no están disponibles
            raise ImportError("CambioDevolucion serializers not available. Please restart the server after running migrations.")
        
        def get_queryset(self):
            # Obtener los modelos dinámicamente si aún no están disponibles
            global CambioDevolucion, DetalleCambioDevolucion
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                try:
                    CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                except Exception as e:
                    logger.error(f"Error obteniendo modelos en get_queryset: {e}", exc_info=True)
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            if CambioDevolucion is None or DetalleCambioDevolucion is None:
                from django.core.exceptions import ImproperlyConfigured
                raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
            
            # Continuar con la lógica normal
            user = self.request.user
            queryset = CambioDevolucion.objects.all().select_related(
                'venta_original', 'tienda', 'usuario', 'factura_nota_credito'
            ).prefetch_related('detalles').order_by('-fecha_creacion')
            
            tienda_slug = self.request.query_params.get('tienda_slug', None)
            
            if not user.is_superuser:
                if user.tienda:
                    queryset = queryset.filter(tienda=user.tienda)
                else:
                    return CambioDevolucion.objects.none()
            elif tienda_slug:
                queryset = queryset.filter(tienda__nombre=tienda_slug)
            
            # Filtrar por venta original
            venta_id = self.request.query_params.get('venta_original', None)
            if venta_id:
                queryset = queryset.filter(venta_original_id=venta_id)
            
            return queryset
        
        def create(self, request, *args, **kwargs):
                """Sobrescribir create para devolver el objeto con el serializer completo"""
                # Asegurarse de que los modelos estén disponibles
                global CambioDevolucion, DetalleCambioDevolucion
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    try:
                        CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                    except Exception as e:
                        logger.error(f"❌ Error obteniendo modelos en create: {e}", exc_info=True)
                        from django.core.exceptions import ImproperlyConfigured
                        raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                
                # Llamar a perform_create que retorna el objeto creado
                cambio_devolucion = self.perform_create(serializer)
                
                # Refrescar para asegurar que todas las relaciones estén cargadas
                cambio_devolucion.refresh_from_db()
                
                # Usar el serializer completo para la respuesta
                response_serializer = CambioDevolucionSerializer(cambio_devolucion)
                headers = self.get_success_headers(response_serializer.data)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        
        def perform_create(self, serializer):
            """Procesa el cambio/devolución: actualiza stock, genera nota de crédito si aplica"""
            validated_data = serializer.validated_data
            venta_original = validated_data['venta_original']
            detalles_data = validated_data['detalles']
            tipo = validated_data.get('tipo', 'CAMBIO')
            motivo = validated_data.get('motivo', '')
            
            # Verificar permisos
            user = self.request.user
            if not user.is_superuser and user.tienda != venta_original.tienda:
                raise serializers.ValidationError({"error": "No tienes permiso para procesar cambios/devoluciones de esta tienda."})
            
            # Calcular montos
            monto_devolucion = Decimal('0.00')
            monto_nuevo = Decimal('0.00')
            
            # Crear el cambio/devolución
            cambio_devolucion = CambioDevolucion.objects.create(
                    venta_original=venta_original,
                    tienda=venta_original.tienda,
                    usuario=user,
                    tipo=tipo,
                    motivo=motivo,
                    estado='PROCESADO'
                )
            
            # Procesar cada detalle
            for detalle_data in detalles_data:
                accion = detalle_data['accion']
                cantidad = detalle_data['cantidad']
                detalle_venta_original_id = detalle_data.get('detalle_venta_original_id')
                producto_nuevo_id = detalle_data.get('producto_nuevo_id')
                precio_unitario_nuevo = detalle_data.get('precio_unitario_nuevo')
                
                detalle_venta_original = None
                producto_nuevo = None
                
                # Obtener detalle de venta original si aplica
                if detalle_venta_original_id:
                    detalle_venta_original = DetalleVenta.objects.get(id=detalle_venta_original_id)
                
                # Obtener producto nuevo si aplica
                if producto_nuevo_id:
                    producto_nuevo = Producto.objects.get(id=producto_nuevo_id)
                
                # Calcular precios y subtotales
                precio_unitario_devuelto = None
                subtotal_devuelto = Decimal('0.00')
                subtotal_nuevo = Decimal('0.00')
                
                if detalle_venta_original:
                    # Calcular precio ajustado considerando descuentos/recargos de la venta original
                    precio_unitario_original = detalle_venta_original.precio_unitario
                    
                    # Calcular factor de ajuste si hay descuento/recargo porcentual
                    adjustment_factor = Decimal('1.0')
                    venta_original_obj = venta_original
                    
                    if venta_original_obj.descuento_porcentaje and venta_original_obj.descuento_porcentaje > 0:
                        adjustment_factor = Decimal('1.0') - (venta_original_obj.descuento_porcentaje / Decimal('100'))
                    elif venta_original_obj.recargo_porcentaje and venta_original_obj.recargo_porcentaje > 0:
                        adjustment_factor = Decimal('1.0') + (venta_original_obj.recargo_porcentaje / Decimal('100'))
                    
                    # Si el ajuste es por monto, calcular proporcionalmente
                    is_amount_adjustment = (venta_original_obj.descuento_monto and venta_original_obj.descuento_monto > 0) or \
                                           (venta_original_obj.recargo_monto and venta_original_obj.recargo_monto > 0)
                    
                    if is_amount_adjustment:
                        # Calcular el subtotal original de la venta (suma de todos los detalles no anulados)
                        subtotal_original_venta = sum(
                            det.precio_unitario * det.cantidad 
                            for det in venta_original_obj.detalles.all() 
                            if not det.anulado_individualmente
                        )
                        
                        # Calcular el total ajustado
                        total_ajustado = subtotal_original_venta
                        if venta_original_obj.descuento_monto and venta_original_obj.descuento_monto > 0:
                            total_ajustado = subtotal_original_venta - venta_original_obj.descuento_monto
                        elif venta_original_obj.recargo_monto and venta_original_obj.recargo_monto > 0:
                            total_ajustado = subtotal_original_venta + venta_original_obj.recargo_monto
                        
                        # Calcular el factor de proporción
                        if subtotal_original_venta > 0:
                            factor_proporcion = total_ajustado / subtotal_original_venta
                            precio_unitario_devuelto = precio_unitario_original * factor_proporcion
                        else:
                            precio_unitario_devuelto = precio_unitario_original
                    else:
                        # Si es porcentual, aplicar el factor directamente
                        precio_unitario_devuelto = precio_unitario_original * adjustment_factor
                    
                    subtotal_devuelto = precio_unitario_devuelto * cantidad
                    monto_devolucion += subtotal_devuelto
                
                if producto_nuevo and precio_unitario_nuevo:
                    subtotal_nuevo = precio_unitario_nuevo * cantidad
                    monto_nuevo += subtotal_nuevo
                
                # Crear detalle del cambio/devolución
                DetalleCambioDevolucion.objects.create(
                cambio_devolucion=cambio_devolucion,
                detalle_venta_original=detalle_venta_original,
                producto_nuevo=producto_nuevo,
                accion=accion,
                cantidad=cantidad,
                precio_unitario_devuelto=precio_unitario_devuelto,
                precio_unitario_nuevo=precio_unitario_nuevo,
                subtotal_devuelto=subtotal_devuelto,
                subtotal_nuevo=subtotal_nuevo
                )
                
                # Manejar stock
                if accion == 'DEVOLVER':
                    # Devolver stock del producto original
                    if detalle_venta_original and detalle_venta_original.producto:
                        producto = detalle_venta_original.producto
                        producto.stock += cantidad
                        producto.save()
                        
                        # Anular el detalle de venta si se devuelve todo
                        if cantidad >= detalle_venta_original.cantidad:
                            detalle_venta_original.anulado_individualmente = True
                            detalle_venta_original.save()
                
                elif accion == 'CAMBIAR':
                    # Devolver stock del producto original
                    if detalle_venta_original and detalle_venta_original.producto:
                        producto = detalle_venta_original.producto
                        producto.stock += cantidad
                        producto.save()
                        
                        # Anular el detalle de venta si se cambia todo
                        if cantidad >= detalle_venta_original.cantidad:
                            detalle_venta_original.anulado_individualmente = True
                            detalle_venta_original.save()
                    
                    # Reducir stock del producto nuevo
                    if producto_nuevo:
                        if producto_nuevo.stock < cantidad:
                            raise serializers.ValidationError({"error": f"Stock insuficiente para el producto {producto_nuevo.nombre}."})
                        producto_nuevo.stock -= cantidad
                        producto_nuevo.save()
                
                elif accion == 'AGREGAR':
                    # Reducir stock del producto nuevo
                    if producto_nuevo:
                        if producto_nuevo.stock < cantidad:
                            raise serializers.ValidationError({"error": f"Stock insuficiente para el producto {producto_nuevo.nombre}."})
                        producto_nuevo.stock -= cantidad
                        producto_nuevo.save()
                
                # Calcular monto de diferencia
                monto_diferencia = monto_nuevo - monto_devolucion
                
                # Calcular saldo a favor (si monto_devolucion > monto_nuevo)
                saldo_a_favor = Decimal('0.00')
                if monto_diferencia < 0:
                    saldo_a_favor = abs(monto_diferencia)
                
                cambio_devolucion.monto_devolucion = monto_devolucion
                cambio_devolucion.monto_nuevo = monto_nuevo
                cambio_devolucion.monto_diferencia = monto_diferencia
                cambio_devolucion.saldo_a_favor = saldo_a_favor
                
                # Guardar primero el cambio_devolucion para tener el ID
                cambio_devolucion.save()
                
                # Si hay saldo a favor, generar automáticamente recibo/nota de crédito
                if saldo_a_favor > 0:
                    try:
                        venta_nota_credito = Venta.objects.create(
                            total=saldo_a_favor,
                            tienda=venta_original.tienda,
                            usuario=user,
                            metodo_pago='Nota de Crédito',
                            fecha_venta=timezone.now(),
                            facturada=False,
                            descuento_monto=saldo_a_favor,
                            descuento_porcentaje=Decimal('0.00'),
                            recargo_monto=Decimal('0.00'),
                            recargo_porcentaje=Decimal('0.00'),
                        )
                        
                        DetalleVenta.objects.create(
                            venta=venta_nota_credito,
                            producto=None,
                            cantidad=1,
                            precio_unitario=saldo_a_favor,
                            subtotal=saldo_a_favor,
                            costo_unitario=Decimal('0.00'),
                        )
                        
                        cambio_devolucion.nota_credito_generada = True
                        cambio_devolucion.venta_nota_credito = venta_nota_credito
                        cambio_devolucion.save()
                        logger.info(f"✅ Nota de crédito generada automáticamente: {venta_nota_credito.id} por ${saldo_a_favor}")
                    except Exception as e:
                        logger.error(f"Error al generar nota de crédito automática: {str(e)}", exc_info=True)
                        raise serializers.ValidationError({
                            "error": f"No se pudo generar la nota de crédito: {str(e)}. Detalles: {repr(e)}"
                        })
                
                # Si hay diferencia a pagar, crear venta pendiente para completar desde el flujo normal
                if monto_diferencia > 0:
                    try:
                        venta_diferencia = Venta.objects.create(
                            total=monto_diferencia,
                            tienda=venta_original.tienda,
                            usuario=user,
                            metodo_pago='Pendiente',
                            fecha_venta=timezone.now(),
                            facturada=False,
                        )
                        
                        cambio_devolucion.diferencia_pendiente = True
                        cambio_devolucion.venta_diferencia_pendiente = venta_diferencia
                        cambio_devolucion.save()
                        logger.info(f"✅ Venta pendiente creada para diferencia: {venta_diferencia.id} por ${monto_diferencia}")
                    except Exception as e:
                        logger.error(f"Error al crear venta pendiente para diferencia: {str(e)}", exc_info=True)
                        raise serializers.ValidationError({
                            "error": f"No se pudo crear la venta pendiente para la diferencia: {str(e)}. Detalles: {repr(e)}"
                        })
                
                return cambio_devolucion
            
            @action(detail=True, methods=['get'])
            def obtener_venta_diferencia(self, request, pk=None):
                cambio_devolucion = get_object_or_404(CambioDevolucion, pk=pk)
                
                if not cambio_devolucion.diferencia_pendiente or not cambio_devolucion.venta_diferencia_pendiente:
                    return Response(
                        {"error": "No hay venta pendiente para la diferencia."},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                venta_serializer = VentaSerializer(cambio_devolucion.venta_diferencia_pendiente)
                return Response({
                    "venta": venta_serializer.data,
                    "monto_diferencia": cambio_devolucion.monto_diferencia,
                    "message": "Esta venta puede ser completada desde el flujo normal de ventas."
                })
            
            def update(self, request, *args, **kwargs):
                cambio_devolucion = self.get_object()
                
                if cambio_devolucion.estado == 'CANCELADO':
                    return Response(
                        {"error": "Este cambio/devolución ya está cancelado."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                nuevo_estado = request.data.get('estado')
                if nuevo_estado == 'CANCELADO':
                    for detalle in cambio_devolucion.detalles.all():
                        if detalle.accion in ['DEVOLVER', 'CAMBIAR'] and detalle.detalle_venta_original:
                            if detalle.detalle_venta_original.producto:
                                producto = detalle.detalle_venta_original.producto
                                producto.stock -= detalle.cantidad
                                producto.save()
                                
                                if detalle.detalle_venta_original.anulado_individualmente:
                                    detalle.detalle_venta_original.anulado_individualmente = False
                                    detalle.detalle_venta_original.cantidad += detalle.cantidad
                                    detalle.detalle_venta_original.subtotal = detalle.detalle_venta_original.precio_unitario * detalle.detalle_venta_original.cantidad
                                    detalle.detalle_venta_original.save()
                        
                        if detalle.accion in ['CAMBIAR', 'AGREGAR'] and detalle.producto_nuevo:
                            producto = detalle.producto_nuevo
                            producto.stock += detalle.cantidad
                            producto.save()
                    
                    cambio_devolucion.estado = 'CANCELADO'
                    cambio_devolucion.save()
                    logger.info(f"✅ Cambio/Devolución {cambio_devolucion.id} cancelado. Stock revertido.")
                    
                    return Response({
                        "message": "Cambio/Devolución cancelado con éxito. Los cambios de stock han sido revertidos.",
                        "estado": "CANCELADO"
                    })
                
                return super().update(request, *args, **kwargs)
            
            def list(self, request, *args, **kwargs):
                # Verificar modelos antes de listar
                global CambioDevolucion, DetalleCambioDevolucion
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    try:
                        CambioDevolucion, DetalleCambioDevolucion = _get_cambio_devolucion_models()
                    except Exception as e:
                        logger.error(f"❌ Error obteniendo modelos en list: {e}", exc_info=True)
                        from django.core.exceptions import ImproperlyConfigured
                        raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                if CambioDevolucion is None or DetalleCambioDevolucion is None:
                    from django.core.exceptions import ImproperlyConfigured
                    raise ImproperlyConfigured("CambioDevolucion models not available. Please run migrations and restart the server.")
                
                close_old_connections()
                return super().list(request, *args, **kwargs)
