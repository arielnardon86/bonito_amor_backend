# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0015_add_mercadolibre_producto_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='ml_sincronizar',
            field=models.BooleanField(default=False, help_text='Marca esta casilla para sincronizar este producto con Mercado Libre en la próxima sincronización'),
        ),
        migrations.AddField(
            model_name='producto',
            name='ml_categoria_id',
            field=models.CharField(blank=True, help_text='ID de la categoría de Mercado Libre para este producto (ej: MLA1574)', max_length=20, null=True),
        ),
    ]
