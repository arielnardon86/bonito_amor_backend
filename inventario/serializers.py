# BONITO_AMOR/backend/inventario/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda # Importar Tienda

User = get_user_model()

# --- Serializador para el Modelo de Usuario ---
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser']
        read_only_fields = ['id']

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}) # Para confirmación

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'password', 'password2']
        extra_kwargs = {
            'password': {'write_only': True},
            'is_staff': {'required': False},
            'is_superuser': {'required': False},
        }

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Ambas contraseñas deben coincidir."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2') # Eliminar password2 antes de crear el usuario
        user = User.objects.create_user(**validated_data)
        return user

    def update(self, instance, validated_data):
        # Manejar la actualización de la contraseña por separado
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
            validated_data.pop('password2', None) # Asegurarse de quitar password2 si se envía

        return super().update(instance, validated_data)


# --- Serializador para el Modelo Categoria ---
class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

# --- Serializador para el Modelo Tienda ---
class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'
        read_only_fields = ['slug'] # El slug se genera automáticamente

# --- Serializador para el Modelo Producto ---
class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True) # Añadir nombre de la tienda

    class Meta:
        model = Producto
        fields = [
            'id', 'nombre', 'descripcion', 'codigo_barras', 'precio_compra',
            'precio_venta', 'stock', 'talle', 'categoria', 'categoria_nombre',
            'tienda', 'tienda_nombre' # Incluir tienda y su nombre
        ]
        read_only_fields = ['id', 'codigo_barras', 'categoria_nombre', 'tienda_nombre']

# --- Serializador para DetalleVenta (anidado en Venta) ---
class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    # Asegúrate de que el producto esté disponible para la creación
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())

    class Meta:
        model = DetalleVenta
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario_venta']
        read_only_fields = ['id', 'producto_nombre', 'precio_unitario_venta'] # precio_unitario_venta se establece en el save del modelo

# --- Serializador para la creación de Venta (maneja detalles anidados) ---
class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, write_only=True) # 'write_only' para que no se muestre en GET

    class Meta:
        model = Venta
        fields = ['id', 'usuario', 'fecha_venta', 'total_venta', 'anulada', 'metodo_pago', 'tienda', 'detalles'] # Añadir 'tienda'
        read_only_fields = ['id', 'fecha_venta', 'total_venta', 'anulada']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        # El usuario se asigna automáticamente al request.user en la vista, si no se envía
        # Si el usuario no se envía en validated_data, se asigna automáticamente en la vista.
        # Aquí, si el usuario no está en validated_data, se puede asignar desde request.user si es necesario.
        # validated_data['usuario'] = self.context['request'].user # Esto es si quieres forzar el usuario autenticado

        # Asegúrate de que la tienda se establezca si no viene en los datos validados
        # Esto es crucial si la tienda se envía desde el frontend o se determina de otra forma
        # Si la tienda no se envía en el payload, y necesitas que se asigne automáticamente,
        # puedes obtenerla del request.query_params en la vista y pasarla al serializer context.
        # Por ahora, asumimos que 'tienda' puede venir en validated_data.

        venta = Venta.objects.create(**validated_data)
        total_venta = 0
        for detalle_data in detalles_data:
            producto = detalle_data['producto']
            cantidad = detalle_data['cantidad']
            
            if producto.stock < cantidad:
                raise serializers.ValidationError(f"No hay suficiente stock para {producto.nombre}. Disponible: {producto.stock}")

            # Descontar stock
            producto.stock -= cantidad
            producto.save()

            # Crear DetalleVenta, el precio_unitario_venta se establecerá en el save del modelo
            DetalleVenta.objects.create(venta=venta, **detalle_data)
            total_venta += cantidad * producto.precio_venta # Usar precio_venta del producto para el total

        venta.total_venta = total_venta
        venta.save()
        return venta

# --- Serializador para la representación de Venta (incluye detalles anidados para GET) ---
class VentaSerializer(serializers.ModelSerializer):
    usuario = UserSerializer(read_only=True) # Mostrar detalles del usuario
    detalles = DetalleVentaSerializer(many=True, read_only=True) # Mostrar detalles de la venta
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True) # Añadir nombre de la tienda

    class Meta:
        model = Venta
        fields = ['id', 'usuario', 'fecha_venta', 'total_venta', 'anulada', 'metodo_pago', 'tienda', 'tienda_nombre', 'detalles']
        read_only_fields = ['id', 'usuario', 'fecha_venta', 'total_venta', 'anulada', 'detalles', 'tienda_nombre']
