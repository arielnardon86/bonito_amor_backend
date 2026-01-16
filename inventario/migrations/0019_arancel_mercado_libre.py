# Generated manually
from django.db import migrations, models
import django.db.models.deletion
import uuid
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0018_fix_ml_modo_test_default'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArancelMercadoLibre',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('arancel_porcentaje', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Arancel en porcentaje (%) que la tienda paga a Mercado Libre por ventas en esta categoría.', max_digits=5)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('categoria_ml', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aranceles_por_tienda', to='inventario.categoriamercadolibre')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aranceles_ml', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Arancel Mercado Libre por Categoría',
                'verbose_name_plural': 'Aranceles Mercado Libre por Categoría',
                'ordering': ['tienda', 'categoria_ml__nombre'],
                'unique_together': {('tienda', 'categoria_ml')},
            },
        ),
        migrations.AddIndex(
            model_name='arancelmercadolibre',
            index=models.Index(fields=['tienda', 'categoria_ml'], name='inventario_tienda__idx'),
        ),
    ]
