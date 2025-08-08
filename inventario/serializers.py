# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra 
from decimal import Decimal 
from django.utils import timezone

# Serializer para el usuario, para anidar en VentaSerializer
class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = '__all__'

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=False, 
        allow_null=True 
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tienda']
        read_only_fields = ['is_staff', 'is_superuser']

class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True) 
    
    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['subtotal']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id', 'fecha_venta', 'total', 'anulada', 'descuento_porcentaje', 
            'monto_descontado', 'metodo_pago', 'metodo_pago_nombre', 
            'usuario', 'tienda', 'tienda_nombre', 'detalles', 'observaciones',
            'fecha_creacion', 'fecha_actualizacion'
        ]

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    
    class Meta:
        model = Venta
        fields = [
            'fecha_venta', 'total', 'descuento_porcentaje', 'metodo_pago', 
            'tienda', 'detalles', 'observaciones', 'monto_descontado'
        ]
        extra_kwargs = {
            'total': {'required': False},
            'fecha_venta': {'required': False},
            'descuento_porcentaje': {'required': False}, # Asegura que este campo no sea requerido
            'observaciones': {'required': False}, # Asegura que este campo no sea requerido
            'monto_descontado': {'required': False}, # Asegura que este campo no sea requerido
        }

    def validate(self, data):
        detalles_data = data.get('detalles', [])
        if not detalles_data:
            raise serializers.ValidationError("La venta debe tener al menos un detalle de venta.")

        calculated_total = Decimal('0.00')
        for detalle_data in detalles_data:
            producto_id = detalle_data.get('producto')
            cantidad = detalle_data.get('cantidad')
            precio_unitario = detalle_data.get('precio_unitario')

            if not producto_id:
                raise serializers.ValidationError({"detalles": "Cada detalle debe tener un producto."})
            if cantidad is None or cantidad <= 0:
                raise serializers.ValidationError({"detalles": "La cantidad debe ser un número positivo."})
            if precio_unitario is None or precio_unitario < 0:
                raise serializers.ValidationError({"detalles": "El precio unitario debe ser un número no negativo."})

            try:
                producto_obj = Producto.objects.get(id=producto_id)
            except Producto.DoesNotExist:
                raise serializers.ValidationError({"detalles": f"Producto con ID {producto_id} no encontrado."})
            
            if producto_obj.stock < cantidad:
                raise serializers.ValidationError({"detalles": f"Stock insuficiente para el producto {producto_obj.nombre}. Stock disponible: {producto_obj.stock}, solicitado: {cantidad}."})

            calculated_total += precio_unitario * cantidad

        descuento_porcentaje = data.get('descuento_porcentaje', Decimal('0.00'))
        if not (Decimal('0.00') <= descuento_porcentaje <= Decimal('100.00')):
            raise serializers.ValidationError({"descuento_porcentaje": "El porcentaje de descuento debe estar entre 0 y 100."})

        data['total'] = calculated_total * (Decimal('1') - (descuento_porcentaje / Decimal('100')))
        data['monto_descontado'] = calculated_total * (descuento_porcentaje / Decimal('100'))
        
        if 'fecha_venta' not in data or not data['fecha_venta']:
            data['fecha_venta'] = timezone.now()

        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        venta = Venta.objects.create(
            total=validated_data.pop('total'),
            usuario=self.context['request'].user, 
            tienda=validated_data.pop('tienda'),
            metodo_pago=validated_data.pop('metodo_pago'),
            descuento_porcentaje=validated_data.pop('descuento_porcentaje', Decimal('0.00')), # Uso de .pop con valor por defecto
            monto_descontado=validated_data.pop('monto_descontado', Decimal('0.00')), # Uso de .pop con valor por defecto
            fecha_venta=validated_data.pop('fecha_venta'),
            observaciones=validated_data.pop('observaciones', ''), # Uso de .pop con valor por defecto
        )
        
        for detalle_data in detalles_data:
            producto_id = detalle_data['producto'] 
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']

            try:
                producto_obj = Producto.objects.get(id=producto_id)
            except Producto.DoesNotExist:
                raise serializers.ValidationError({"detalles": f"Producto con ID {producto_id} no encontrado."})

            subtotal = precio_unitario * cantidad
            DetalleVenta.objects.create(venta=venta, subtotal=subtotal, producto=producto_obj, cantidad=cantidad, precio_unitario=precio_unitario)

            producto_obj.stock -= cantidad
            producto_obj.save()

        return venta

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        if user.tienda:
            token['tienda_id'] = str(user.tienda.id)
            token['tienda_nombre'] = user.tienda.nombre
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        return data

class CompraSerializer(serializers.ModelSerializer):
    usuario = SimpleUserSerializer(read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Compra
        fields = '__all__'
        read_only_fields = ['usuario', 'fecha_compra']

class CompraCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Compra
        fields = ['total', 'proveedor', 'tienda']
        extra_kwargs = {
            'total': {'required': True},
            'tienda': {'required': True},
        }
    
    def validate_tienda(self, value):
        # Esta validación es importante para evitar errores
        if not Tienda.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("La tienda especificada no existe.")
        return value

    def create(self, validated_data):
        compra = Compra.objects.create(**validated_data)
        return compra
