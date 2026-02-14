# Generated manually - Aranceles ML por producto (reemplaza categorías)
from django.db import migrations, models
import django.db.models.deletion
import uuid
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0021_rename_inventario_tienda__idx_inventario__tienda__0017ec_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArancelMercadoLibreProducto',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('arancel_porcentaje', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Arancel en % que ML cobra por ventas de este producto', max_digits=5)),
                ('costo_envio', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Costo de envío estimado por unidad de este producto', max_digits=10)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aranceles_ml', to='inventario.producto')),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aranceles_ml_producto', to='inventario.tienda')),
            ],
            options={
                'verbose_name': 'Arancel Mercado Libre por Producto',
                'verbose_name_plural': 'Aranceles Mercado Libre por Producto',
                'ordering': ['tienda', 'producto__nombre'],
                'unique_together': {('tienda', 'producto')},
            },
        ),
        migrations.AddField(
            model_name='venta',
            name='costo_envio_ml',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Costo total de envío (solo ventas Mercado Libre)', max_digits=10),
        ),
        migrations.AddField(
            model_name='venta',
            name='origen_mercadolibre',
            field=models.BooleanField(default=False, help_text='True si la venta provino del webhook de Mercado Libre'),
        ),
        migrations.AddIndex(
            model_name='arancelmercadolibreproducto',
            index=models.Index(fields=['tienda', 'producto'], name='inventario__tienda__aranc_ml_prod_idx'),
        ),
    ]
