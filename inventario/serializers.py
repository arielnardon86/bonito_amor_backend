# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate # Aunque no se usa directamente en este snippet, se mantiene si es necesario en otras partes
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import (
    User, Tienda, Categoria, Producto, Venta, DetalleVenta,
    MetodoPago
)
from decimal import Decimal # Importar Decimal para cálculos precisos


class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'
        read_only_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


class UserSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_staff', 'is_superuser', 'tienda', 'tienda_nombre',
            'fecha_creacion', 'fecha_actualizacion'
        )
        read_only_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'tienda': {'required': False, 'allow_null': True}
        }

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'
        read_only_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Producto
        fields = (
            'id', 'nombre', 'descripcion', 'precio', 'stock', 'codigo_barras',
            'talle', 'categoria', 'categoria_nombre', 'tienda', 'tienda_nombre',
            'fecha_creacion', 'fecha_actualizacion'
        )
        read_only_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'
        read_only_fields = ('id', 'fecha_creacion', 'fecha_actualizacion')


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    precio_unitario_venta = serializers.DecimalField(source='precio_unitario', max_digits=10, decimal_places=2, read_only=True)
    anulado_individualmente = serializers.BooleanField(read_only=True) # Asegurarse de que el campo esté aquí

    class Meta:
        model = DetalleVenta
        fields = [
            'id', 'venta', 'producto', 'producto_nombre', 'cantidad',
            'precio_unitario', 'precio_unitario_venta', 'subtotal',
            'anulado_individualmente'
        ]
        read_only_fields = [
            'subtotal', 'venta', 'id', 'producto_nombre', 'precio_unitario',
            'precio_unitario_venta', 'anulado_individualmente'
        ]


class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = UserSerializer(read_only=True) # Usar el UserSerializer completo para más detalles
    tienda = TiendaSerializer(read_only=True) # Para mostrar detalles de la tienda
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'anulada', 'detalles']
        read_only_fields = ['id', 'fecha_venta', 'total', 'detalles', 'anulada']


class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=True
    )
    tienda_slug = serializers.CharField(write_only=True, required=False) # Hacerlo no requerido aquí
    metodo_pago_nombre = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Venta
        fields = ['metodo_pago_nombre', 'detalles', 'tienda_slug']
        read_only_fields = ['total', 'usuario', 'anulada']

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        metodo_pago_nombre = validated_data.pop('metodo_pago_nombre')
        tienda_slug = validated_data.pop('tienda_slug', None) # Obtenerlo, puede ser None

        try:
            metodo_pago_obj = MetodoPago.objects.get(nombre=metodo_pago_nombre)
        except MetodoPago.DoesNotExist:
            raise serializers.ValidationError({"metodo_pago_nombre": "Método de pago no encontrado."})

        request = self.context.get('request')
        usuario = request.user if request and request.user.is_authenticated else None

        if not usuario:
            raise serializers.ValidationError({"usuario": "Usuario no autenticado para realizar la venta."})

        # Si el usuario tiene una tienda asignada, usar esa. Si no, usar la del slug si se proporcionó.
        if usuario.tienda:
            tienda = usuario.tienda
        elif tienda_slug:
            try:
                tienda = Tienda.objects.get(nombre=tienda_slug)
            except Tienda.DoesNotExist:
                raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})
        else:
            raise serializers.ValidationError({"tienda": "No se pudo determinar la tienda para la venta. Asegúrate de que el usuario tenga una tienda asignada o proporciona un 'tienda_slug'."})

        validated_data['tienda'] = tienda
        validated_data['metodo_pago'] = metodo_pago_obj.nombre
        validated_data['usuario'] = usuario

        venta = Venta.objects.create(**validated_data)
        total_venta = Decimal('0.00')

        for detalle_data in detalles_data:
            producto_id = detalle_data.get('producto') # Asumo que el frontend envía 'producto' como ID
            cantidad = detalle_data.get('cantidad')

            if not producto_id or not cantidad:
                raise serializers.ValidationError("Cada detalle de venta debe tener 'producto' (ID) y 'cantidad'.")

            try:
                producto = Producto.objects.get(id=producto_id, tienda=tienda)
            except Producto.DoesNotExist:
                raise serializers.ValidationError(f"Producto con ID {producto_id} no encontrado en tu tienda.")

            if producto.stock < cantidad:
                raise serializers.ValidationError(f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock}, Solicitado: {cantidad}")

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


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer personalizado para JWT que incluye información del usuario
    y sus tiendas al iniciar sesión. (Esta clase se ha movido al final)
    """
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
        # Aquí puedes añadir más datos al response del token si es necesario
        # Por ejemplo, la lista de tiendas del usuario, etc.
        return data
