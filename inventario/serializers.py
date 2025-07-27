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
        read_only_fields = ['subtotal', 'venta'] # 'venta' también es read_only en este contexto de creación anidada

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True) 
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    # CAMBIO CLAVE: Si metodo_pago es un CharField en el modelo Venta
    # metodo_pago = serializers.CharField(read_only=True)
    # Si metodo_pago es un ForeignKey a MetodoPago, y quieres el nombre:
    metodo_pago = serializers.CharField(source='metodo_pago.nombre', read_only=True)


    class Meta:
        model = Venta
        fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'detalles']
        read_only_fields = ['id', 'fecha_venta', 'total', 'detalles'] # 'anulada' no está en el modelo Venta que adjuntaste

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True)
    # CAMBIO CLAVE: Aceptar el slug de la tienda
    tienda_slug = serializers.CharField(write_only=True, required=True)
    # CAMBIO CLAVE: Aceptar el nombre del método de pago
    metodo_pago_nombre = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Venta
        # Excluye 'tienda' y 'metodo_pago' del fields, los manejaremos manualmente
        fields = ['tienda_slug', 'metodo_pago_nombre', 'detalles']
        read_only_fields = ['total', 'usuario'] # 'usuario' se asignará en la vista

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
        validated_data['metodo_pago'] = metodo_pago_obj # Asignar el objeto MetodoPago

        # Obtener el usuario de la request (pasado desde la vista)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['usuario'] = request.user
        else:
            # Esto debería ser manejado por las permisos, pero como fallback
            raise serializers.ValidationError({"usuario": "Usuario no autenticado para realizar la venta."})


        venta = Venta.objects.create(**validated_data)
        total_venta = Decimal('0.00')

        for detalle_data in detalles_data:
            producto = detalle_data['producto'] # Esto ya es un objeto Producto si el DetalleVentaSerializer lo maneja
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']

            # Asegurarse de que el producto sea un objeto Producto, no solo un ID
            if isinstance(producto, str): # Si viene como ID (UUID string)
                try:
                    producto_obj = Producto.objects.get(id=producto)
                except Producto.DoesNotExist:
                    raise serializers.ValidationError({"detalles": f"Producto con ID {producto} no encontrado."})
            else: # Si ya es un objeto Producto
                producto_obj = producto

            subtotal = precio_unitario * cantidad
            DetalleVenta.objects.create(venta=venta, subtotal=subtotal, producto=producto_obj, cantidad=cantidad, precio_unitario=precio_unitario)
            total_venta += subtotal
            
            # Actualizar stock del producto
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
        # Añadir información adicional al token
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
