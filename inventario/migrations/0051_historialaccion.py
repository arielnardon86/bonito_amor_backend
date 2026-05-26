import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0050_producto_stock_ultimo_ingreso'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialAccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('accion', models.CharField(choices=[
                    ('anulacion_venta', 'Anulación de venta'),
                    ('anulacion_item', 'Anulación de ítem'),
                    ('ingreso_stock', 'Ingreso de stock'),
                    ('cambio_devolucion', 'Cambio / Devolución'),
                ], max_length=30)),
                ('detalle', models.CharField(max_length=500)),
                ('objeto_id', models.UUIDField(blank=True, null=True)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('tienda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial_acciones', to='inventario.tienda')),
                ('usuario', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='historial_acciones', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Historial de acción',
                'verbose_name_plural': 'Historial de acciones',
                'ordering': ['-fecha'],
            },
        ),
        migrations.AddIndex(
            model_name='historialaccion',
            index=models.Index(fields=['tienda', '-fecha'], name='historial_tienda_fecha_idx'),
        ),
    ]
