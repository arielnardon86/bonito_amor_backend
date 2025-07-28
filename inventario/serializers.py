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

    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'precio_unitario_venta', 'subtotal']
        read_only_fields = ['subtotal', 'venta']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True) 
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    # --- CAMBIO AQUÍ: No necesitas definir metodo_pago explícitamente con source si ya es CharField en el modelo ---
    # Solo asegúrate de que esté en 'fields'
    # metodo_pago = serializers.CharField(source='metodo_pago.nombre', read_only=True) # <-- Esta línea debe eliminarse o comentarse

    class Meta:
        model = Venta
        # Asegúrate de que 'metodo_pago' y 'anulada' estén en la lista de campos
        fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'detalles', 'anulada']
        read_only_fields = ['id', 'fecha_venta', 'total', 'detalles', 'anulada'] 

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    tienda_slug = serializers.CharField(write_only=True, required=True)
    metodo_pago_nombre = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Venta
        fields = ['tienda_slug', 'metodo_pago_nombre', 'detalles']
        read_only_fields = ['total', 'usuario']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        tienda_slug = validated_data.pop('tienda_slug')
        metodo_pago_nombre = validated_data.pop('metodo_pago_nombre')

        # Resolver la tienda a partir del slug
        try:
            tienda = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        # Resolver el método de pago a partir del nombre
        try:
            metodo_pago_obj = MetodoPago.objects.get(nombre=metodo_pago_nombre)
        except MetodoPago.DoesNotExist:
            raise serializers.ValidationError({"metodo_pago_nombre": "Método de pago no encontrado."})

        # Asignar la tienda y el método de pago resueltos al validated_data
        validated_data['tienda'] = tienda
        # Asignar el NOMBRE del método de pago, no el objeto, porque es un CharField
        validated_data['metodo_pago'] = metodo_pago_obj.nombre 

        # Obtener el usuario de la request (pasado desde la vista)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['usuario'] = request.user
        else:
            raise serializers.ValidationError({"usuario": "Usuario no autenticado para realizar la venta."})


        venta = Venta.objects.create(**validated_data)
        total_venta = Decimal('0.00')

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
            total_venta += subtotal
            
            producto_obj.stock -= cantidad
            producto_obj.save()
        
        venta.total = total_venta
        venta.save()
        return venta

# Serializer para el token JWT personalizado
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
