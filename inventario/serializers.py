# inventario/serializers.py - CÓDIGO COMPLETO Y CORREGIDO
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda 
from decimal import Decimal 
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer # Importación necesaria aquí

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']

class ProductoSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.SlugRelatedField(
        source='tienda',
        slug_field='nombre',
        queryset=Tienda.objects.all(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Producto
        fields = ['id', 'nombre', 'talle', 'precio', 'costo', 'stock', 'codigo_barras', 'tienda_slug']

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class TiendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    tienda = serializers.SlugRelatedField(
        slug_field='nombre', 
        queryset=Tienda.objects.all(), 
        required=False, 
        allow_null=True 
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'tienda']
        read_only_fields = ['is_staff', 'is_superuser']

class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

# NUEVO SERIALIZER: Arancel por Método y Tienda
class ArancelMetodoTiendaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)
    
    class Meta:
        model = ArancelMetodoTienda
        fields = ['id', 'metodo_pago', 'metodo_pago_nombre', 'nombre_plan', 'arancel_porcentaje']
# ------------------------------------------------

class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True) 
    
    class Meta:
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'costo_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion']
        model = DetalleVenta
        read_only_fields = ['subtotal']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    # Campos de arancel para lectura
    arancel_aplicado_nombre = serializers.CharField(source='arancel_aplicado.nombre_plan', read_only=True)
    arancel_aplicado_porcentaje = serializers.DecimalField(source='arancel_aplicado.arancel_porcentaje', max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id', 'fecha_venta', 'total', 'anulada', 
            'descuento_porcentaje', 'descuento_monto',
            'recargo_porcentaje', 'recargo_monto',
            'metodo_pago', 'metodo_pago_nombre', 
            'usuario', 'tienda', 'tienda_nombre', 'detalles',
            'arancel_aplicado', 'arancel_aplicado_nombre', 'arancel_aplicado_porcentaje', 'arancel_total',
            'fecha_creacion', 'fecha_actualizacion'
        ]

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(
        child=serializers.DictField(),
        write_only=True 
    )
    tienda_slug = serializers.CharField(write_only=True)
    arancel_aplicado_id = serializers.PrimaryKeyRelatedField(
        queryset=ArancelMetodoTienda.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    
    class Meta:
        model = Venta
        fields = [
            'id',
            'fecha_venta',
            'descuento_porcentaje', 'descuento_monto', 
            'recargo_porcentaje', 'recargo_monto', 
            'metodo_pago', 
            'tienda_slug', 'detalles', 'arancel_aplicado_id'
        ]
        extra_kwargs = {
            'descuento_porcentaje': {'required': False},
            'descuento_monto': {'required': False},
            'recargo_porcentaje': {'required': False}, 
            'recargo_monto': {'required': False},      
        }

    def validate(self, data):
        detalles_data = data.get('detalles', [])
        tienda_slug = data.get('tienda_slug')

        if not detalles_data:
            raise serializers.ValidationError("La venta debe tener al menos un detalle de venta.")
        if not tienda_slug:
            raise serializers.ValidationError({"tienda_slug": "El slug de la tienda es obligatorio."})

        try:
            tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError({"tienda_slug": "Tienda no encontrada."})

        data['tienda'] = tienda_obj
        
        calculated_subtotal = Decimal('0.00')
        for detalle_data in detalles_data:
            producto_id = detalle_data.get('producto')
            cantidad = detalle_data.get('cantidad')
            precio_unitario = detalle_data.get('precio_unitario')

            if not all([producto_id, cantidad, precio_unitario is not None]):
                raise serializers.ValidationError({"detalles": "Cada detalle debe tener un 'producto', 'cantidad' y 'precio_unitario'."})

            try:
                producto_obj = Producto.objects.get(id=producto_id, tienda=tienda_obj)
            except Producto.DoesNotExist:
                raise serializers.ValidationError({"detalles": f"Producto con ID {producto_id} no encontrado en la tienda {tienda_slug}."})
            
            if producto_obj.stock < cantidad:
                raise serializers.ValidationError({"detalles": f"Stock insuficiente para el producto {producto_obj.nombre}. Stock disponible: {producto_obj.stock}, solicitado: {cantidad}."})
            
            if precio_unitario < 0:
                raise serializers.ValidationError({"detalles": "El precio unitario no puede ser negativo."})

            calculated_subtotal += precio_unitario * cantidad
            # Agrega el costo al detalle de datos si existe
            detalle_data['costo_unitario'] = producto_obj.costo

        descuento_porcentaje = data.get('descuento_porcentaje', Decimal('0.00'))
        descuento_monto = data.get('descuento_monto', Decimal('0.00'))
        recargo_porcentaje = data.get('recargo_porcentaje', Decimal('0.00'))
        recargo_monto = data.get('recargo_monto', Decimal('0.00'))
        
        # Validación de exclusividad: Solo puede haber un tipo de ajuste
        ajustes_aplicados = [a for a in [descuento_monto, descuento_porcentaje, recargo_monto, recargo_porcentaje] if a > Decimal('0.00')]

        if len(ajustes_aplicados) > 1:
            raise serializers.ValidationError({"ajustes": "Solo se puede aplicar un tipo de ajuste (desc. monto/porcentaje o recargo monto/porcentaje) a la vez."})
        
        # CÁLCULO DEL TOTAL CON RECARGO/DESCUENTO
        if recargo_monto > 0: 
            data['total'] = calculated_subtotal + recargo_monto
        elif recargo_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') + (recargo_porcentaje / Decimal('100')))
        elif descuento_monto > 0:
            data['total'] = max(Decimal('0.00'), calculated_subtotal - descuento_monto)
        elif descuento_porcentaje > 0:
            data['total'] = calculated_subtotal * (Decimal('1') - (descuento_porcentaje / Decimal('100')))
        else:
            data['total'] = calculated_subtotal
        
        # Lógica de arancel
        data['arancel_total'] = Decimal('0.00')
        arancel_obj = data.pop('arancel_aplicado_id', None) 

        metodos_financieros = MetodoPago.objects.filter(es_financiero=True).values_list('nombre', flat=True)

        if data.get('metodo_pago') in metodos_financieros:
            if not arancel_obj:
                 raise serializers.ValidationError({"arancel_aplicado_id": "Se requiere seleccionar un Plan/Arancel para este método de pago."})

            if arancel_obj.tienda != data['tienda']:
                 raise serializers.ValidationError({"arancel_aplicado_id": "El arancel seleccionado no pertenece a la tienda actual."})
            
            arancel_porcentaje = arancel_obj.arancel_porcentaje
            total_final = data['total']
            data['arancel_total'] = total_final * (arancel_porcentaje / Decimal('100'))
            data['arancel_aplicado'] = arancel_obj # Guardamos el objeto para el create

        elif arancel_obj:
            raise serializers.ValidationError({"metodo_pago": "No se permite seleccionar un Arancel para el método de pago seleccionado."})

        data['fecha_venta'] = timezone.now()

        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        arancel_aplicado = validated_data.pop('arancel_aplicado', None)
        arancel_total = validated_data.pop('arancel_total', Decimal('0.00'))

        venta = Venta.objects.create(
            total=validated_data['total'],
            usuario=self.context['request'].user, 
            tienda=validated_data['tienda'],
            metodo_pago=validated_data['metodo_pago'],
            descuento_porcentaje=validated_data.get('descuento_porcentaje', Decimal('0.00')),
            descuento_monto=validated_data.get('descuento_monto', Decimal('0.00')),
            recargo_porcentaje=validated_data.get('recargo_porcentaje', Decimal('0.00')),
            recargo_monto=validated_data.get('recargo_monto', Decimal('0.00')),
            arancel_aplicado=arancel_aplicado, 
            arancel_total=arancel_total,       
            fecha_venta=validated_data['fecha_venta'],
        )
        
        for detalle_data in detalles_data:
            producto_id = detalle_data['producto'] 
            cantidad = detalle_data['cantidad']
            precio_unitario = detalle_data['precio_unitario']
            costo_unitario = detalle_data.get('costo_unitario', None)

            producto_obj = Producto.objects.get(id=producto_id)
            subtotal = precio_unitario * cantidad
            DetalleVenta.objects.create(
                venta=venta,
                subtotal=subtotal,
                producto=producto_obj,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                costo_unitario=costo_unitario
            )

            producto_obj.stock -= cantidad
            producto_obj.save()

        return venta

# CRUCIAL: DEFINICIÓN DE CustomTokenObtainPairSerializer MOVIDA AL FINAL
# Esto soluciona el error de importación.
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
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
        return data

class CompraSerializer(serializers.ModelSerializer):
    usuario = SimpleUserSerializer(read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Compra
        fields = '__all__'
        read_only_fields = ['usuario', 'fecha_compra']

class CompraCreateSerializer(serializers.ModelSerializer):
    tienda_slug = serializers.CharField(write_only=True)
    fecha_compra = serializers.DateField(write_only=True)

    class Meta:
        model = Compra
        fields = ['total', 'proveedor', 'tienda_slug', 'fecha_compra']
        extra_kwargs = {
            'total': {'required': True},
            'proveedor': {'required': False},
        }

    def create(self, validated_data):
        tienda_slug = validated_data.pop('tienda_slug')
        fecha_compra_data = validated_data.pop('fecha_compra') 
        tienda_obj = get_object_or_404(Tienda, nombre=tienda_slug)
        
        compra_fields = {
            'total': validated_data.pop('total'),
            'proveedor': validated_data.pop('proveedor', None),
            'tienda': tienda_obj,
            'usuario': self.context['request'].user,
            'fecha_compra': fecha_compra_data 
        }
        
        compra = Compra.objects.create(**compra_fields)
        return compra