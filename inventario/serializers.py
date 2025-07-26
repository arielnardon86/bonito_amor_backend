# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer as SimpleJWTOBPSerializer
from .models import Producto, Categoria, Venta, DetalleVenta, Tienda 

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.CharField(source='tienda.slug', read_only=True) 
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True) 

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tienda_slug', 'tienda_nombre')
        read_only_fields = ('id', 'tienda_slug', 'tienda_nombre')

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    is_staff = serializers.BooleanField(required=False, default=False)
    is_superuser = serializers.BooleanField(required=False, default=False)
    tienda_slug = serializers.SlugField(write_only=True, required=False, allow_null=True) 

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tienda_slug']
        extra_kwargs = {'password': {'write_only': True}} 

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        return data

    def create(self, validated_data):
        validated_data.pop('password2') 
        tienda_slug = validated_data.pop('tienda_slug', None) 

        is_staff = validated_data.pop('is_staff', False)
        is_superuser = validated_data.pop('is_superuser', False)

        user = User.objects.create_user(
            is_staff=is_staff,       
            is_superuser=is_superuser, 
            **validated_data
        )
        if tienda_slug:
            try:
                tienda = Tienda.objects.get(slug=tienda_slug)
                user.tienda = tienda 
                user.save()
            except Tienda.DoesNotExist:
                raise serializers.ValidationError({"tienda_slug": "La tienda especificada no existe."})

        return user

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'
        read_only_fields = ('slug',) 

class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Producto
        fields = '__all__'
        # CAMBIO CLAVE AQUÍ: 'tienda' es de solo lectura para la entrada (escritura)
        # Esto significa que el frontend no debe enviar el ID de la tienda.
        read_only_fields = ('fecha_creacion', 'fecha_actualizacion', 'tienda') 

    # Opcional: Validar que el precio sea un número válido si el frontend envía un string
    def validate_precio(self, value):
        try:
            return float(value)
        except (ValueError, TypeError):
            raise serializers.ValidationError("El precio debe ser un número válido.")


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_id = serializers.UUIDField(source='producto.id', read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ['id', 'producto', 'producto_nombre', 'producto_id', 'cantidad', 'precio_unitario', 'subtotal']
        read_only_fields = ['id', 'producto_nombre', 'producto_id', 'precio_unitario', 'subtotal']

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, write_only=True) 

    class Meta:
        model = Venta
        fields = ['tienda', 'metodo_pago', 'cliente_nombre', 'cliente_email', 'detalles']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        venta = Venta.objects.create(**validated_data)
        total_venta = 0

        for detalle_data in detalles_data:
            producto = detalle_data.get('producto')
            cantidad = detalle_data.get('cantidad')

            if not producto:
                raise serializers.ValidationError({"detalles": "Producto no especificado en un detalle de venta."})
            if cantidad <= 0:
                raise serializers.ValidationError({"detalles": "La cantidad debe ser mayor que cero."})
            if producto.tienda != venta.tienda:
                raise serializers.ValidationError({"detalles": f"El producto '{producto.nombre}' no pertenece a la tienda de la venta."})
            if producto.stock < cantidad:
                raise serializers.ValidationError({"detalles": f"No hay suficiente stock para el producto '{producto.nombre}'. Stock disponible: {producto.stock}"})

            precio_unitario = producto.precio
            subtotal = precio_unitario * cantidad
            
            DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal=subtotal
            )
            producto.stock -= cantidad
            producto.save()
            total_venta += subtotal
        
        venta.total = total_venta
        venta.save()
        return venta

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True) 
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Venta
        fields = '__all__'
        read_only_fields = ('fecha_venta', 'total')

class CustomTokenObtainPairSerializer(SimpleJWTOBPSerializer):
    store_slug = serializers.SlugField(write_only=True, required=False) 

    def validate(self, attrs):
        data = super().validate(attrs) 

        user = self.user 
        store_slug = attrs.get('store_slug')

        if store_slug:
            if user.tienda is None or user.tienda.slug != store_slug: 
                raise serializers.ValidationError({'detail': 'Credenciales inválidas para esta tienda.'})
        else:
            pass

        data['user_id'] = user.id
        data['username'] = user.username
        data['is_staff'] = user.is_staff
        data['is_superuser'] = user.is_superuser
        if user.tienda: 
            data['selected_store_slug'] = user.tienda.slug
            data['selected_store_name'] = user.tienda.nombre

        return data

