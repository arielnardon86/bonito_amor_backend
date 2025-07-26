# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda

User = get_user_model()

# Custom Token Serializer para incluir datos del usuario
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Añadir información adicional al token
        token['username'] = user.username
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        if user.tienda:
            token['tienda_id'] = str(user.tienda.id)
            token['tienda_nombre'] = user.tienda.nombre
        else:
            token['tienda_id'] = None
            token['tienda_nombre'] = None
        return token

# Serializador para el modelo de usuario
class UserSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    tienda_id = serializers.UUIDField(source='tienda.id', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_staff', 'is_superuser', 'tienda', 'tienda_nombre', 'tienda_id', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['id', 'is_staff', 'is_superuser', 'fecha_creacion', 'fecha_actualizacion']

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'is_staff', 'tienda']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

# Serializador para el modelo de Tienda
class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'
        read_only_fields = ['id', 'fecha_creacion', 'fecha_actualizacion']

# Serializador para el modelo de Categoría (Si aún lo usas)
# Si eliminaste el modelo Categoria, puedes eliminar este serializador también
class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'
        read_only_fields = ['id', 'fecha_creacion', 'fecha_actualizacion']

# Serializador para el modelo de Producto
class ProductoSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    
    class Meta:
        model = Producto
        # CAMBIO CLAVE AQUÍ: Asegúrate de que 'codigo_barras' esté en la lista de fields
        fields = ['id', 'nombre', 'descripcion', 'precio', 'stock', 'tienda', 'tienda_nombre', 'codigo_barras', 'fecha_creacion', 'fecha_actualizacion']
        # 'codigo_barras' debe ser read_only_fields porque se genera automáticamente
        read_only_fields = ['id', 'tienda_nombre', 'codigo_barras', 'fecha_creacion', 'fecha_actualizacion'] 

# Serializador para el modelo de DetalleVenta
class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    
    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'subtotal', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['id', 'fecha_creacion', 'fecha_actualizacion']

# Serializador para el modelo de Venta (Lectura)
class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total', 'metodo_pago', 'tienda', 'tienda_nombre', 'detalles', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['id', 'fecha_venta', 'total', 'tienda_nombre', 'fecha_creacion', 'fecha_actualizacion']

# Serializador para la creación de Venta (Escritura)
class VentaCreateSerializer(serializers.ModelSerializer):
    productos = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=True,
        help_text="Lista de productos para la venta. Cada elemento debe ser un diccionario con 'producto_id' y 'cantidad'."
    )

    class Meta:
        model = Venta
        fields = ['id', 'metodo_pago', 'productos', 'tienda']
        read_only_fields = ['id', 'total'] # 'total' se calcula en el create

    def create(self, validated_data):
        productos_data = validated_data.pop('productos')
        tienda = validated_data.pop('tienda', None) # Obtener la tienda si se proporciona

        # Si la tienda no se proporcionó en los datos, intentar obtenerla del usuario
        if not tienda and self.context['request'].user.tienda:
            tienda = self.context['request'].user.tienda
        elif not tienda:
            raise serializers.ValidationError({"tienda": "La tienda es requerida para crear una venta."})

        venta = Venta.objects.create(tienda=tienda, **validated_data)
        total_venta = 0

        for item_data in productos_data:
            try:
                producto = Producto.objects.get(id=item_data['producto_id'])
            except Producto.DoesNotExist:
                raise serializers.ValidationError(f"Producto con ID {item_data['producto_id']} no encontrado.")

            cantidad = item_data.get('cantidad', 1)
            if cantidad <= 0:
                raise serializers.ValidationError(f"La cantidad para el producto {producto.nombre} debe ser mayor que cero.")

            if producto.stock < cantidad:
                raise serializers.ValidationError(f"No hay suficiente stock para el producto: {producto.nombre}. Stock disponible: {producto.stock}")

            subtotal = producto.precio * cantidad
            DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                subtotal=subtotal
            )
            producto.stock -= cantidad
            producto.save()
            total_venta += subtotal

        venta.total = total_venta
        venta.save()
        return venta
