# Generated manually
from django.conf import settings
import django.db.models.deletion
import django.utils.timezone
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0012_tienda_condicion_iva_emisor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CambioDevolucion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('DEVOLUCION', 'Devolución Total'), ('CAMBIO', 'Cambio de Producto'), ('DEVOLUCION_PARCIAL', 'Devolución Parcial')], default='CAMBIO', help_text='Tipo de cambio/devolución', max_length=20)),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('PROCESADO', 'Procesado'), ('CANCELADO', 'Cancelado')], default='PROCESADO', max_length=20)),
                ('motivo', models.TextField(blank=True, help_text='Motivo del cambio o devolución', null=True)),
                ('monto_devolucion', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Monto a devolver al cliente (productos devueltos)', max_digits=10)),
                ('monto_nuevo', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Monto de productos nuevos recibidos en el cambio', max_digits=10)),
                ('monto_diferencia', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Diferencia: positivo = cliente debe pagar, negativo = saldo a favor del cliente', max_digits=10)),
                ('saldo_a_favor', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Saldo a favor del cliente que queda pendiente', max_digits=10)),
                ('saldo_utilizado', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Saldo a favor que fue utilizado en compras posteriores', max_digits=10)),
                ('nota_credito_generada', models.BooleanField(default=False, help_text='Indica si se generó un recibo/nota de crédito por el saldo a favor')),
                ('diferencia_pendiente', models.BooleanField(default=False, help_text='Indica si hay una diferencia a pagar pendiente')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cambios_devoluciones', to='inventario.tienda')),
                ('usuario', models.ForeignKey(blank=True, help_text='Usuario que procesó el cambio/devolución', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_devoluciones_procesados', to=settings.AUTH_USER_MODEL)),
                ('venta_diferencia_pendiente', models.ForeignKey(blank=True, help_text='Venta creada para la diferencia a pagar (se completa desde el flujo normal de ventas)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambio_devolucion_diferencia', to='inventario.venta')),
                ('venta_nota_credito', models.ForeignKey(blank=True, help_text='Venta/Recibo generado como nota de crédito (saldo a favor)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='nota_credito_origen', to='inventario.venta')),
                ('venta_original', models.ForeignKey(help_text='Venta original de la que se realiza el cambio/devolución', on_delete=django.db.models.deletion.CASCADE, related_name='cambios_devoluciones', to='inventario.venta')),
            ],
            options={
                'verbose_name': 'Cambio/Devolución',
                'verbose_name_plural': 'Cambios/Devoluciones',
                'ordering': ['-fecha_creacion'],
            },
        ),
        migrations.CreateModel(
            name='DetalleCambioDevolucion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('accion', models.CharField(choices=[('DEVOLVER', 'Devolver Producto'), ('CAMBIAR', 'Cambiar Producto'), ('AGREGAR', 'Agregar Producto Nuevo')], help_text='Acción realizada sobre el producto', max_length=20)),
                ('cantidad', models.IntegerField(default=1, help_text='Cantidad de productos afectados')),
                ('precio_unitario_devuelto', models.DecimalField(blank=True, decimal_places=2, help_text='Precio unitario del producto devuelto', max_digits=10, null=True)),
                ('precio_unitario_nuevo', models.DecimalField(blank=True, decimal_places=2, help_text='Precio unitario del producto nuevo', max_digits=10, null=True)),
                ('subtotal_devuelto', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Subtotal del producto devuelto', max_digits=10)),
                ('subtotal_nuevo', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Subtotal del producto nuevo', max_digits=10)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('cambio_devolucion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detalles', to='inventario.cambiodevolucion')),
                ('detalle_venta_original', models.ForeignKey(blank=True, help_text='Detalle de venta original que se devuelve o cambia', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_devoluciones', to='inventario.detalleventa')),
                ('producto_nuevo', models.ForeignKey(blank=True, help_text='Producto nuevo que se recibe en el cambio', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_recibidos', to='inventario.producto')),
            ],
            options={
                'verbose_name': 'Detalle de Cambio/Devolución',
                'verbose_name_plural': 'Detalles de Cambios/Devoluciones',
                'ordering': ['fecha_creacion'],
            },
        ),
    ]


