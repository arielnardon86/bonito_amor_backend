# UniqueConstraint para evitar ventas duplicadas de ML (race condition)
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0024_venta_ml_order_id'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='venta',
            constraint=models.UniqueConstraint(
                condition=models.Q(ml_order_id__isnull=False),
                fields=('tienda', 'ml_order_id'),
                name='unique_ml_order_per_tienda',
            ),
        ),
    ]
