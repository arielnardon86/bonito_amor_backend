# inventario/serializers.py - CÓDIGO COMPLETO Y CORREGIDO
import logging
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, CompraStock, ArancelMetodoTienda, ArancelMercadoLibre, ArancelMercadoLibreProducto, Factura, CategoriaMercadoLibre, NotaCredito, CierreCaja, EgresoCaja, HistorialAccion, Cliente, MovimientoCuentaCorriente, Rubro, Presupuesto, DetallePresupuesto

logger = logging.getLogger(__name__)
# Importación condicional para CambioDevolucion (puede no existir si la migración no está aplicada)
try:
    from .models import CambioDevolucion, DetalleCambioDevolucion
except ImportError:
    CambioDevolucion = None
    DetalleCambioDevolucion = None 
from decimal import Decimal, InvalidOperation 
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer # Importación necesaria aquí

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class VarianteSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ['id', 'nombre', 'talle', 'precio', 'stock', 'codigo_barras',
                  'tn_product_id', 'tn_variant_id', 'tn_sincronizado',
                  'stock_ultimo_ingreso', 'fecha_ultimo_ingreso']


class ProductoSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.SlugRelatedField(
        source='tienda',
        slug_field='nombre',
        queryset=Tienda.objects.all(),
        write_only=True,
        required=False
    )
    variantes = VarianteSimpleSerializer(many=True, read_only=True)
    # Declarado explícito: al estar en unique_together con tienda, el
    # UniqueTogetherValidator de DRF exige que la clave esté presente en el payload
    # (enforce_required_fields), sin importar required=False en el campo. El
    # default=None asegura que siempre esté presente aunque no se envíe (solo se
    # completa desde la carga masiva; la creación manual no lo pide).
    codigo_interno = serializers.CharField(required=False, allow_null=True, allow_blank=True, default=None)

    def get_fields(self):
        """Genera fields dinámicamente verificando si los campos de ML existen"""
        fields = super().get_fields()

        # Remover 'tienda' del serializer ya que usamos 'tienda_slug' en su lugar
        # Esto evita el conflicto con UniqueTogetherValidator
        if 'tienda' in fields and 'tienda_slug' in fields:
            fields.pop('tienda', None)

        # Campos de ML que pueden no existir
        ml_fields = ['ml_item_id', 'ml_sincronizado', 'ml_sincronizar', 'ml_categoria_id', 'ml_ultima_sincronizacion']

        # Verificar si los campos de ML existen en el modelo
        ml_fields_exist = hasattr(Producto, 'ml_item_id')

        # Remover campos de ML si no existen en el modelo
        if not ml_fields_exist:
            for field_name in ml_fields:
                fields.pop(field_name, None)

        # Incluir variantes (relación inversa declarada en clase, no en Meta)
        if 'variantes' not in fields:
            fields['variantes'] = VarianteSimpleSerializer(many=True, read_only=True)

        return fields

    class Meta:
        model = Producto
        fields = '__all__'

    def validate(self, attrs):
        if attrs.get('producto_padre') and not attrs.get('talle'):
            raise serializers.ValidationError(
                {'talle': 'Las variantes deben tener un valor de talle/color/variante.'}
            )
        return attrs

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'
    
    def create(self, validated_data):
        """
        Crea una tienda, estableciendo valores por defecto para campos que pueden no existir
        si las migraciones no están aplicadas.
        """
        # Verificar si los campos de ML existen en el modelo
        ml_fields_exist = hasattr(Tienda, 'plataforma_ecommerce')
        
        if ml_fields_exist:
            # Si los campos existen, establecer valores por defecto
            if 'plataforma_ecommerce' not in validated_data:
                validated_data['plataforma_ecommerce'] = 'NINGUNA'
            if 'ml_modo_test' not in validated_data:
                validated_data['ml_modo_test'] = True
            if 'ml_sync_habilitado' not in validated_data:
                validated_data['ml_sync_habilitado'] = False
            if 'ml_sincronizar_stock' not in validated_data:
                validated_data['ml_sincronizar_stock'] = True
            if 'ml_sincronizar_precios' not in validated_data:
                validated_data['ml_sincronizar_precios'] = True
            if 'ml_sincronizar_productos' not in validated_data:
                validated_data['ml_sincronizar_productos'] = True
            if 'ml_facturar_ventas' not in validated_data:
                validated_data['ml_facturar_ventas'] = True
        else:
            # Si los campos no existen, removerlos de validated_data para evitar errores
            ml_fields = ['plataforma_ecommerce', 'ml_app_id', 'ml_client_secret',
                        'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios',
                        'ml_sincronizar_productos', 'ml_modo_test', 'ml_facturar_ventas', 'ml_aranceles_automaticos', 'ml_user_id',
                        'ml_token_expires_at', 'ml_access_token', 'ml_refresh_token']
            for field in ml_fields:
                validated_data.pop(field, None)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        Actualiza una tienda, manejando campos que pueden no existir
        """
        # Verificar si los campos de ML existen en el modelo
        ml_fields_exist = hasattr(Tienda, 'plataforma_ecommerce')

        if not ml_fields_exist:
            # Si los campos no existen, removerlos de validated_data
            ml_fields = ['plataforma_ecommerce', 'ml_app_id', 'ml_client_secret',
                        'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios',
                        'ml_sincronizar_productos', 'ml_modo_test', 'ml_facturar_ventas', 'ml_aranceles_automaticos', 'ml_user_id',
                        'ml_token_expires_at', 'ml_access_token', 'ml_refresh_token']
            for field in ml_fields:
                validated_data.pop(field, None)
        
        return super().update(instance, validated_data)
    
    def to_representation(self, instance):
        """
        Maneja campos que pueden no existir si las migraciones no están aplicadas.
        """
        data = super().to_representation(instance)
        
        # Campos que pueden no existir si las migraciones no están aplicadas
        campos_fiscales = ['cuit', 'punto_venta', 'tipo_facturacion', 'certificado_afip', 
                          'clave_privada_afip', 'modo_test_afip', 'api_key_arca', 'url_arca',
                          'condicion_iva_emisor']
        
        # Campos de e-commerce (Mercado Libre + Tienda Nube)
        campos_ecommerce = ['plataforma_ecommerce', 'ml_app_id', 'ml_client_secret',
                           'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios',
                           'ml_sincronizar_productos', 'ml_modo_test', 'ml_facturar_ventas', 'ml_aranceles_automaticos', 'ml_user_id',
                           'ml_token_expires_at',
                           'tn_app_id', 'tn_store_id', 'tn_sync_habilitado', 'tn_facturar_ventas',
                           'tn_webhook_id']

        # Campos sensibles que NO se deben exponer en el serializer
        campos_sensibles = ['ml_access_token', 'ml_refresh_token', 'certificado_afip',
                           'clave_privada_afip', 'ml_client_secret',
                           'tn_access_token', 'tn_client_secret']
        
        # Remover campos sensibles de la respuesta
        for campo in campos_sensibles:
            if campo in data:
                del data[campo]
        
        # Agregar valores por defecto para campos que pueden no existir
        for campo in campos_fiscales:
            if campo not in data:
                if campo == 'punto_venta':
                    data[campo] = 1
                elif campo == 'tipo_facturacion':
                    data[campo] = 'NINGUNA'
                elif campo == 'modo_test_afip' or campo == 'condicion_iva_emisor':
                    data[campo] = 'MT' if campo == 'condicion_iva_emisor' else True
                else:
                    data[campo] = None
        
        for campo in campos_ecommerce:
            if campo not in data:
                if campo == 'plataforma_ecommerce':
                    data[campo] = 'NINGUNA'
                elif campo in ['ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios',
                              'ml_sincronizar_productos', 'ml_modo_test', 'ml_facturar_ventas', 'ml_aranceles_automaticos',
                              'tn_sync_habilitado', 'tn_facturar_ventas']:
                    data[campo] = False if campo in ('ml_sync_habilitado', 'tn_sync_habilitado') else True
                else:
                    data[campo] = None
        
        return data

class UserSerializer(serializers.ModelSerializer):
    tienda = serializers.SlugRelatedField(
        slug_field='nombre',
        queryset=Tienda.objects.all(),
        required=False,
        allow_null=True
    )
    tiendas_autorizadas = serializers.SerializerMethodField()

    def get_tiendas_autorizadas(self, obj):
        return list(obj.tiendas_autorizadas.values('id', 'nombre'))

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_supervisor', 'tienda', 'cierre_caja_habilitado', 'tiendas_autorizadas']
        read_only_fields = ['is_staff', 'is_superuser']

class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear nuevos usuarios"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, label='Confirmar contraseña')
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=False, 
        allow_null=True 
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'password2', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_supervisor', 'tienda', 'cierre_caja_habilitado']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        # Si el usuario es superusuario, también debe ser staff automáticamente
        # Si es solo staff, no se asigna is_superuser
        if validated_data.get('is_superuser', False):
            validated_data['is_staff'] = True
        # Si no es superusuario, asegurarse de que is_superuser sea False explícitamente
        elif not validated_data.get('is_superuser', False):
            validated_data['is_superuser'] = False
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer para actualizar usuarios (sin contraseña)"""
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=False, 
        allow_null=True 
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_supervisor', 'tienda', 'cierre_caja_habilitado']

    def update(self, instance, validated_data):
        # Si el usuario es superusuario, también debe ser staff automáticamente
        if validated_data.get('is_superuser', False):
            validated_data['is_staff'] = True
        # Si se desmarca is_superuser, asegurarse de que sea False
        # (pero mantener is_staff si está marcado, ya que pueden ser solo staff)
        elif 'is_superuser' in validated_data and not validated_data.get('is_superuser', False):
            validated_data['is_superuser'] = False
        return super().update(instance, validated_data)

class ChangePasswordSerializer(serializers.Serializer):
    """Serializer para cambiar contraseña"""
    new_password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})
    new_password2 = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'}, label='Confirmar nueva contraseña')

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Las contraseñas no coinciden."})
        return attrs

class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

# NUEVO SERIALIZER: Arancel por Método y Tienda
class ArancelMetodoTiendaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    
    class Meta:
        model = ArancelMetodoTienda
        fields = ['id', 'tienda', 'tienda_nombre', 'metodo_pago', 'metodo_pago_nombre', 'nombre_plan', 'arancel_porcentaje']
        
    def validate_arancel_porcentaje(self, value):
        """Validar que el arancel esté entre 0 y 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("El arancel debe estar entre 0 y 100%")
        return value

class ArancelMetodoTiendaCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar aranceles"""
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=True,
        write_only=True
    )
    
    class Meta:
        model = ArancelMetodoTienda
        fields = ['id', 'tienda', 'metodo_pago', 'nombre_plan', 'arancel_porcentaje']
        
    def validate_arancel_porcentaje(self, value):
        """Validar que el arancel esté entre 0 y 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("El arancel debe estar entre 0 y 100%")
        return value
# ------------------------------------------------

# SERIALIZER: Arancel Mercado Libre por Categoría
class ArancelMercadoLibreSerializer(serializers.ModelSerializer):
    categoria_ml_nombre = serializers.CharField(source='categoria_ml.nombre', read_only=True)
    categoria_ml_id = serializers.CharField(source='categoria_ml.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    
    class Meta:
        model = ArancelMercadoLibre
        fields = ['id', 'tienda', 'tienda_nombre', 'categoria_ml', 'categoria_ml_id', 'categoria_ml_nombre', 'arancel_porcentaje', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['fecha_creacion', 'fecha_actualizacion']
        
    def validate_arancel_porcentaje(self, value):
        """Validar que el arancel esté entre 0 y 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("El arancel debe estar entre 0 y 100%")
        return value

class ArancelMercadoLibreCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear/actualizar aranceles ML"""
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=True,
        write_only=True
    )
    categoria_ml = serializers.PrimaryKeyRelatedField(
        queryset=CategoriaMercadoLibre.objects.all(),
        required=True
    )
    
    class Meta:
        model = ArancelMercadoLibre
        fields = ['id', 'tienda', 'categoria_ml', 'arancel_porcentaje']
        
    def validate_arancel_porcentaje(self, value):
        """Validar que el arancel esté entre 0 y 100"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("El arancel debe estar entre 0 y 100%")
        return value
    
    def validate(self, data):
        """Validar que la tienda tenga integración ML"""
        tienda = data.get('tienda')
        if tienda:
            tiene_ml = (
                hasattr(tienda, 'plataforma_ecommerce') and
                tienda.plataforma_ecommerce == 'MERCADO_LIBRE' and
                hasattr(tienda, 'ml_access_token') and
                tienda.ml_access_token
            )
            if not tiene_ml:
                raise serializers.ValidationError("La tienda debe tener integración con Mercado Libre configurada.")
        return data
# ------------------------------------------------

# SERIALIZER: Arancel Mercado Libre por Producto (arancel % + costo envío)
class ArancelMercadoLibreProductoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    
    class Meta:
        model = ArancelMercadoLibreProducto
        fields = ['id', 'tienda', 'tienda_nombre', 'producto', 'producto_nombre', 'arancel_porcentaje', 'costo_envio', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['fecha_creacion', 'fecha_actualizacion']

class ArancelMercadoLibreProductoCreateSerializer(serializers.ModelSerializer):
    tienda = serializers.SlugRelatedField(slug_field='nombre', queryset=Tienda.objects.all(), required=True, write_only=True)
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all(), required=True)
    
    class Meta:
        model = ArancelMercadoLibreProducto
        fields = ['id', 'tienda', 'producto', 'arancel_porcentaje', 'costo_envio']
    
    def validate_arancel_porcentaje(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("El arancel debe estar entre 0 y 100%")
        return value
    
    def validate_costo_envio(self, value):
        if value < 0:
            raise serializers.ValidationError("El costo de envío no puede ser negativo")
        return value
# ------------------------------------------------

class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True, allow_null=True) 
    
    class Meta:
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'costo_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion']
        model = DetalleVenta
        read_only_fields = ['subtotal']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    # Campos de arancel para lectura
    arancel_aplicado_nombre = serializers.CharField(source='arancel_aplicado.nombre_plan', read_only=True)
    arancel_aplicado_porcentaje = serializers.DecimalField(source='arancel_aplicado.arancel_porcentaje', max_digits=5, decimal_places=2, read_only=True)
    # Campo para saber si tiene factura asociada
    tiene_factura = serializers.SerializerMethodField()
    
    # Campos relacionados con cambios/devoluciones
    cambio_devolucion_nota_credito = serializers.SerializerMethodField()
    cambio_devolucion_diferencia = serializers.SerializerMethodField()
    es_nota_credito = serializers.SerializerMethodField()
    es_diferencia_pendiente = serializers.SerializerMethodField()

    def get_tiene_factura(self, obj):
        """Verifica si la venta tiene una factura asociada (usa select_related)"""
        try:
            return obj.factura is not None
        except Exception:
            return False

    def get_cambio_devolucion_nota_credito(self, obj):
        """Obtiene el cambio/devolución que generó esta nota de crédito (usa prefetch cache)"""
        if CambioDevolucion is None:
            return None
        try:
            # Usar .all() para aprovechar el prefetch_related cache
            cached = obj.nota_credito_origen.all()
            cambio = cached[0] if cached else None
            if cambio:
                productos_devueltos = []
                # Usar .all() en detalles para aprovechar prefetch cache
                for detalle in cambio.detalles.all():
                    if detalle.accion not in ('DEVOLVER', 'CAMBIAR'):
                        continue
                    if detalle.detalle_venta_original and detalle.detalle_venta_original.producto:
                        productos_devueltos.append({
                            'nombre': detalle.detalle_venta_original.producto.nombre,
                            'cantidad': detalle.cantidad
                        })
                return {
                    'id': str(cambio.id),
                    'venta_original_id': str(cambio.venta_original_id),
                    'fecha_creacion': cambio.fecha_creacion,
                    'tipo': cambio.tipo,
                    'saldo_a_favor': str(cambio.saldo_a_favor),
                    'productos_devueltos': productos_devueltos
                }
        except Exception:
            pass
        return None

    def get_cambio_devolucion_diferencia(self, obj):
        """Obtiene el cambio/devolución que generó esta venta de diferencia (usa prefetch cache)"""
        if CambioDevolucion is None:
            return None
        try:
            cached = obj.cambio_devolucion_diferencia.all()
            cambio = cached[0] if cached else None
            if cambio:
                return {
                    'id': str(cambio.id),
                    'venta_original_id': str(cambio.venta_original_id),
                    'fecha_creacion': cambio.fecha_creacion,
                    'tipo': cambio.tipo,
                    'monto_diferencia': str(cambio.monto_diferencia),
                    'monto_devolucion': str(cambio.monto_devolucion),
                    'monto_nuevo': str(cambio.monto_nuevo),
                    'saldo_a_favor': str(cambio.saldo_a_favor)
                }
        except Exception:
            pass
        return None

    def get_es_nota_credito(self, obj):
        """Indica si esta venta es una nota de crédito (usa prefetch cache)"""
        if CambioDevolucion is None:
            return False
        try:
            return len(obj.nota_credito_origen.all()) > 0
        except Exception:
            return False

    def get_es_diferencia_pendiente(self, obj):
        """Indica si esta venta es una diferencia pendiente de un cambio/devolución (usa prefetch cache)"""
        if CambioDevolucion is None:
            return False
        try:
            return len(obj.cambio_devolucion_diferencia.all()) > 0
        except Exception:
            return False

    class Meta:
        model = Venta
        fields = [
            'id', 'fecha_venta', 'total', 'anulada', 
            'descuento_porcentaje', 'descuento_monto',
            'recargo_porcentaje', 'recargo_monto',
            'metodo_pago', 'metodo_pago_nombre', 
            'usuario', 'tienda', 'tienda_nombre', 'detalles',
            'arancel_aplicado', 'arancel_aplicado_nombre', 'arancel_aplicado_porcentaje', 'arancel_total',
            'costo_envio_ml', 'origen_mercadolibre', 'ml_order_id',
            'ml_sale_fee', 'ml_shipping_cost', 'ml_tax_fee', 'ml_fecha_entrega',
            'fecha_creacion', 'fecha_actualizacion', 'tiene_factura', 'facturada',
            'cambio_devolucion_nota_credito', 'cambio_devolucion_diferencia',
            'es_nota_credito', 'es_diferencia_pendiente'
        ]

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(
        child=serializers.DictField(),
        write_only=True 
    )
    tienda_slug = serializers.CharField(write_only=True)
    arancel_aplicado_id = serializers.PrimaryKeyRelatedField(
        queryset=ArancelMetodoTienda.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    arancel_total_ml = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True,
        help_text="Arancel total calculado para ventas Mercado Libre (por producto)")
    costo_envio_ml = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True,
        help_text="Costo de envío total para ventas Mercado Libre (por producto)")
    arancel_combinado = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, write_only=True,
        help_text="Suma de aranceles de todos los métodos en un pago combinado")
    cambio_devolucion_id = serializers.UUIDField(required=False, allow_null=True, write_only=True, help_text="ID del cambio/devolución relacionado (para ventas por diferencia)")
    presupuesto_id = serializers.UUIDField(required=False, allow_null=True, write_only=True, help_text="ID del presupuesto que se está convirtiendo en venta")
    cliente_id = serializers.PrimaryKeyRelatedField(
        source='cliente', queryset=Cliente.objects.all(), required=False, allow_null=True, write_only=True,
        help_text="Cliente asociado a la venta. Obligatorio si metodo_pago='Cuenta Corriente'."
    )

    def to_internal_value(self, data):
        """Normalizar arancel_aplicado_id/cliente_id antes de la validación: convertir cadena vacía a None"""
        if isinstance(data, dict):
            if data.get('arancel_aplicado_id') == '':
                data['arancel_aplicado_id'] = None
            if data.get('cliente_id') == '':
                data['cliente_id'] = None
        return super().to_internal_value(data)
    
    class Meta:
        model = Venta
        fields = [
            'id',
            'fecha_venta',
            'descuento_porcentaje', 'descuento_monto', 
            'recargo_porcentaje', 'recargo_monto', 
            'metodo_pago', 'monto_efectivo',
            'tienda_slug', 'detalles', 'arancel_aplicado_id', 'arancel_total_ml', 'costo_envio_ml', 'arancel_combinado', 'cambio_devolucion_id',
            'presupuesto_id', 'cliente_id',
        ]
        extra_kwargs = {
            'descuento_porcentaje': {'required': False},
            'descuento_monto': {'required': False},
            'recargo_porcentaje': {'required': False},
            'recargo_monto': {'required': False},
            'monto_efectivo': {'required': False},
        }

    def validate(self, data):
        detalles_data = data.get('detalles', [])
        tienda_slug = data.get('tienda_slug')

        if not detalles_data:
            raise serializers.ValidationError("La venta debe tener al menos un detalle de venta.")
        if not tienda_slug:
            raise serializers.ValidationError({"tienda_slug": "El slug de la tienda es obligatorio."})

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        data['tienda'] = tienda_obj
        
        calculated_subtotal = Decimal('0.00')
        for detalle_data in detalles_data:
            producto_id = detalle_data.get('producto')
            cantidad = detalle_data.get('cantidad')
            precio_unitario = detalle_data.get('precio_unitario')

            if not all([producto_id, cantidad, precio_unitario is not None]):
                raise serializers.ValidationError({"detalles": "Cada detalle debe tener un 'producto', 'cantidad' y 'precio_unitario'."})

            try:
                producto_obj = Producto.objects.get(id=producto_id, tienda=tienda_obj)
            except Producto.DoesNotExist:
                raise serializers.ValidationError({"detalles": f"Producto con ID {producto_id} no encontrado en la tienda {tienda_slug}."})
            
            # Si la venta viene de un cambio/devolución, el stock ya se validó y restó,
            # así que no validamos stock aquí para evitar errores
            cambio_devolucion_id = data.get('cambio_devolucion_id')
            if not cambio_devolucion_id and producto_obj.stock < cantidad:
                raise serializers.ValidationError({"detalles": f"Stock insuficiente para el producto {producto_obj.nombre}. Stock disponible: {producto_obj.stock}, solicitado: {cantidad}."})
            
            if precio_unitario < 0:
                raise serializers.ValidationError({"detalles": "El precio unitario no puede ser negativo."})

            calculated_subtotal += precio_unitario * cantidad
            # Agrega el costo al detalle de datos si existe
            detalle_data['costo_unitario'] = producto_obj.costo

        descuento_porcentaje = data.get('descuento_porcentaje', Decimal('0.00'))
        descuento_monto = data.get('descuento_monto', Decimal('0.00'))
        recargo_porcentaje = data.get('recargo_porcentaje', Decimal('0.00'))
        recargo_monto = data.get('recargo_monto', Decimal('0.00'))
        
        # Validación de exclusividad: Solo puede haber un tipo de ajuste
        ajustes_aplicados = [a for a in [descuento_monto, descuento_porcentaje, recargo_monto, recargo_porcentaje] if a > Decimal('0.00')]

        if len(ajustes_aplicados) > 1:
            raise serializers.ValidationError({"ajustes": "Solo se puede aplicar un tipo de ajuste (desc. monto/porcentaje o recargo monto/porcentaje) a la vez."})
        
        # CÁLCULO DEL TOTAL CON RECARGO/DESCUENTO
        if recargo_monto > 0: 
            data['total'] = calculated_subtotal + recargo_monto
        elif recargo_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') + (recargo_porcentaje / Decimal('100')))
        elif descuento_monto > 0:
            data['total'] = max(Decimal('0.00'), calculated_subtotal - descuento_monto)
        elif descuento_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') - (descuento_porcentaje / Decimal('100')))
        else:
            data['total'] = calculated_subtotal
        
        # Lógica de arancel
        data['arancel_total'] = Decimal('0.00')
        arancel_obj      = data.pop('arancel_aplicado_id', None)
        arancel_combinado = data.pop('arancel_combinado', None)

        # Normalizar: si viene como cadena vacía o None, convertir a None
        if arancel_obj == '' or arancel_obj is None:
            arancel_obj = None

        metodos_financieros = MetodoPago.objects.filter(es_financiero=True).values_list('nombre', flat=True)
        es_mercadolibre = data.get('metodo_pago') == 'Mercado Libre'
        # Pago combinado: el frontend siempre envía arancel_combinado (incluso si es 0)
        es_combinado = arancel_combinado is not None

        if es_mercadolibre:
            data['arancel_total'] = data.pop('arancel_total_ml', None) or Decimal('0.00')
            data['costo_envio_ml'] = data.pop('costo_envio_ml', None) or Decimal('0.00')
        elif es_combinado:
            # Pago combinado: arancel calculado en el frontend por cada tramo
            data['arancel_total'] = Decimal(str(arancel_combinado or 0))
        elif data.get('metodo_pago') in metodos_financieros:
            if not arancel_obj:
                 raise serializers.ValidationError({"arancel_aplicado_id": "Se requiere seleccionar un Plan/Arancel para este método de pago."})

            if arancel_obj.tienda != data['tienda']:
                 raise serializers.ValidationError({"arancel_aplicado_id": "El arancel seleccionado no pertenece a la tienda actual."})

            arancel_porcentaje = arancel_obj.arancel_porcentaje
            total_final = data['total']
            data['arancel_total'] = total_final * (arancel_porcentaje / Decimal('100'))
            data['arancel_aplicado'] = arancel_obj

        elif arancel_obj:
            raise serializers.ValidationError({"metodo_pago": "No se permite seleccionar un Arancel para el método de pago seleccionado."})

        # Cuenta Corriente: el cliente es obligatorio y debe pertenecer a la misma tienda
        # de esta venta (nunca al conjunto ampliado de tiendas_autorizadas del usuario).
        cliente_obj = data.get('cliente')
        if data.get('metodo_pago') == 'Cuenta Corriente':
            if not cliente_obj:
                raise serializers.ValidationError({"cliente_id": "Se requiere seleccionar un Cliente para el método de pago Cuenta Corriente."})
            if cliente_obj.tienda != data['tienda']:
                raise serializers.ValidationError({"cliente_id": "El cliente seleccionado no pertenece a la tienda actual."})

        data['fecha_venta'] = timezone.now()

        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        cambio_devolucion_id = validated_data.pop('cambio_devolucion_id', None)
        presupuesto_id = validated_data.pop('presupuesto_id', None)
        cliente_obj = validated_data.pop('cliente', None)

        arancel_aplicado = validated_data.pop('arancel_aplicado', None)
        arancel_total = validated_data.pop('arancel_total', Decimal('0.00'))

        # Obtener el usuario del request y asegurarse de que sea una instancia del modelo User correcto
        # El problema es que request.user puede ser un TokenUser de SimpleJWT, no el modelo User real
        user = self.context['request'].user
        user_obj = None
        
        if user and not user.is_anonymous:
            try:
                # Intentar obtener el usuario real de la base de datos usando su ID
                # Esto funciona tanto si user es un User real como si es un TokenUser
                user_obj = User.objects.get(pk=user.pk)
            except (AttributeError, User.DoesNotExist, TypeError, ValueError) as e:
                # Si no se puede obtener el usuario, usar None (el campo permite null)
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"No se pudo obtener el usuario de la BD: {e}. Usando None.")
                user_obj = None

        costo_envio_ml = validated_data.pop('costo_envio_ml', Decimal('0.00'))
        monto_efectivo = validated_data.pop('monto_efectivo', None)

        # Si el frontend no envió monto_efectivo, deducirlo del metodo_pago
        metodo = validated_data.get('metodo_pago', '') or ''
        if monto_efectivo is None:
            if 'efectivo' in metodo.lower() and '+' not in metodo:
                monto_efectivo = validated_data.get('total', Decimal('0.00'))
            else:
                monto_efectivo = Decimal('0.00')

        # Para ventas de cambio/devolución, el total y el efectivo recibido deben ser
        # solo la diferencia a pagar, no el precio completo del producto nuevo.
        # El frontend envía los items del carrito a precio completo, pero lo que se cobra
        # es únicamente la diferencia (precio_nuevo - crédito_por_devuelto), con los
        # descuentos/recargos aplicados sobre esa diferencia (no sobre el precio del producto).
        if cambio_devolucion_id:
            try:
                from .models import CambioDevolucion as _CD
                cd = _CD.objects.get(id=cambio_devolucion_id)
                monto_base = cd.monto_diferencia  # raw difference: monto_nuevo - monto_devolucion

                # Reconstruct new-items subtotal and devolution credit from cart detalles
                monto_nuevo_full = sum(
                    Decimal(str(d.get('precio_unitario', 0))) * Decimal(str(d.get('cantidad', 0)))
                    for d in detalles_data
                )
                monto_devolucion_credito = monto_nuevo_full - monto_base

                desc_monto = validated_data.get('descuento_monto') or Decimal('0.00')
                desc_pct   = validated_data.get('descuento_porcentaje') or Decimal('0.00')
                rec_monto  = validated_data.get('recargo_monto') or Decimal('0.00')
                rec_pct    = validated_data.get('recargo_porcentaje') or Decimal('0.00')

                if desc_pct > 0:
                    # Discount applies to new items total, then devolution credit is subtracted.
                    # This matches the intent: "X% off what the customer is taking new".
                    total_final = max(Decimal('0.00'),
                        monto_nuevo_full * (Decimal('1') - desc_pct / Decimal('100')) - monto_devolucion_credito
                    )
                elif desc_monto > 0:
                    if desc_monto <= monto_base:
                        # Discount directly on the remaining difference
                        total_final = max(Decimal('0.00'), monto_base - desc_monto)
                    else:
                        # desc_monto was computed in the frontend to include the devolution credit
                        # (redondearMonto path). validate() already produced the correct total:
                        # total = monto_nuevo_full - desc_monto (already ≈ customer's net payment).
                        total_final = validated_data['total']
                elif rec_monto > 0:
                    total_final = monto_base + rec_monto
                elif rec_pct > 0:
                    total_final = monto_base * (Decimal('1') + rec_pct / Decimal('100'))
                else:
                    total_final = monto_base

                validated_data['total'] = max(Decimal('0.00'), total_final)
                if 'efectivo' in metodo.lower() and '+' not in metodo:
                    monto_efectivo = validated_data['total']
            except Exception:
                pass

        venta = Venta.objects.create(
            total=validated_data['total'],
            usuario=user_obj,
            tienda=validated_data['tienda'],
            metodo_pago=validated_data['metodo_pago'],
            monto_efectivo=monto_efectivo,
            descuento_porcentaje=validated_data.get('descuento_porcentaje', Decimal('0.00')),
            descuento_monto=validated_data.get('descuento_monto', Decimal('0.00')),
            recargo_porcentaje=validated_data.get('recargo_porcentaje', Decimal('0.00')),
            recargo_monto=validated_data.get('recargo_monto', Decimal('0.00')),
            arancel_aplicado=arancel_aplicado,
            costo_envio_ml=costo_envio_ml,
            arancel_total=arancel_total,
            fecha_venta=validated_data['fecha_venta'],
            cliente=cliente_obj,
        )

        # Cuenta Corriente: registrar el débito en el libro de movimientos del cliente.
        # La venta cuenta como ingreso real desde ya (no se excluye de métricas); lo único
        # que queda pendiente es el cobro físico, que se registra aparte vía cobrar_deuda.
        if validated_data['metodo_pago'] == 'Cuenta Corriente' and cliente_obj:
            MovimientoCuentaCorriente.objects.create(
                cliente=cliente_obj,
                tienda=validated_data['tienda'],
                venta=venta,
                usuario=user_obj,
                tipo='DEBITO',
                monto=venta.total,
                concepto=f'Venta {venta.id}',
            )

        # Si viene de un cambio/devolución, relacionar la venta con el cambio/devolución
        if cambio_devolucion_id:
            try:
                from .models import CambioDevolucion
                import logging as _logging
                _logger = _logging.getLogger(__name__)
                cambio_devolucion = CambioDevolucion.objects.get(id=cambio_devolucion_id)
                # Reemplazar la venta Pendiente placeholder por la venta real
                old_pendiente = cambio_devolucion.venta_diferencia_pendiente
                cambio_devolucion.venta_diferencia_pendiente = venta
                cambio_devolucion.diferencia_pendiente = False
                cambio_devolucion.save()
                if old_pendiente and old_pendiente.id != venta.id and old_pendiente.metodo_pago == 'Pendiente':
                    try:
                        old_pendiente.delete()
                    except Exception as e:
                        # No fallar la venta si no se puede borrar el placeholder
                        _logger.warning("No se pudo eliminar venta Pendiente %s al procesar cambio/devolución: %s", old_pendiente.id, e)
            except CambioDevolucion.DoesNotExist:
                pass
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning("Error al vincular venta %s con CambioDevolucion %s: %s", venta.id, cambio_devolucion_id, e)

        # Si viene de un presupuesto, marcarlo como convertido y linkear la venta generada
        if presupuesto_id:
            try:
                from .models import Presupuesto as _Presupuesto
                presupuesto = _Presupuesto.objects.get(id=presupuesto_id)
                presupuesto.estado = 'CONVERTIDO'
                presupuesto.venta_generada = venta
                presupuesto.save(update_fields=['estado', 'venta_generada', 'fecha_actualizacion'])
            except _Presupuesto.DoesNotExist:
                pass
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning("Error al vincular venta %s con Presupuesto %s: %s", venta.id, presupuesto_id, e)

        for detalle_data in detalles_data:
            producto_id = detalle_data['producto'] 
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']
            costo_unitario = detalle_data.get('costo_unitario', None)

            producto_obj = Producto.objects.get(id=producto_id)
            subtotal = precio_unitario * cantidad
            DetalleVenta.objects.create(
                venta=venta,
                subtotal=subtotal,
                producto=producto_obj,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                costo_unitario=costo_unitario
            )

            # NO restar stock si la venta viene de un cambio/devolución
            # porque el stock ya se restó cuando se procesó el cambio/devolución
            if not cambio_devolucion_id:
                producto_obj.stock -= cantidad
                producto_obj.save()

        # Enviar notificaciones push a usuarios de la tienda
        try:
            from .services.notificaciones_service import NotificacionesService
            NotificacionesService.enviar_notificacion_venta(venta)
        except Exception as e:
            # No fallar la creación de la venta si las notificaciones fallan
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al enviar notificaciones push para venta {venta.id}: {str(e)}")

        return venta


# ── Presupuestos ──────────────────────────────────────────────────────────────

class DetallePresupuestoSerializer(serializers.ModelSerializer):
    producto = ProductoSerializer(read_only=True)

    class Meta:
        model = DetallePresupuesto
        fields = ['id', 'producto', 'cantidad', 'precio_unitario', 'subtotal']
        read_only_fields = fields


class PresupuestoSerializer(serializers.ModelSerializer):
    detalles = DetallePresupuestoSerializer(many=True, read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre_razon_social', read_only=True)
    cliente_cuit = serializers.CharField(source='cliente.cuit_cuil', read_only=True)
    cliente_email = serializers.CharField(source='cliente.email', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = Presupuesto
        fields = [
            'id', 'tienda', 'tienda_nombre', 'cliente', 'cliente_nombre', 'cliente_cuit', 'cliente_email',
            'usuario', 'usuario_nombre', 'estado', 'estado_display', 'metodo_pago_sugerido',
            'descuento_porcentaje', 'descuento_monto', 'recargo_porcentaje', 'recargo_monto', 'total',
            'venta_generada', 'notas', 'fecha_creacion', 'fecha_actualizacion', 'detalles',
        ]
        read_only_fields = ['id', 'estado', 'venta_generada', 'fecha_creacion', 'fecha_actualizacion']

    def get_usuario_nombre(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'


class PresupuestoCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(child=serializers.DictField(), write_only=True)
    tienda_slug = serializers.CharField(write_only=True)
    # A diferencia de Venta, el cliente es obligatorio: todo presupuesto se genera para alguien puntual.
    cliente_id = serializers.PrimaryKeyRelatedField(
        source='cliente', queryset=Cliente.objects.all(), write_only=True,
        help_text="Cliente para el que se genera el presupuesto (obligatorio)."
    )

    class Meta:
        model = Presupuesto
        fields = [
            'id', 'tienda_slug', 'cliente_id', 'detalles',
            'descuento_porcentaje', 'descuento_monto', 'recargo_porcentaje', 'recargo_monto',
            'metodo_pago_sugerido', 'notas',
        ]
        extra_kwargs = {
            'descuento_porcentaje': {'required': False},
            'descuento_monto': {'required': False},
            'recargo_porcentaje': {'required': False},
            'recargo_monto': {'required': False},
            'metodo_pago_sugerido': {'required': False, 'allow_null': True, 'allow_blank': True},
            'notas': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def validate(self, data):
        detalles_data = data.get('detalles', [])
        tienda_slug = data.get('tienda_slug')
        cliente = data.get('cliente')

        if not detalles_data:
            raise serializers.ValidationError({"detalles": "El presupuesto debe tener al menos un producto."})
        if not tienda_slug:
            raise serializers.ValidationError({"tienda_slug": "El slug de la tienda es obligatorio."})
        if not cliente:
            raise serializers.ValidationError({"cliente_id": "Debe seleccionar un cliente para generar el presupuesto."})

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        if cliente.tienda_id != tienda_obj.id:
            raise serializers.ValidationError({"cliente_id": "El cliente seleccionado no pertenece a la tienda actual."})

        data['tienda'] = tienda_obj

        calculated_subtotal = Decimal('0.00')
        for detalle_data in detalles_data:
            producto_id = detalle_data.get('producto')
            cantidad = detalle_data.get('cantidad')
            precio_unitario = detalle_data.get('precio_unitario')

            if not all([producto_id, cantidad, precio_unitario is not None]):
                raise serializers.ValidationError({"detalles": "Cada detalle debe tener 'producto', 'cantidad' y 'precio_unitario'."})

            try:
                Producto.objects.get(id=producto_id, tienda=tienda_obj)
            except Producto.DoesNotExist:
                raise serializers.ValidationError({"detalles": f"Producto con ID {producto_id} no encontrado en la tienda {tienda_slug}."})

            if Decimal(str(precio_unitario)) < 0:
                raise serializers.ValidationError({"detalles": "El precio unitario no puede ser negativo."})
            if int(cantidad) <= 0:
                raise serializers.ValidationError({"detalles": "La cantidad debe ser mayor a 0."})

            # No se valida ni descuenta stock: un presupuesto es una cotización, no una operación de inventario.
            calculated_subtotal += Decimal(str(precio_unitario)) * int(cantidad)

        descuento_porcentaje = data.get('descuento_porcentaje') or Decimal('0.00')
        descuento_monto = data.get('descuento_monto') or Decimal('0.00')
        recargo_porcentaje = data.get('recargo_porcentaje') or Decimal('0.00')
        recargo_monto = data.get('recargo_monto') or Decimal('0.00')

        ajustes_aplicados = [a for a in [descuento_monto, descuento_porcentaje, recargo_monto, recargo_porcentaje] if a > Decimal('0.00')]
        if len(ajustes_aplicados) > 1:
            raise serializers.ValidationError({"ajustes": "Solo se puede aplicar un tipo de ajuste (descuento o recargo) a la vez."})

        if recargo_monto > 0:
            data['total'] = calculated_subtotal + recargo_monto
        elif recargo_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') + recargo_porcentaje / Decimal('100'))
        elif descuento_monto > 0:
            data['total'] = max(Decimal('0.00'), calculated_subtotal - descuento_monto)
        elif descuento_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') - descuento_porcentaje / Decimal('100'))
        else:
            data['total'] = calculated_subtotal

        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        tienda_obj = validated_data.pop('tienda')
        cliente_obj = validated_data.pop('cliente')

        # Mismo criterio que VentaCreateSerializer: request.user puede ser un TokenUser de SimpleJWT.
        user = self.context['request'].user
        user_obj = None
        if user and not user.is_anonymous:
            try:
                user_obj = User.objects.get(pk=user.pk)
            except (AttributeError, User.DoesNotExist, TypeError, ValueError):
                user_obj = None

        presupuesto = Presupuesto.objects.create(
            tienda=tienda_obj,
            cliente=cliente_obj,
            usuario=user_obj,
            total=validated_data.get('total', Decimal('0.00')),
            descuento_porcentaje=validated_data.get('descuento_porcentaje') or Decimal('0.00'),
            descuento_monto=validated_data.get('descuento_monto') or Decimal('0.00'),
            recargo_porcentaje=validated_data.get('recargo_porcentaje') or Decimal('0.00'),
            recargo_monto=validated_data.get('recargo_monto') or Decimal('0.00'),
            metodo_pago_sugerido=validated_data.get('metodo_pago_sugerido') or None,
            notas=validated_data.get('notas') or None,
        )

        for detalle_data in detalles_data:
            producto_obj = Producto.objects.get(id=detalle_data['producto'])
            cantidad = int(detalle_data['cantidad'])
            precio_unitario = Decimal(str(detalle_data['precio_unitario']))
            DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                producto=producto_obj,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=precio_unitario * cantidad,
            )

        return presupuesto


# Serializers para Facturación
class FacturaSerializer(serializers.ModelSerializer):
    venta_id = serializers.UUIDField(source='venta.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    tienda_cuit = serializers.CharField(source='tienda.cuit', read_only=True)
    tienda_direccion = serializers.CharField(source='tienda.direccion', read_only=True)
    numero_factura_completo = serializers.CharField(read_only=True)

    class Meta:
        model = Factura
        fields = [
            'id', 'venta', 'venta_id', 'tienda', 'tienda_nombre',
            'tienda_cuit', 'tienda_direccion',
            'numero_comprobante', 'punto_venta', 'tipo_comprobante',
            'numero_factura_completo',
            'cliente_nombre', 'cliente_cuit', 'cliente_domicilio',
            'cliente_tipo_documento', 'cliente_condicion_iva',
            'subtotal', 'impuesto_iva', 'total',
            'estado', 'sistema_facturacion',
            'cae', 'fecha_vencimiento_cae', 'numero_comprobante_afip',
            'error_mensaje', 'fecha_emision', 'fecha_actualizacion'
        ]
        read_only_fields = [
            'id', 'numero_comprobante', 'cae', 'fecha_vencimiento_cae',
            'numero_comprobante_afip', 'estado', 'error_mensaje',
            'fecha_emision', 'fecha_actualizacion'
        ]

class NotaCreditoSerializer(serializers.ModelSerializer):
    numero_nc_completo = serializers.ReadOnlyField()
    factura_numero     = serializers.CharField(source='factura_origen.numero_factura_completo', read_only=True)
    tienda_nombre      = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model  = NotaCredito
        fields = [
            'id', 'factura_origen', 'factura_numero', 'tienda', 'tienda_nombre',
            'numero_comprobante', 'punto_venta', 'tipo_comprobante', 'numero_nc_completo',
            'motivo', 'monto', 'impuesto_iva',
            'cliente_nombre', 'cliente_cuit',
            'estado', 'sistema_facturacion',
            'cae', 'fecha_vencimiento_cae', 'numero_comprobante_afip',
            'error_mensaje', 'fecha_emision',
        ]
        read_only_fields = [
            'id', 'numero_comprobante', 'cae', 'fecha_vencimiento_cae',
            'numero_comprobante_afip', 'estado', 'error_mensaje', 'fecha_emision',
        ]


class EmitirNotaCreditoSerializer(serializers.Serializer):
    """Datos necesarios para emitir una nota de crédito vinculada a una factura."""
    monto  = serializers.DecimalField(max_digits=10, decimal_places=2)
    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')


class EmitirFacturaSerializer(serializers.Serializer):
    """Serializer para emitir una factura desde una venta"""
    # venta_id es opcional porque el pk viene en la URL del endpoint
    venta_id = serializers.UUIDField(required=False, allow_null=True)
    cliente_nombre = serializers.CharField(required=True, max_length=255)
    cliente_cuit = serializers.CharField(required=False, max_length=13, allow_blank=True, allow_null=True)
    cliente_domicilio = serializers.CharField(required=False, max_length=255, allow_blank=True, allow_null=True)
    cliente_tipo_documento = serializers.CharField(required=False, max_length=20, allow_blank=True, allow_null=True)
    cliente_condicion_iva = serializers.ChoiceField(
        choices=Factura.CONDICION_IVA_CHOICES,
        default='CF',
        required=False
    )

class EgresoCajaSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    tipo_display = serializers.SerializerMethodField()

    class Meta:
        model = EgresoCaja
        fields = ['id', 'cierre_caja', 'tipo', 'tipo_display', 'concepto', 'importe', 'fecha', 'usuario', 'usuario_nombre']
        read_only_fields = ['id', 'fecha', 'usuario', 'tienda']

    def get_usuario_nombre(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()


# ── Clientes y Cuenta Corriente ────────────────────────────────────────────────

def calcular_saldo_pendiente(cliente):
    """Saldo siempre recalculado a partir del libro de movimientos: nunca se cachea."""
    from django.db.models import Sum, Case, When, F, DecimalField
    total = cliente.movimientos_cuenta_corriente.aggregate(
        saldo=Sum(
            Case(
                When(tipo='DEBITO', then=F('monto')),
                When(tipo='CREDITO', then=-F('monto')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['saldo']
    return total or Decimal('0.00')


class ClienteSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.SlugRelatedField(
        source='tienda', slug_field='nombre', queryset=Tienda.objects.all(), write_only=True
    )
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id', 'tienda_slug', 'nombre_razon_social', 'cuit_cuil',
            'direccion', 'telefono', 'email', 'activo', 'saldo_pendiente',
            'fecha_creacion',
        ]
        read_only_fields = ['id', 'fecha_creacion']

    def get_saldo_pendiente(self, obj):
        return str(calcular_saldo_pendiente(obj))


class MovimientoCuentaCorrienteSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    tipo_display = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoCuentaCorriente
        fields = ['id', 'tipo', 'tipo_display', 'monto', 'concepto', 'venta', 'usuario', 'usuario_nombre', 'fecha']
        read_only_fields = fields

    def get_usuario_nombre(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()


# ── Carga masiva de productos (rubros con IVA por tienda) ────────────────────

class RubroSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.SlugRelatedField(
        source='tienda', slug_field='nombre', queryset=Tienda.objects.all(), write_only=True
    )

    class Meta:
        model = Rubro
        fields = ['id', 'tienda_slug', 'nombre', 'iva_porcentaje']
        read_only_fields = ['id']

    def validate_iva_porcentaje(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("El IVA debe estar entre 0 y 100%.")
        return value


class CierreCajaSerializer(serializers.ModelSerializer):
    egresos = EgresoCajaSerializer(many=True, read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    recuento_fisico_calculado = serializers.SerializerMethodField()
    total_teorico = serializers.SerializerMethodField()

    class Meta:
        model = CierreCaja
        fields = [
            'id', 'tienda', 'usuario', 'usuario_nombre', 'estado',
            'fecha_apertura', 'fecha_cierre', 'cambio_inicial',
            'billetes_20000', 'billetes_10000', 'billetes_2000', 'billetes_1000',
            'billetes_500', 'billetes_200', 'billetes_100', 'monedas',
            'total_ventas_efectivo', 'total_gastos', 'total_retiros', 'total_ingresos_extra',
            'total_egresos', 'total_recuento_fisico', 'diferencia',
            'recuento_fisico_calculado', 'total_teorico',
            'notas', 'egresos',
        ]
        read_only_fields = [
            'id', 'tienda', 'usuario', 'estado', 'fecha_apertura', 'fecha_cierre',
            'total_ventas_efectivo', 'total_gastos', 'total_retiros', 'total_ingresos_extra',
            'total_egresos', 'total_recuento_fisico', 'diferencia',
        ]

    def get_usuario_nombre(self, obj):
        return obj.usuario.username if obj.usuario else 'N/A'

    def get_recuento_fisico_calculado(self, obj):
        return str(obj.calcular_recuento_fisico())

    def get_total_teorico(self, obj):
        cambio   = obj.cambio_inicial or Decimal('0')
        ventas   = obj.total_ventas_efectivo or Decimal('0')
        gastos   = obj.total_gastos or Decimal('0')
        retiros  = obj.total_retiros or Decimal('0')
        ingresos = obj.total_ingresos_extra or Decimal('0')
        return str(cambio + ventas + ingresos - gastos - retiros)


# CRUCIAL: DEFINICIÓN DE CustomTokenObtainPairSerializer MOVIDA AL FINAL
# Esto soluciona el error de importación.
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        token['is_supervisor'] = user.is_supervisor
        token['cierre_caja_habilitado'] = user.cierre_caja_habilitado
        tienda_tiene_cierre = (
            user.__class__.objects.filter(tienda=user.tienda, cierre_caja_habilitado=True).exists()
            if user.tienda else False
        )
        token['tienda_tiene_cierre_caja'] = tienda_tiene_cierre
        if user.tienda:
            token['tienda_id'] = str(user.tienda.id)
            token['tienda_nombre'] = user.tienda.nombre
        tiendas = {str(t['id']): t for t in user.tiendas_autorizadas.values('id', 'nombre')}
        # Siempre incluir la tienda principal en la lista
        if user.tienda and str(user.tienda.id) not in tiendas:
            tiendas[str(user.tienda.id)] = {'id': str(user.tienda.id), 'nombre': user.tienda.nombre}
        # IDs de tiendas que tienen al menos un usuario con cierre_caja_habilitado
        tiendas_con_cierre = set(
            str(tid) for tid in
            user.__class__.objects.filter(
                cierre_caja_habilitado=True,
                tienda_id__in=[t['id'] for t in tiendas.values()],
            ).values_list('tienda_id', flat=True)
        )
        token['tiendas_autorizadas'] = [
            {'id': str(t['id']), 'nombre': t['nombre'], 'tiene_cierre_caja': str(t['id']) in tiendas_con_cierre}
            for t in tiendas.values()
        ]
        return token

    def validate(self, attrs):
        raw = attrs.get('username') or ''
        username = str(raw).strip()
        attrs = {**attrs, 'username': username}
        try:
            data = super().validate(attrs)
            return data
        except Exception as e:
            try:
                u = User.objects.filter(username=username).first()
                if u is None:
                    u_iexact = User.objects.filter(username__iexact=username).first()
                    total = User.objects.count()
                    if u_iexact is not None:
                        logger.warning(
                            "[LOGIN] Usuario existe con distinta capitalizacion: request=%r vs DB=%r total_users=%d",
                            username,
                            u_iexact.username,
                            total,
                            exc_info=False,
                        )
                    else:
                        db_usernames = list(User.objects.values_list('username', flat=True)[:5])
                        logger.warning(
                            "[LOGIN] Usuario no encontrado: request=%r total_users=%d usernames_en_DB=%r",
                            username,
                            total,
                            db_usernames,
                            exc_info=False,
                        )
                else:
                    logger.warning(
                        "[LOGIN] Usuario existe pero login fallo: username=%r is_active=%s tiene_tienda=%s",
                        username,
                        u.is_active,
                        u.tienda_id is not None,
                        exc_info=False,
                    )
            except Exception as log_err:
                logger.exception("[LOGIN] Error al registrar debug: %s", log_err)
            raise

class CompraSerializer(serializers.ModelSerializer):
    usuario = SimpleUserSerializer(read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Compra
        fields = '__all__'
        read_only_fields = ['usuario', 'fecha_compra']

class CompraCreateSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.CharField(write_only=True)
    fecha_compra = serializers.DateField(write_only=True)

    class Meta:
        model = Compra
        fields = ['total', 'proveedor', 'tienda_slug', 'fecha_compra']
        extra_kwargs = {
            'total': {'required': True},
            'proveedor': {'required': False},
        }

    def create(self, validated_data):
        from datetime import datetime as dt, time as dt_time
        tienda_slug = validated_data.pop('tienda_slug')
        fecha_compra_data = validated_data.pop('fecha_compra')
        tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)

        # Convertir date a datetime timezone-aware para evitar el RuntimeWarning
        fecha_compra_aware = timezone.make_aware(
            dt.combine(fecha_compra_data, dt_time(12, 0, 0))
        )

        compra_fields = {
            'total': validated_data.pop('total'),
            'proveedor': validated_data.pop('proveedor', None),
            'tienda': tienda_obj,
            'usuario': self.context['request'].user,
            'fecha_compra': fecha_compra_aware,
        }

        compra = Compra.objects.create(**compra_fields)
        return compra


class CompraStockSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = CompraStock
        fields = [
            'id', 'tienda', 'tienda_nombre', 'fecha_compra', 'proveedor',
            'monto', 'recibido', 'notas', 'usuario', 'usuario_username',
            'fecha_creacion', 'fecha_actualizacion'
        ]
        read_only_fields = ['id', 'usuario', 'tienda', 'fecha_creacion', 'fecha_actualizacion']


class CompraStockCreateSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.CharField(write_only=True)

    class Meta:
        model = CompraStock
        fields = ['tienda_slug', 'fecha_compra', 'proveedor', 'monto', 'recibido', 'notas']
        extra_kwargs = {
            'monto': {'required': True},
            'proveedor': {'required': False},
            'notas': {'required': False},
            'recibido': {'required': False},
        }

    def create(self, validated_data):
        tienda_slug = validated_data.pop('tienda_slug')
        tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        return CompraStock.objects.create(
            tienda=tienda_obj,
            **validated_data
        )


# Serializers para Cambio/Devolución (solo si los modelos existen)
if CambioDevolucion is not None and DetalleCambioDevolucion is not None:
    class DetalleCambioDevolucionSerializer(serializers.ModelSerializer):
        producto_original_nombre = serializers.CharField(source='detalle_venta_original.producto.nombre', read_only=True)
        producto_nuevo_nombre = serializers.CharField(source='producto_nuevo.nombre', read_only=True)
        
        class Meta:
            model = DetalleCambioDevolucion
            fields = [
                'id', 'accion', 'cantidad',
                'detalle_venta_original', 'producto_original_nombre',
                'producto_nuevo', 'producto_nuevo_nombre',
                'precio_unitario_devuelto', 'precio_unitario_nuevo',
                'subtotal_devuelto', 'subtotal_nuevo',
                'fecha_creacion', 'fecha_actualizacion'
            ]
            read_only_fields = ['subtotal_devuelto', 'subtotal_nuevo']

    class CambioDevolucionSerializer(serializers.ModelSerializer):
        detalles = DetalleCambioDevolucionSerializer(many=True, read_only=True)
        usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)
        tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
        venta_original_id = serializers.UUIDField(source='venta_original.id', read_only=True)
        venta_nota_credito_id = serializers.SerializerMethodField()
        venta_diferencia_pendiente_id = serializers.SerializerMethodField()
        
        def get_venta_nota_credito_id(self, obj):
            """Obtiene el ID de la venta de nota de crédito si existe"""
            if obj.venta_nota_credito:
                return str(obj.venta_nota_credito.id)
            return None
        
        def get_venta_diferencia_pendiente_id(self, obj):
            """Obtiene el ID de la venta de diferencia pendiente si existe"""
            if obj.venta_diferencia_pendiente:
                return str(obj.venta_diferencia_pendiente.id)
            return None
        
        class Meta:
            model = CambioDevolucion
            fields = [
                'id', 'venta_original', 'venta_original_id', 'tienda', 'tienda_nombre',
                'usuario', 'usuario_nombre', 'tipo', 'estado', 'motivo',
                'monto_devolucion', 'monto_nuevo', 'monto_diferencia',
                'saldo_a_favor', 'saldo_utilizado',
                'nota_credito_generada', 'venta_nota_credito', 'venta_nota_credito_id',
                'diferencia_pendiente', 'venta_diferencia_pendiente', 'venta_diferencia_pendiente_id',
                'detalles', 'fecha_creacion', 'fecha_actualizacion'
            ]
            read_only_fields = [
                'monto_devolucion', 'monto_nuevo', 'monto_diferencia', 
                'saldo_a_favor', 'saldo_utilizado', 
                'nota_credito_generada', 'diferencia_pendiente'
            ]

    class CambioDevolucionCreateSerializer(serializers.ModelSerializer):
        detalles = serializers.ListField(
            child=serializers.DictField(),
            write_only=True,
            help_text="Lista de detalles del cambio/devolución. Cada detalle debe tener: detalle_venta_original_id, accion, cantidad, producto_nuevo_id (opcional), precio_unitario_nuevo (opcional)"
        )
        tipo = serializers.CharField(required=False, allow_blank=True, default='CAMBIO')
        motivo = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
        
        class Meta:
            model = CambioDevolucion
            fields = [
                'venta_original', 'tipo', 'motivo', 'detalles'
            ]
        
        def validate(self, data):
            venta_original = data.get('venta_original')
            detalles = data.get('detalles', [])
            tipo = data.get('tipo', 'CAMBIO')
            motivo = data.get('motivo', '') or None
            
            if not venta_original:
                raise serializers.ValidationError({"venta_original": "La venta original es obligatoria."})
            
            if venta_original.anulada:
                raise serializers.ValidationError({"venta_original": "No se puede realizar un cambio/devolución sobre una venta anulada."})
            
            if not detalles:
                raise serializers.ValidationError({"detalles": "Debe especificar al menos un detalle para el cambio/devolución."})
            
            # Asegurar valores por defecto
            if not tipo:
                data['tipo'] = 'CAMBIO'
            if motivo == '':
                data['motivo'] = None
            
            # Validar cada detalle
            for detalle_data in detalles:
                accion = detalle_data.get('accion')
                detalle_venta_original_id = detalle_data.get('detalle_venta_original_id')
                cantidad = detalle_data.get('cantidad')
                
                if not accion:
                    raise serializers.ValidationError({"detalles": "Cada detalle debe tener una 'accion' (DEVOLVER, CAMBIAR, AGREGAR)."})
                
                if accion not in ['DEVOLVER', 'CAMBIAR', 'AGREGAR']:
                    raise serializers.ValidationError({"detalles": f"Acción inválida: {accion}. Debe ser DEVOLVER, CAMBIAR o AGREGAR."})
                
                if accion in ['DEVOLVER', 'CAMBIAR']:
                    if not detalle_venta_original_id:
                        raise serializers.ValidationError({"detalles": f"Para la acción {accion}, se requiere 'detalle_venta_original_id'."})
                    
                    try:
                        detalle_venta = DetalleVenta.objects.get(id=detalle_venta_original_id, venta=venta_original)
                        if detalle_venta.anulado_individualmente:
                            raise serializers.ValidationError({"detalles": f"El detalle de venta {detalle_venta_original_id} ya fue anulado."})
                        
                        if cantidad > detalle_venta.cantidad:
                            raise serializers.ValidationError({"detalles": f"La cantidad a devolver ({cantidad}) no puede ser mayor que la cantidad vendida ({detalle_venta.cantidad})."})
                    except DetalleVenta.DoesNotExist:
                        raise serializers.ValidationError({"detalles": f"Detalle de venta {detalle_venta_original_id} no encontrado."})
                
                if accion in ['CAMBIAR', 'AGREGAR']:
                    producto_nuevo_id = detalle_data.get('producto_nuevo_id')
                    precio_unitario_nuevo = detalle_data.get('precio_unitario_nuevo')
                    
                    # Validar que producto_nuevo_id no sea null o vacío
                    if not producto_nuevo_id:
                        raise serializers.ValidationError({"detalles": f"Para la acción {accion}, se requiere 'producto_nuevo_id' y no puede ser nulo."})
                    
                    try:
                        producto_nuevo = Producto.objects.get(id=producto_nuevo_id, tienda=venta_original.tienda)
                        # Para CAMBIAR también verificar stock ya que se agrega un producto nuevo
                        if accion in ['CAMBIAR', 'AGREGAR'] and producto_nuevo.stock < cantidad:
                            raise serializers.ValidationError({"detalles": f"Stock insuficiente para el producto {producto_nuevo.nombre}. Stock disponible: {producto_nuevo.stock}, solicitado: {cantidad}."})
                    except Producto.DoesNotExist:
                        raise serializers.ValidationError({"detalles": f"Producto {producto_nuevo_id} no encontrado en la tienda."})
                    
                    # Validar que precio_unitario_nuevo no sea None ni cadena vacía
                    if precio_unitario_nuevo is None or precio_unitario_nuevo == '':
                        raise serializers.ValidationError({"detalles": f"Para la acción {accion}, se requiere 'precio_unitario_nuevo' y no puede ser nulo o vacío."})
                    
                    # Convertir a Decimal si es string
                    try:
                        precio_decimal = Decimal(str(precio_unitario_nuevo))
                        if precio_decimal < 0:
                            raise serializers.ValidationError({"detalles": f"El precio unitario no puede ser negativo."})
                    except (ValueError, InvalidOperation):
                        raise serializers.ValidationError({"detalles": f"El precio_unitario_nuevo debe ser un número válido."})
            
            return data
else:
    # Si los modelos no existen, crear serializers dummy para evitar errores de importación
    class DetalleCambioDevolucionSerializer(serializers.Serializer):
        pass
    class CambioDevolucionSerializer(serializers.Serializer):
        pass
    class CambioDevolucionCreateSerializer(serializers.Serializer):
        pass


class HistorialAccionSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source='usuario.username', read_only=True, default='—')
    accion_display = serializers.CharField(source='get_accion_display', read_only=True)

    class Meta:
        model = HistorialAccion
        fields = ['id', 'accion', 'accion_display', 'detalle', 'usuario_username', 'objeto_id', 'fecha']
