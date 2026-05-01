from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0038_venta_monto_efectivo'),
    ]

    operations = [
        migrations.AddField(
            model_name='tienda',
            name='ml_aranceles_automaticos',
            field=models.BooleanField(
                default=True,
                help_text="Si está activo, los cargos de ML se obtienen de las notificaciones (webhook) y se muestran en 'Descuentos Mercado Libre'. Si está desactivado, se usan los aranceles configurados manualmente y se muestran en 'Aranceles'.",
            ),
        ),
    ]
