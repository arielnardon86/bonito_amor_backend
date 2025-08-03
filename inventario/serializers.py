# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago
from decimal import Decimal # Importar Decimal para cálculos precisos

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
    precio_unitario_venta = serializers.DecimalField(source='precio_unitario', max_digits=10, decimal_places=2, read_only=True)
    anulado_individualmente = serializers.BooleanField(read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'precio_unitario_venta', 'subtotal', 'anulado_individualmente']
        read_only_fields = ['subtotal', 'venta', 'anulado_individualmente']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    descuento_porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    tienda = TiendaSerializer(read_only=True) 

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'detalles', 'anulada', 'descuento_porcentaje']
        read_only_fields = ['id', 'fecha_venta', 'total', 'detalles', 'anulada', 'descuento_porcentaje']

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    tienda = serializers.SlugRelatedField(
        slug_field='nombre',  
        queryset=Tienda.objects.all(),
        write_only=True,
        required=True 
    )
    metodo_pago_nombre = serializers.CharField(write_only=True, required=True)
    descuento_porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal('0.00'))
    total = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)


    class Meta:
        model = Venta
        fields = ['tienda', 'metodo_pago_nombre', 'detalles', 'descuento_porcentaje', 'total']
        read_only_fields = ['usuario'] 

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        tienda_obj = validated_data.pop('tienda') # Ya es el objeto Tienda resuelto por SlugRelatedField
        metodo_pago_nombre = validated_data.pop('metodo_pago_nombre')
        descuento_porcentaje = validated_data.pop('descuento_porcentaje', Decimal('0.00')) 
        total_venta_final = validated_data.pop('total') 

        try:
            metodo_pago_obj = MetodoPago.objects.get(nombre=metodo_pago_nombre)
        except MetodoPago.DoesNotExist:
            raise serializers.ValidationError({"metodo_pago_nombre": "Método de pago no encontrado."})

        request = self.context.get('request')
        if request and request.user.is_authenticated:
            usuario_obj = request.user
        else:
            raise serializers.ValidationError({"usuario": "Usuario no autenticado para realizar la venta."})

        # Construir explícitamente los argumentos para la creación de la Venta
        venta_args = {
            'tienda': tienda_obj,  # Objeto Tienda resuelto
            'metodo_pago': metodo_pago_obj.nombre,
            'usuario': usuario_obj,
            'total': total_venta_final,
            'descuento_porcentaje': descuento_porcentaje,
            # Incluir cualquier otro campo que pueda estar en validated_data y no haya sido pop'd
            **validated_data 
        }

        # Crear la venta principal
        venta = Venta.objects.create(**venta_args)
        
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

        # No es estrictamente necesario llamar a venta.save() aquí si todos los campos se asignaron en create()
        # pero no hace daño y puede ser útil si se añaden más lógicas de negocio después.
        # venta.save() 
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
