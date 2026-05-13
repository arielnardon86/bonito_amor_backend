from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0042_add_producto_padre'),
    ]

    operations = [
        migrations.AlterField(
            model_name='producto',
            name='producto_padre',
            field=models.ForeignKey(
                blank=True,
                help_text='Producto padre del que esta variante forma parte',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='variantes',
                to='inventario.producto',
            ),
        ),
    ]
