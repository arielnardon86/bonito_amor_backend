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
    # CAMBIO CLAVE AQUÍ: Serializar la tienda por su nombre
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', # Indica que queremos el campo 'nombre' de la Tienda
        queryset=Tienda.objects.all(), # Necesario para la escritura (si se permite)
        required=False, # El campo puede ser nulo
        allow_null=True # Permite que el campo sea nulo
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
    # CAMBIO: Incluir el campo 'anulado_individualmente'
    anulado_individualmente = serializers.BooleanField(read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'precio_unitario_venta', 'subtotal', 'anulado_individualmente']
        read_only_fields = ['subtotal', 'venta', 'anulado_individualmente'] # También read-only

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    # Incluir descuento_porcentaje en el serializer de lectura
    descuento_porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)


    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'detalles', 'anulada', 'descuento_porcentaje']
        read_only_fields = ['id', 'fecha_venta', 'total', 'detalles', 'anulada', 'descuento_porcentaje']

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    # CAMBIO CLAVE AQUÍ: Volvemos a usar tienda_nombre para que el frontend envíe el nombre
    tienda_nombre = serializers.CharField(write_only=True, required=True) 
    metodo_pago_nombre = serializers.CharField(write_only=True, required=True)
    descuento_porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal('0.00'))
    total = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)


    class Meta:
        model = Venta
        # Ahora 'tienda_nombre' está en los campos del serializer
        fields = ['tienda_nombre', 'metodo_pago_nombre', 'detalles', 'descuento_porcentaje', 'total']
        read_only_fields = ['usuario'] # El usuario se asigna automáticamente en el backend

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        # Pop tienda_nombre y buscar la instancia de Tienda manualmente
        tienda_nombre = validated_data.pop('tienda_nombre') 
        metodo_pago_nombre = validated_data.pop('metodo_pago_nombre')
        descuento_porcentaje = validated_data.pop('descuento_porcentaje', Decimal('0.00')) 
        total_venta_final = validated_data.pop('total') 

        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_nombre) # Búsqueda manual
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_nombre": "Tienda no encontrada."})

        try:
            metodo_pago_obj = MetodoPago.objects.get(nombre=metodo_pago_nombre)
        except MetodoPago.DoesNotExist:
            raise serializers.ValidationError({"metodo_pago_nombre": "Método de pago no encontrado."})

        validated_data['metodo_pago'] = metodo_pago_obj.nombre
        validated_data['tienda'] = tienda_obj # Asignar el objeto Tienda resuelto

        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['usuario'] = request.user
        else:
            raise serializers.ValidationError({"usuario": "Usuario no autenticado para realizar la venta."})

        # Crear la venta principal con el descuento y el total final
        venta = Venta.objects.create(
            total=total_venta_final, 
            descuento_porcentaje=descuento_porcentaje, 
            **validated_data
        )
        
        for detalle_data in detalles_data:
            producto = detalle_data['producto']
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']

            if isinstance(producto, str):
                try:
                    producto_obj = Producto.objects.get(id=producto)
                except Producto.DoesNotExist:
                    raise serializers.ValidationError({"detalles": f"Producto con ID {producto} no encontrado."})
            else:
                producto_obj = producto

            subtotal = precio_unitario * cantidad
            DetalleVenta.objects.create(venta=venta, subtotal=subtotal, producto=producto_obj, cantidad=cantidad, precio_unitario=precio_unitario)

            producto_obj.stock -= cantidad
            producto_obj.save()

        venta.save() 
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
