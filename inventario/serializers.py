# inventario/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Producto, Categoria, Venta, DetalleVenta
from django.contrib.auth import get_user_model # Importar para obtener el modelo de usuario activo

User = get_user_model() # Obtiene el modelo de usuario configurado en settings.py

# Serializador para el modelo User (para mostrar información del usuario logueado y en listas)
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser') 
        read_only_fields = ('id',) 

# Serializador para creación de usuarios
class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    is_staff = serializers.BooleanField(required=False, default=False)
    is_superuser = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name', 'is_staff', 'is_superuser']
        extra_kwargs = {'password': {'write_only': True}} 

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Ambas contraseñas deben coincidir."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2') 
        
        is_staff = validated_data.pop('is_staff', False)
        is_superuser = validated_data.pop('is_superuser', False)

        user = User.objects.create_user(
            is_staff=is_staff,       
            is_superuser=is_superuser, 
            **validated_data
        )
        return user

# Serializador para el modelo Categoria (si lo necesitas y el modelo existe)
class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

# Serializador para el modelo Producto
class ProductoSerializer(serializers.ModelSerializer):
    # Si 'categoria' es una ForeignKey, puedes añadir esto para mostrar el nombre
    # Asegúrate que el campo 'categoria' en tu modelo Producto es una ForeignKey a Categoria
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True) 
    
    class Meta:
        model = Producto
        # Asegúrate de incluir 'categoria_nombre' aquí si lo usas
        fields = '__all__' 

class DetalleVentaSerializer(serializers.ModelSerializer):
    # Campo para devolver el nombre del producto en la respuesta
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    
    # Campo para aceptar el ID del producto en la entrada (POST/PUT)
    # Aquí, 'producto' es el campo de tu modelo DetalleVenta
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all()) 

    class Meta:
        model = DetalleVenta
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario_venta']
        # 'id' y 'producto_nombre' son de solo lectura en la salida
        read_only_fields = ['id', 'producto_nombre'] 

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    # Campo oculto que automáticamente asigna el usuario actual a la venta
    # Esto funciona si la vista tiene configurada la autenticación (ej. IsAuthenticated)
    usuario = serializers.HiddenField(default=serializers.CurrentUserDefault()) 

    class Meta:
        model = Venta
        # Asegúrate de incluir 'usuario' en los campos
        fields = ['id', 'fecha_venta', 'total_venta', 'usuario', 'detalles']
        # 'fecha_venta' y 'total_venta' se calculan en el backend
        read_only_fields = ['id', 'fecha_venta', 'total_venta']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        # 'usuario' ya está en validated_data gracias a HiddenField
        
        with transaction.atomic():
            venta = Venta.objects.create(**validated_data) # El usuario ya está aquí

            total_venta = 0
            for detalle_data in detalles_data:
                # El PrimaryKeyRelatedField ya resolvió 'producto' al objeto Producto
                producto = detalle_data['producto'] 
                cantidad = detalle_data['cantidad']
                precio_unitario_venta = detalle_data['precio_unitario_venta']

                if producto.stock < cantidad:
                    raise serializers.ValidationError(f"No hay suficiente stock para {producto.nombre}. Disponible: {producto.stock}")

                DetalleVenta.objects.create(venta=venta, **detalle_data)
                
                producto.stock -= cantidad
                producto.save()

                total_venta += cantidad * precio_unitario_venta
            
            venta.total_venta = total_venta
            venta.save()

        return venta

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    # Usa el UserSerializer para obtener todos los detalles del usuario
    usuario = UserSerializer(read_only=True) 

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total_venta', 'detalles', 'usuario']
        read_only_fields = ['id', 'fecha_venta', 'total_venta', 'usuario'] # 'usuario' ahora es read_only