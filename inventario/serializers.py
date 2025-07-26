    # BONITO_AMOR/backend/inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago

    # Serializer para el usuario, para anidar en VentaSerializer
class SimpleUserSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ['id', 'username', 'first_name', 'last_name'] # Puedes añadir más campos si los necesitas

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
        # Asegúrate de que 'producto_nombre' se resuelva correctamente
        producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
        # Asegúrate de que 'precio_unitario_venta' se resuelva correctamente
        precio_unitario_venta = serializers.DecimalField(source='precio_unitario', max_digits=10, decimal_places=2, read_only=True)


        class Meta:
            model = DetalleVenta
            fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'precio_unitario_venta', 'subtotal']
            read_only_fields = ['subtotal'] # subtotal se calcula en el modelo o en la vista

class VentaSerializer(serializers.ModelSerializer):
        detalles = DetalleVentaSerializer(many=True, read_only=True)
        # CAMBIO CLAVE: Usa el SimpleUserSerializer para el campo 'usuario'
        usuario = SimpleUserSerializer(read_only=True) 
        
        # CAMBIO CLAVE: Asegúrate de que 'total' sea el campo correcto del modelo Venta
        # Si tu modelo Venta tiene un campo 'total', esto es suficiente:
        total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
        # Si lo llamas 'total_venta' en el frontend pero es 'total' en el modelo, puedes usar:
        # total_venta = serializers.DecimalField(source='total', max_digits=10, decimal_places=2, read_only=True)

        # CAMBIO CLAVE: Asegúrate de que 'metodo_pago' se exponga correctamente
        # Si 'metodo_pago' es un ForeignKey a MetodoPago, usa source='metodo_pago.nombre'
        metodo_pago = serializers.CharField(source='metodo_pago.nombre', read_only=True)
        # Si 'metodo_pago' es un CharField directo en el modelo Venta, usa:
        # metodo_pago = serializers.CharField(read_only=True)


        class Meta:
            model = Venta
            # Asegúrate de que 'total', 'usuario', 'metodo_pago' estén en los fields
            fields = ['id', 'fecha_venta', 'total', 'usuario', 'metodo_pago', 'tienda', 'anulada', 'detalles']
            read_only_fields = ['id', 'fecha_venta', 'total', 'anulada', 'detalles']

class VentaCreateSerializer(serializers.ModelSerializer):
        detalles = DetalleVentaSerializer(many=True) # Permite crear detalles anidados

        class Meta:
            model = Venta
            fields = ['tienda', 'metodo_pago', 'detalles'] # 'usuario' se asignará en la vista
            read_only_fields = ['total'] # El total se calcula en el backend

        def create(self, validated_data):
            detalles_data = validated_data.pop('detalles')
            venta = Venta.objects.create(**validated_data)
            total_venta = Decimal('0.00')
            for detalle_data in detalles_data:
                producto = detalle_data['producto']
                cantidad = detalle_data['cantidad']
                precio_unitario = detalle_data['precio_unitario'] # Usar el precio unitario proporcionado
                subtotal = precio_unitario * cantidad
                DetalleVenta.objects.create(venta=venta, subtotal=subtotal, **detalle_data)
                total_venta += subtotal
                # Actualizar stock del producto
                producto.stock -= cantidad
                producto.save()
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
            # Aquí puedes añadir lógica para verificar la tienda_slug si se envía en el login
            # Si el usuario no tiene tienda asignada y se requiere, puedes manejarlo aquí.
            return data