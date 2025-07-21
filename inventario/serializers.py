# inventario/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Producto, Categoria, Venta, DetalleVenta
from django.contrib.auth import get_user_model # Importar para obtener el modelo de usuario activo

User = get_user_model() # Obtiene el modelo de usuario configurado en settings.py

# Serializer for the User model (to display logged-in user info and in lists)
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser') 
        read_only_fields = ('id',) 

# Serializer for user creation
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
            raise serializers.ValidationError({"password": "Both passwords must match."})
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

# Serializer for the Categoria model (if needed and the model exists)
class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

# Serializer for the Producto model
class ProductoSerializer(serializers.ModelSerializer):
    # If 'categoria' is a ForeignKey, you can add this to display the name
    # Make sure the 'categoria' field in your Producto model is a ForeignKey to Categoria
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True) 
    
    class Meta:
        model = Producto
        # Make sure to include 'categoria_nombre' here if you use it
        fields = '__all__' 

class DetalleVentaSerializer(serializers.ModelSerializer):
    # Field to return the product name in the response
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    
    # Field to accept the product ID on input (POST/PUT)
    # Here, 'producto' is the field in your DetalleVenta model
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all()) 

    class Meta:
        model = DetalleVenta
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario_venta']
        # 'id' and 'producto_nombre' are read-only in the output
        read_only_fields = ['id', 'producto_nombre'] 

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    # Hidden field that automatically assigns the current user to the sale
    # This works if the view has authentication configured (e.g., IsAuthenticated)
    usuario = serializers.HiddenField(default=serializers.CurrentUserDefault()) 

    class Meta:
        model = Venta
        # Make sure to include 'usuario' in the fields
        fields = ['id', 'fecha_venta', 'total_venta', 'usuario', 'detalles', 'metodo_pago'] # Added 'metodo_pago'
        # 'fecha_venta' and 'total_venta' are calculated in the backend
        read_only_fields = ['id', 'fecha_venta', 'total_venta']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        # 'usuario' is already in validated_data thanks to HiddenField
        
        with transaction.atomic():
            venta = Venta.objects.create(**validated_data) # The user is already here

            total_venta = 0
            for detalle_data in detalles_data:
                # PrimaryKeyRelatedField already resolved 'producto' to the Producto object
                producto = detalle_data['producto'] 
                cantidad = detalle_data['cantidad']
                precio_unitario_venta = detalle_data['precio_unitario_venta']

                if producto.stock < cantidad:
                    raise serializers.ValidationError(f"Not enough stock for {producto.nombre}. Available: {producto.stock}")

                DetalleVenta.objects.create(venta=venta, **detalle_data)
                
                producto.stock -= cantidad
                producto.save()

                total_venta += cantidad * precio_unitario_venta
            
            venta.total_venta = total_venta
            venta.save()

        return venta

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    # Use UserSerializer to get all user details
    usuario = UserSerializer(read_only=True) 

    class Meta:
        model = Venta
        # Added 'metodo_pago' to the fields list
        fields = ['id', 'fecha_venta', 'total_venta', 'detalles', 'usuario', 'anulada', 'metodo_pago'] # Added 'anulada' and 'metodo_pago'
        read_only_fields = ['id', 'fecha_venta', 'total_venta', 'usuario', 'anulada', 'metodo_pago'] # 'usuario', 'anulada', 'metodo_pago' now read_only
