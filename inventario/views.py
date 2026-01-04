# inventario/views.py - CÓDIGO COMPLETO Y CORREGIDO
# BONITO_AMOR/backend/inventario/views.py
import logging
from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Count, F, Q, Value 
from django.db.models.functions import Coalesce, ExtractYear, ExtractMonth, ExtractDay, ExtractHour
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import DecimalField 
from django.db import close_old_connections # <-- Importado para el fix de conexión
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

# CAMBIO 1: Importar ArancelMetodoTienda
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda, Factura, CambioDevolucion, DetalleCambioDevolucion
from django.core.exceptions import ObjectDoesNotExist 
# CAMBIO 2: Importar ArancelMetodoTiendaSerializer
from .serializers import (
    ProductoSerializer, CategoriaSerializer, TiendaSerializer, UserSerializer,
    VentaSerializer, DetalleVentaSerializer, MetodoPagoSerializer,
    CustomTokenObtainPairSerializer, VentaCreateSerializer,
    CompraSerializer, CompraCreateSerializer, ArancelMetodoTiendaSerializer,
    FacturaSerializer, EmitirFacturaSerializer,
    CambioDevolucionSerializer, CambioDevolucionCreateSerializer, DetalleCambioDevolucionSerializer,
    UserCreateSerializer, UserUpdateSerializer, ChangePasswordSerializer,
    ArancelMetodoTiendaCreateSerializer
)
# Importar modelos de facturación
from .models import Factura
from .services.facturacion_service import FacturacionService
from .filters import VentaFilter 


class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nombre', 'talle', 'codigo_barras']

    def get_queryset(self):
        user = self.request.user
        queryset = Producto.objects.all()

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

class TiendaViewSet(viewsets.ModelViewSet):
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    
    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    # FIX DE CONEXIÓN (Mantenido)
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)

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
        queryset = Venta.objects.all().order_by('-fecha_venta')
        tienda_slug = self.request.query_params.get('tienda_slug', None)
        
        if not user.is_superuser:
            if user.tienda:
                queryset = queryset.filter(tienda=user.tienda)
            else:
                return Venta.objects.none()
        elif tienda_slug:
            queryset = queryset.filter(tienda__nombre=tienda_slug)
    
    def retrieve(self, request, *args, **kwargs):
        """Sobrescribir retrieve para permitir acceso a ventas de nota de crédito relacionadas con cambios/devoluciones"""
        instance = self.get_object()
        
        # Si es una nota de crédito o diferencia pendiente, verificar permisos de manera más flexible
        if instance.metodo_pago in ['Nota de Crédito', 'Pendiente']:
            # Verificar si está relacionada con un cambio/devolución
            cambio_nota_credito = instance.nota_credito_origen.first()
            cambio_diferencia = instance.cambio_devolucion_diferencia.first()
            
            if cambio_nota_credito or cambio_diferencia:
                # Si el usuario tiene acceso a la tienda de la venta original o es superusuario, permitir acceso
                user = request.user
                if user.is_superuser or (user.tienda and instance.tienda == user.tienda):
                    serializer = self.get_serializer(instance)
                    return Response(serializer.data)
        
        # Para otras ventas, usar el comportamiento estándar
        return super().retrieve(request, *args, **kwargs)

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
                if instance.metodo_pago in ['Nota de Crédito', 'Pendiente']:
                    cambio_nota_credito = instance.nota_credito_origen.first()
                    cambio_diferencia = instance.cambio_devolucion_diferencia.first()
                    
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
        venta = get_object_or_404(Venta, pk=pk)
        if venta.anulada:
            return Response({"error": "Esta venta ya ha sido anulada."}, status=status.HTTP_400_BAD_REQUEST)
        
        venta.anulada = True
        venta.save()

        detalles = DetalleVenta.objects.filter(venta=venta)
        for detalle in detalles:
            if detalle.producto and not detalle.anulado_individualmente:
                producto = detalle.producto
                producto.stock += detalle.cantidad
                producto.save()
        
        return Response({"status": "Venta anulada con éxito"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'])
    def anular_detalle(self, request, pk=None):
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

    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)


# CAMBIO CRUCIAL: NUEVO VIEWSET para aranceles
class ArancelMetodoTiendaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ArancelMetodoTiendaCreateSerializer
        return ArancelMetodoTiendaSerializer

    def get_queryset(self):
        user = self.request.user
        # Uso select_related para optimizar la consulta de tienda y método de pago
        queryset = ArancelMetodoTienda.objects.all().select_related('tienda', 'metodo_pago')
        tienda_slug = self.request.query_params.get('tienda_slug', None)

        # Solo superusuarios pueden gestionar aranceles
        if not user.is_superuser:
            return ArancelMetodoTienda.objects.none()

        if tienda_slug:
            return queryset.filter(tienda__nombre=tienda_slug).order_by('metodo_pago__nombre', 'nombre_plan')
        
        return queryset.order_by('tienda__nombre', 'metodo_pago__nombre', 'nombre_plan')

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
                return queryset.filter(tienda__nombre=tienda_slug).order_by('-fecha_compra')
            return queryset.order_by('-fecha_compra')
        elif user.tienda:
            return queryset.filter(tienda=user.tienda).order_by('-fecha_compra')
        return Compra.objects.none()

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
        

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

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

# --- VISTA PARA MÉTRICAS DE VENTAS (ACTUALIZADA) ---
class MetricasAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        tienda_slug = request.query_params.get('tienda_slug', None)
        year = request.query_params.get('year', None)
        month = request.query_params.get('month', None)
        day = request.query_params.get('day', None)
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
        
        # Primero, obtener todas las ventas y calcular el total
        ventas_list = list(queryset_ventas.select_related().prefetch_related('cambio_devolucion_diferencia'))
        total_ventas_periodo = Decimal('0.00')
        
        for venta in ventas_list:
            # Si la venta viene de un cambio/devolución (tiene diferencia pendiente),
            # usar el monto_diferencia del cambio/devolución en lugar del total de la venta
            cambio_diferencia = venta.cambio_devolucion_diferencia.first()
            if cambio_diferencia and cambio_diferencia.monto_diferencia > 0:
                # Solo contar la diferencia, no el total completo de la venta
                total_ventas_periodo += cambio_diferencia.monto_diferencia
            else:
                # Para ventas normales, usar el total
                total_ventas_periodo += venta.total
        
        # Filtramos los detalles de venta para excluir los anulados individualmente
        # Pero para ventas que vienen de cambios/devoluciones, solo contamos los productos nuevos
        detalles_activos = DetalleVenta.objects.filter(venta__in=queryset_ventas, anulado_individualmente=False)
        total_productos_vendidos_periodo = detalles_activos.aggregate(total_productos_vendidos=Sum('cantidad'))['total_productos_vendidos'] or 0
        
        # Calcular costo vendido: para ventas normales usar todos los detalles,
        # para ventas de diferencia solo contar productos nuevos (ya están en los detalles de la venta)
        total_costo_vendido = detalles_activos.aggregate(total_costo_vendido=Sum(F('cantidad') * Coalesce('costo_unitario', Value(0), output_field=DecimalField())))['total_costo_vendido'] or Decimal('0.00')
        
        # Ajustar costo vendido si hay ventas que vienen de cambios/devoluciones
        # (en este caso, los productos ya están correctamente en los detalles, así que no hay que ajustar)

        total_compras_periodo = queryset_compras.aggregate(total_egresos=Sum('total'))['total_egresos'] or Decimal('0.00')

        # CAMBIO 10: NUEVO CÁLCULO: Arancel Total de Ventas con Comisión
        # Calcular arancel considerando solo la diferencia para ventas de cambio/devolución
        total_arancel_ventas = Decimal('0.00')
        for venta in ventas_list:
            cambio_diferencia = venta.cambio_devolucion_diferencia.first()
            if cambio_diferencia and cambio_diferencia.monto_diferencia > 0:
                # Para ventas de diferencia, calcular arancel solo sobre la diferencia
                # (el arancel ya debería estar calculado sobre el total de la venta, pero lo ajustamos proporcionalmente)
                if venta.arancel_total and venta.total > 0:
                    factor_proporcion = cambio_diferencia.monto_diferencia / venta.total
                    total_arancel_ventas += venta.arancel_total * factor_proporcion
            else:
                total_arancel_ventas += venta.arancel_total or Decimal('0.00')


        # CAMBIO 11: La rentabilidad ahora resta el costo de los productos, los egresos Y los aranceles
        rentabilidad_bruta = total_ventas_periodo - total_costo_vendido - total_compras_periodo - total_arancel_ventas
        margen_rentabilidad = (rentabilidad_bruta / total_ventas_periodo * 100) if total_ventas_periodo > 0 else 0

        # Filtrar detalles que tienen producto (excluir notas de crédito y detalles sin producto)
        productos_mas_vendidos = detalles_activos.filter(producto__isnull=False).values(
            'producto__nombre', 'producto__talle'
        ).annotate(
            cantidad_total=Sum('cantidad')
        ).order_by('-cantidad_total')[:10]
        
        # Para ventas por usuario, también aplicar la lógica de diferencia
        ventas_por_usuario_dict = {}
        for venta in ventas_list:
            username = venta.usuario.username if venta.usuario else 'Sin usuario'
            cambio_diferencia = venta.cambio_devolucion_diferencia.first()
            if cambio_diferencia and cambio_diferencia.monto_diferencia > 0:
                monto_venta = cambio_diferencia.monto_diferencia
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
        ventas_por_metodo_pago_dict = {}
        for venta in ventas_list:
            metodo_pago = venta.metodo_pago or 'Sin método'
            cambio_diferencia = venta.cambio_devolucion_diferencia.first()
            if cambio_diferencia and cambio_diferencia.monto_diferencia > 0:
                monto_venta = cambio_diferencia.monto_diferencia
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
            'total_arancel_ventas': total_arancel_ventas, # NUEVA MÉTRICA
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
        
        # Subtotal sin IVA (después de descuentos/recargos)
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

class CambioDevolucionViewSet(viewsets.ModelViewSet):
    """ViewSet para gestionar cambios y devoluciones"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CambioDevolucionCreateSerializer
        return CambioDevolucionSerializer
    
    def get_queryset(self):
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
                    else:
                        # Reducir la cantidad del detalle (se podría crear un nuevo detalle con cantidad negativa, pero por ahora solo anulamos)
                        # En el futuro, se podría implementar una lógica más sofisticada
                        pass
            
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
                    descuento_monto=saldo_a_favor,  # Se registra como descuento (saldo a favor)
                    descuento_porcentaje=Decimal('0.00'),
                    recargo_monto=Decimal('0.00'),
                    recargo_porcentaje=Decimal('0.00'),
                )
                
                # Crear un detalle que indique que es una nota de crédito
                # Nota: producto=None está permitido porque el modelo tiene null=True, blank=True
                DetalleVenta.objects.create(
                    venta=venta_nota_credito,
                    producto=None,  # No hay producto específico para notas de crédito
                    cantidad=1,
                    precio_unitario=saldo_a_favor,
                    subtotal=saldo_a_favor,
                    costo_unitario=Decimal('0.00'),
                )
                
                cambio_devolucion.nota_credito_generada = True
                cambio_devolucion.venta_nota_credito = venta_nota_credito
                cambio_devolucion.save()  # Guardar la relación con la nota de crédito
                logger.info(f"✅ Nota de crédito generada automáticamente: {venta_nota_credito.id} por ${saldo_a_favor}")
            except Exception as e:
                logger.error(f"Error al generar nota de crédito automática: {str(e)}", exc_info=True)
                # Re-lanzar la excepción para que el frontend pueda manejarla
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
                cambio_devolucion.save()  # Guardar la relación con la venta de diferencia
                logger.info(f"✅ Venta pendiente creada para diferencia: {venta_diferencia.id} por ${monto_diferencia}")
            except Exception as e:
                logger.error(f"Error al crear venta pendiente para diferencia: {str(e)}", exc_info=True)
                # Re-lanzar la excepción para que el frontend pueda manejarla
                raise serializers.ValidationError({
                    "error": f"No se pudo crear la venta pendiente para la diferencia: {str(e)}. Detalles: {repr(e)}"
                })
        
        # Retornar el objeto creado para que el método create() pueda usarlo
        return cambio_devolucion
    
    @action(detail=True, methods=['get'])
    def obtener_venta_diferencia(self, request, pk=None):
        """
        Obtiene la venta pendiente creada para la diferencia a pagar.
        Esta venta puede ser completada desde el flujo normal de ventas (PuntoVenta.js)
        """
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
            "message": "Esta venta puede ser completada desde el flujo normal de ventas. Actualiza el método de pago y completa la venta normalmente."
        })
    
    def update(self, request, *args, **kwargs):
        """Permite actualizar el estado del cambio/devolución (ej: cancelar)"""
        cambio_devolucion = self.get_object()
        
        # Solo permitir actualizar el estado si está en estado PROCESADO
        if cambio_devolucion.estado == 'CANCELADO':
            return Response(
                {"error": "Este cambio/devolución ya está cancelado."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Si se intenta cancelar, revertir cambios de stock
        nuevo_estado = request.data.get('estado')
        if nuevo_estado == 'CANCELADO':
            # Revertir cambios de stock
            for detalle in cambio_devolucion.detalles.all():
                if detalle.accion in ['DEVOLVER', 'CAMBIAR'] and detalle.detalle_venta_original:
                    # Revertir devolución de stock (restar stock que se había sumado)
                    if detalle.detalle_venta_original.producto:
                        producto = detalle.detalle_venta_original.producto
                        producto.stock -= detalle.cantidad
                        producto.save()
                        
                        # Revertir anulación del detalle
                        if detalle.detalle_venta_original.anulado_individualmente:
                            detalle.detalle_venta_original.anulado_individualmente = False
                            detalle.detalle_venta_original.cantidad += detalle.cantidad
                            detalle.detalle_venta_original.subtotal = detalle.detalle_venta_original.precio_unitario * detalle.detalle_venta_original.cantidad
                            detalle.detalle_venta_original.save()
                
                if detalle.accion in ['CAMBIAR', 'AGREGAR'] and detalle.producto_nuevo:
                    # Revertir reducción de stock (sumar stock que se había restado)
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
        
        # Para otros campos, usar el update normal
        return super().update(request, *args, **kwargs)
    
    # FIX DE CONEXIÓN
    def list(self, request, *args, **kwargs):
        close_old_connections()
        return super().list(request, *args, **kwargs)