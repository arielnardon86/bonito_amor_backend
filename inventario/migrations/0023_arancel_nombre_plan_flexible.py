# Generated manually - permite planes personalizados además de los predefinidos
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0022_arancel_ml_producto'),
    ]

    operations = [
        migrations.AlterField(
            model_name='arancelmetodotienda',
            name='nombre_plan',
            field=models.CharField(max_length=50, default='CONTADO', help_text='Plan predefinido o nombre personalizado (ej: 18 cuotas)'),
        ),
    ]
