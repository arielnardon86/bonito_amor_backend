from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0037_cierre_caja_tipos_movimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='venta',
            name='monto_efectivo',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Monto pagado en efectivo. Para pagos combinados es solo la parte en efectivo.',
                max_digits=10,
                null=True,
            ),
        ),
    ]
