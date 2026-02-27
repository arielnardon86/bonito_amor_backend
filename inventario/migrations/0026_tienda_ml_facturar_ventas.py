# Generated migration for Tienda.ml_facturar_ventas

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0025_venta_unique_ml_order_per_tienda'),
    ]

    operations = [
        migrations.AddField(
            model_name='tienda',
            name='ml_facturar_ventas',
            field=models.BooleanField(
                default=True,
                help_text='Si está activo, las ventas procesadas por el webhook de Mercado Libre se facturan automáticamente (AFIP/ARCA). Si está desactivado, solo se emite recibo (no se genera factura electrónica).'
            ),
        ),
    ]
