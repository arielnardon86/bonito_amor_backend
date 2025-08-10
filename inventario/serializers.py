# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra 
from decimal import Decimal 
from django.utils import timezone
from django.shortcuts import get_object_or_404

# Serializer para el usuario, para anidar en VentaSerializer
class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class ProductoSerializer(serializers.ModelSerializer):
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=False
    )
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
    metodo_pago_nombre = serializers.CharField(source='metodo_pago', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id', 'fecha_venta', 'total', 'anulada', 'descuento_porcentaje', 
            'metodo_pago', 'metodo_pago_nombre', 
            'usuario', 'tienda', 'tienda_nombre', 'detalles',
            'fecha_creacion', 'fecha_actualizacion'
        ]


class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(
        child=serializers.DictField(),
        write_only=True 
    )
    tienda_slug = serializers.CharField(write_only=True)
    
    class Meta:
        model = Venta
        fields = [
            'descuento_porcentaje', 'metodo_pago', 
            'tienda_slug', 'detalles'
        ]
        extra_kwargs = {
            'descuento_porcentaje': {'required': False},
        }

    def validate(self, data):
        detalles_data = data.get('detalles', [])
        tienda_slug = data.get('tienda_slug')

        if not detalles_data:
            raise serializers.ValidationError("La venta debe tener al menos un detalle de venta.")
        if not tienda_slug:
            raise serializers.ValidationError({"tienda_slug": "El slug de la tienda es obligatorio."})

        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        data['tienda'] = tienda_obj
        
        calculated_total = Decimal('0.00')
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
            
            if producto_obj.stock < cantidad:
                raise serializers.ValidationError({"detalles": f"Stock insuficiente para el producto {producto_obj.nombre}. Stock disponible: {producto_obj.stock}, solicitado: {cantidad}."})
            
            if precio_unitario < 0:
                raise serializers.ValidationError({"detalles": "El precio unitario no puede ser negativo."})

            calculated_total += precio_unitario * cantidad

        descuento_porcentaje = data.get('descuento_porcentaje', Decimal('0.00'))
        if not (Decimal('0.00') <= descuento_porcentaje <= Decimal('100.00')):
            raise serializers.ValidationError({"descuento_porcentaje": "El porcentaje de descuento debe estar entre 0 y 100."})

        data['total'] = calculated_total * (Decimal('1') - (descuento_porcentaje / Decimal('100')))
        data['fecha_venta'] = timezone.now()

        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        venta = Venta.objects.create(
            total=validated_data['total'],
            usuario=self.context['request'].user, 
            tienda=validated_data['tienda'],
            metodo_pago=validated_data['metodo_pago'],
            descuento_porcentaje=validated_data.get('descuento_porcentaje', Decimal('0.00')),
            fecha_venta=validated_data['fecha_venta'],
        )
        
        for detalle_data in detalles_data:
            producto_id = detalle_data['producto'] 
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']

            producto_obj = Producto.objects.get(id=producto_id)
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
    tienda_slug = serializers.CharField(write_only=True)

    class Meta:
        model = Compra
        fields = ['total', 'proveedor', 'tienda_slug']
        extra_kwargs = {
            'total': {'required': True},
            'proveedor': {'required': False},
        }

    def create(self, validated_data):
        tienda_slug = validated_data.pop('tienda_slug')
        tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        
        compra_fields = {
            'total': validated_data.pop('total'),
            'proveedor': validated_data.pop('proveedor', None),
            'tienda': tienda_obj,
            'usuario': self.context['request'].user
        }
        
        compra = Compra.objects.create(**compra_fields)
        return compra