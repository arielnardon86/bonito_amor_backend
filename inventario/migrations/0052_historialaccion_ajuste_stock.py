from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0051_historialaccion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historialaccion',
            name='accion',
            field=models.CharField(
                choices=[
                    ('anulacion_venta',   'Anulación de venta'),
                    ('anulacion_item',    'Anulación de ítem'),
                    ('ingreso_stock',     'Ingreso de stock'),
                    ('ajuste_stock',      'Ajuste de stock'),
                    ('cambio_devolucion', 'Cambio / Devolución'),
                ],
                max_length=30,
            ),
        ),
    ]
