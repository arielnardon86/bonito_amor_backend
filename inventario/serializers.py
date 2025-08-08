# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra 
from decimal import Decimal 
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'

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
class UserSerializer(serializers.ModelSerializer):
    tiendas_acceso = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tiendas_acceso']
        read_only_fields = ['is_staff', 'is_superuser']

    def get_tiendas_acceso(self, obj):
        if obj.is_superuser:
            tiendas = Tienda.objects.all()
        else:
            tiendas = Tienda.objects.filter(id=obj.tienda_id) if obj.tienda else Tienda.objects.none()
        
        return TiendaSerializer(tiendas, many=True).data


class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'


class VentaCreateSerializer(serializers.ModelSerializer):
    productos = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()
        ),
        write_only=True
    )
    tienda_slug = serializers.CharField(write_only=True)
    metodo_pago_nombre = serializers.CharField(write_only=True)
    # Definir el campo 'descuento' explícitamente para evitar el error
    descuento = serializers.DecimalField(max_digits=5, decimal_places=2, write_only=True, default=0.0)

    class Meta:
        model = Venta
        fields = ['id', 'productos', 'tienda_slug', 'descuento', 'metodo_pago_nombre']
        read_only_fields = ['monto_total', 'monto_final']

    def validate(self, data):
        # Validation logic...
        return data

    def create(self, validated_data):
        # Creation logic...
        return Venta


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_precio = serializers.DecimalField(source='producto.precio', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'producto_precio', 'cantidad', 'precio_unitario', 'subtotal']
class VentaSerializer(serializers.ModelSerializer):
    usuario = serializers.ReadOnlyField(source='usuario.username')
    tienda = serializers.ReadOnlyField(source='tienda.nombre')
    metodo_pago = serializers.ReadOnlyField(source='metodo_pago.nombre')
    detalles = DetalleVentaSerializer(many=True, read_only=True, source='detalleventa_set')
    
    class Meta:
        model = Venta
        fields = ['id', 'fecha', 'monto_total', 'monto_final', 'descuento', 'usuario', 'tienda', 'metodo_pago', 'detalles']

class CompraSerializer(serializers.ModelSerializer):
    usuario = SimpleUserSerializer(read_only=True)
    tienda = TiendaSerializer(read_only=True)

    class Meta:
        model = Compra
        fields = ['id', 'fecha_compra', 'total', 'proveedor', 'usuario', 'tienda']


class CompraCreateSerializer(serializers.Serializer):
    tienda_slug = serializers.CharField(write_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    proveedor = serializers.CharField(required=False, allow_blank=True)
    
    def create(self, validated_data):
        tienda_slug = validated_data.pop('tienda_slug')
        
        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        compra = Compra.objects.create(
            tienda=tienda_obj,
            total=validated_data['total'],
            proveedor=validated_data.get('proveedor', ''),
            usuario=self.context['request'].user, 
        )
        return compra


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        
        return token