# BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra 
from decimal import Decimal 
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'

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
class UserSerializer(serializers.ModelSerializer):
    tiendas_acceso = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tiendas_acceso']
        read_only_fields = ['is_staff', 'is_superuser']

    def get_tiendas_acceso(self, obj):
        if obj.is_superuser:
            tiendas = Tienda.objects.all()
        else:
            tiendas = Tienda.objects.filter(id=obj.tienda_id) if obj.tienda else Tienda.objects.none()
        
        return TiendaSerializer(tiendas, many=True).data


class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

# Serializador para los detalles de venta en la creación de una venta
class DetalleVentaCreateSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    cantidad = serializers.IntegerField(min_value=1)

    def validate(self, data):
        producto = data['producto']
        cantidad = data['cantidad']
        if cantidad > producto.stock:
            raise serializers.ValidationError(f"No hay suficiente stock para el producto '{producto.nombre}'. Stock disponible: {producto.stock}, solicitado: {cantidad}.")
        return data

class VentaCreateSerializer(serializers.ModelSerializer):
    productos = DetalleVentaCreateSerializer(many=True, write_only=True)
    tienda_slug = serializers.CharField(write_only=True)
    metodo_pago_nombre = serializers.CharField(write_only=True)
    descuento = serializers.DecimalField(max_digits=5, decimal_places=2, write_only=True, default=0.0)

    class Meta:
        model = Venta
        fields = ['id', 'productos', 'tienda_slug', 'descuento', 'metodo_pago_nombre']
        read_only_fields = ['monto_total', 'monto_final']

    def validate(self, data):
        # Asegúrate de que el nombre de la tienda existe
        try:
            tienda = Tienda.objects.get(nombre=data['tienda_slug'])
            data['tienda'] = tienda
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        # Asegúrate de que el método de pago existe
        try:
            metodo_pago = MetodoPago.objects.get(nombre=data['metodo_pago_nombre'])
            data['metodo_pago'] = metodo_pago
        except MetodoPago.DoesNotExist:
            raise serializers.ValidationError({"metodo_pago_nombre": "Método de pago no encontrado."})

        return data

    def create(self, validated_data):
        # CORRECCIÓN: Separar todos los datos que no son campos directos del modelo Venta
        productos_data = validated_data.pop('productos')
        tienda = validated_data.pop('tienda')
        metodo_pago = validated_data.pop('metodo_pago')
        usuario = validated_data.pop('usuario')
        descuento = validated_data.pop('descuento')

        # CORRECCIÓN: Eliminar los campos solo de validación para que no se pasen al modelo
        validated_data.pop('tienda_slug', None)
        validated_data.pop('metodo_pago_nombre', None)


        # Calcular el monto total y final
        monto_total = sum(item['producto'].precio * item['cantidad'] for item in productos_data)
        monto_final = monto_total * (Decimal(1) - (descuento / Decimal(100)))

        # Crear la venta, pasando todos los argumentos de forma explícita
        venta = Venta.objects.create(
            usuario=usuario,
            tienda=tienda,
            metodo_pago=metodo_pago,
            monto_total=monto_total,
            monto_final=monto_final,
            descuento=descuento,
            **validated_data # Esto debería ser un diccionario vacío ahora
        )

        # Crear los detalles de venta y actualizar el stock
        for item_data in productos_data:
            producto = item_data['producto']
            cantidad = item_data['cantidad']
            
            # Crear el detalle de la venta
            DetalleVenta.objects.create(
                venta=venta,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                subtotal=producto.precio * cantidad
            )

            # Actualizar el stock del producto
            producto.stock -= cantidad
            producto.save()

        return venta


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_precio = serializers.DecimalField(source='producto.precio', max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'producto_precio', 'cantidad', 'precio_unitario', 'subtotal']
class VentaSerializer(serializers.ModelSerializer):
    usuario = serializers.ReadOnlyField(source='usuario.username')
    tienda = serializers.ReadOnlyField(source='tienda.nombre')
    metodo_pago = serializers.ReadOnlyField(source='metodo_pago.nombre')
    detalles = DetalleVentaSerializer(many=True, read_only=True, source='detalleventa_set')
    
    class Meta:
        model = Venta
        fields = ['id', 'fecha', 'monto_total', 'monto_final', 'descuento', 'usuario', 'tienda', 'metodo_pago', 'detalles']

class CompraSerializer(serializers.ModelSerializer):
    usuario = SimpleUserSerializer(read_only=True)
    tienda = TiendaSerializer(read_only=True)

    class Meta:
        model = Compra
        fields = ['id', 'fecha_compra', 'total', 'proveedor', 'usuario', 'tienda']


class CompraCreateSerializer(serializers.Serializer):
    tienda_slug = serializers.CharField(write_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    proveedor = serializers.CharField(required=False, allow_blank=True)
    
    def create(self, validated_data):
        tienda_slug = validated_data.pop('tienda_slug')
        
        try:
            tienda_obj = Tienda.objects.get(nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        compra = Compra.objects.create(
            tienda=tienda_obj,
            total=validated_data['total'],
            proveedor=validated_data.get('proveedor', ''),
            usuario=self.context['request'].user, 
        )
        return compra


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        
        return token