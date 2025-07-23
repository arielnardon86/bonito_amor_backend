# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from django.db import transaction
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda # Importa Tienda
from django.contrib.auth import get_user_model 

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser') 
        read_only_fields = ('id',) 

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

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

# --- NUEVO SERIALIZADOR: TiendaSerializer ---
class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = ['id', 'nombre', 'slug', 'descripcion']

class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True) 
    # Añadir el nombre de la tienda para visualización
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True) # <--- CAMBIO CLAVE AQUÍ
    
    class Meta:
        model = Producto
        fields = '__all__' # Asegúrate de que 'tienda' también esté incluido aquí, '__all__' lo hará


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all()) 

    class Meta:
        model = DetalleVenta
        fields = ['id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario_venta']
        read_only_fields = ['id', 'producto_nombre'] 

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    usuario = serializers.HiddenField(default=serializers.CurrentUserDefault()) 

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total_venta', 'usuario', 'detalles', 'metodo_pago']
        read_only_fields = ['id', 'fecha_venta', 'total_venta']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        with transaction.atomic():
            venta = Venta.objects.create(**validated_data) 

            total_venta = 0
            for detalle_data in detalles_data:
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
    usuario = UserSerializer(read_only=True) 
    # Añadir el nombre de la tienda para visualización
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True) # <--- CAMBIO CLAVE AQUÍ

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total_venta', 'detalles', 'usuario', 'anulada', 'metodo_pago', 'tienda_nombre'] # <--- CAMBIO CLÍAVE AQUÍ
        read_only_fields = ['id', 'fecha_venta', 'total_venta', 'usuario', 'anulada', 'metodo_pago', 'tienda_nombre'] 
