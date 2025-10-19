# inventario/serializers.py
from rest_framework import serializers
from .models import Producto, Categoria, Tienda, User, Venta, DetalleVenta, MetodoPago, Compra, ArancelMetodoTienda 
from decimal import Decimal 
from django.utils import timezone
from django.shortcuts import get_object_or_404

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

# --- NUEVO SERIALIZER: Arancel por Método y Tienda ---
class ArancelMetodoTiendaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)
    
    class Meta:
        model = ArancelMetodoTienda
        fields = ['id', 'metodo_pago', 'metodo_pago_nombre', 'nombre_plan', 'arancel_porcentaje']
# ------------------------------------------------

class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True) 
    
    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'costo_unitario', 'subtotal', 'anulado_individualmente', 'fecha_creacion', 'fecha_actualizacion']
        read_only_fields = ['subtotal']

class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    usuario = SimpleUserSerializer(read_only=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    # NUEVO: Detalle del arancel aplicado
    arancel_aplicado_nombre = serializers.CharField(source='arancel_aplicado.nombre_plan', read_only=True)
    arancel_aplicado_porcentaje = serializers.DecimalField(source='arancel_aplicado.arancel_porcentaje', max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = Venta
        fields = [
            'id', 'fecha_venta', 'total', 'anulada', 'descuento_porcentaje', 'descuento_monto',
            'metodo_pago', 'metodo_pago_nombre', 
            'usuario', 'tienda', 'tienda_nombre', 
            'arancel_aplicado', 'arancel_aplicado_nombre', 'arancel_aplicado_porcentaje', 'arancel_total', # NUEVOS CAMPOS
            'detalles',
            'fecha_creacion', 'fecha_actualizacion'
        ]

class VentaCreateSerializer(serializers.ModelSerializer):
    detalles = serializers.ListField(
        child=serializers.DictField(),
        write_only=True 
    )
    tienda_slug = serializers.CharField(write_only=True)
    # NUEVO: Campo para recibir el ID del arancel de cuotas/método
    arancel_aplicado_id = serializers.PrimaryKeyRelatedField(
        queryset=ArancelMetodoTienda.objects.all(),
        required=False,
        allow_null=True,
        write_only=True
    )
    
    class Meta:
        model = Venta
        fields = [
            'descuento_porcentaje', 'descuento_monto', 'metodo_pago', 
            'tienda_slug', 'detalles', 'arancel_aplicado_id' # NUEVO: arancel_aplicado_id
        ]
        extra_kwargs = {
            'descuento_porcentaje': {'required': False},
            'descuento_monto': {'required': False},
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
        # [...] (Lógica de validación de stock y cálculo de subtotal)

        descuento_porcentaje = data.get('descuento_porcentaje', Decimal('0.00'))
        descuento_monto = data.get('descuento_monto', Decimal('0.00'))
        
        if descuento_monto > 0 and descuento_porcentaje > 0:
            raise serializers.ValidationError({"descuentos": "No se pueden aplicar descuentos por monto y porcentaje al mismo tiempo."})
        
        if descuento_monto > 0:
            data['total'] = max(Decimal('0.00'), calculated_subtotal - descuento_monto)
        else:
            data['total'] = calculated_subtotal * (Decimal('1') - (descuento_porcentaje / Decimal('100')))
        
        # CÁLCULO Y VALIDACIÓN DE ARANCEL (si aplica)
        data['arancel_total'] = Decimal('0.00')
        arancel_obj = data.pop('arancel_aplicado_id', None) # Objeto ArancelMetodoTienda

        metodos_financieros = ['Tarjeta de Crédito', 'Tarjeta de Débito', 'Pago QR']

        if data.get('metodo_pago') in metodos_financieros:
            if not arancel_obj:
                 raise serializers.ValidationError({"arancel_aplicado_id": "Se requiere seleccionar un Plan/Arancel para este método de pago."})

            if arancel_obj.tienda != data['tienda']:
                 raise serializers.ValidationError({"arancel_aplicado_id": "El arancel seleccionado no pertenece a la tienda actual."})
            
            # El arancel se calcula sobre el TOTAL final de la venta, después de descuentos.
            arancel_porcentaje = arancel_obj.arancel_porcentaje
            total_final = data['total']
            data['arancel_total'] = total_final * (arancel_porcentaje / Decimal('100'))
            data['arancel_aplicado'] = arancel_obj # Guardamos el objeto para el create

        elif arancel_obj:
            # Si se envió un arancel pero el método no es financiero, es un error
            raise serializers.ValidationError({"metodo_pago": "No se permite seleccionar un Arancel para el método de pago seleccionado."})

        data['fecha_venta'] = timezone.now()
        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles')
        
        # Extraer los nuevos campos
        arancel_aplicado = validated_data.pop('arancel_aplicado', None)
        arancel_total = validated_data.pop('arancel_total', Decimal('0.00'))

        venta = Venta.objects.create(
            total=validated_data['total'],
            usuario=self.context['request'].user, 
            tienda=validated_data['tienda'],
            metodo_pago=validated_data['metodo_pago'],
            descuento_porcentaje=validated_data.get('descuento_porcentaje', Decimal('0.00')),
            descuento_monto=validated_data.get('descuento_monto', Decimal('0.00')),
            arancel_aplicado=arancel_aplicado, # AÑADIDO
            arancel_total=arancel_total,       # AÑADIDO
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

# [...] (CustomTokenObtainPairSerializer, CompraSerializer, CompraCreateSerializer remain the same)