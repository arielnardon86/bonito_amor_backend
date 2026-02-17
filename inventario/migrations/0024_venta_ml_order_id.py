# Generated - campo para evitar duplicados de ventas desde webhook Mercado Libre
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0023_arancel_nombre_plan_flexible'),
    ]

    operations = [
        migrations.AddField(
            model_name='venta',
            name='ml_order_id',
            field=models.CharField(blank=True, help_text='ID de la orden en Mercado Libre (para evitar duplicados)', max_length=50, null=True),
        ),
    ]
