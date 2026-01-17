# Generated manually - Fix para establecer valor por defecto de ml_modo_test en la base de datos

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0017_create_categoria_mercadolibre'),
    ]

    operations = [
        # Primero, establecer el valor por defecto para todas las tiendas existentes que tengan NULL
        migrations.RunSQL(
            "UPDATE inventario_tienda SET ml_modo_test = TRUE WHERE ml_modo_test IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Luego, asegurar que el campo tenga un valor por defecto en la base de datos
        migrations.AlterField(
            model_name='tienda',
            name='ml_modo_test',
            field=models.BooleanField(default=True, help_text='Usar ambiente de testing/sandbox de Mercado Libre (True) o producción (False)'),
        ),
    ]
