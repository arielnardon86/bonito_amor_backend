    # inventario/migrations/0001_initial.py (El nombre del archivo será diferente)

import uuid # Asegúrate de que uuid esté importado
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone # Asegúrate de que timezone esté importado


def populate_uuid_for_existing_products(apps, schema_editor):
        Producto = apps.get_model('inventario', 'Producto')
        for producto in Producto.objects.all():
            if producto.codigo_barras is None: # Solo si es nulo (puede que no haya nulos si es una tabla nueva)
                producto.codigo_barras = uuid.uuid4()
                producto.save(update_fields=['codigo_barras'])

def populate_product_for_existing_detalleventa(apps, schema_editor):
        DetalleVenta = apps.get_model('inventario', 'DetalleVenta')
        Producto = apps.get_model('inventario', 'Producto')

        try:
            default_product = Producto.objects.first() 
        except Producto.DoesNotExist:
            default_product = None 

        if default_product:
            for detalle in DetalleVenta.objects.all():
                if detalle.producto is None:
                    detalle.producto = default_product
                    detalle.save(update_fields=['producto'])


class Migration(migrations.Migration):

        initial = True # DEBE SER TRUE

        dependencies = [
            ('auth', '0012_alter_user_first_name_max_length'), # DEBE SER LA ÚNICA DEPENDENCIA DE AUTH
        ]

        operations = [
            # ... (Aquí irán todas las operaciones de CreateModel para tus modelos: Categoria, Tienda, Producto, User, Venta, DetalleVenta) ...
            # Django las genera automáticamente.

            # EJEMPLO: Si Producto se crea aquí y codigo_barras es NOT NULL
            migrations.CreateModel(
                name='Producto',
                fields=[
                    # ... otros campos ...
                    ('codigo_barras', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                    # ...
                ],
                # ...
            ),
            # AÑADE ESTA OPERACIÓN RunPython JUSTO DESPUÉS DE LA CREACIÓN DEL MODELO Producto
            migrations.RunPython(populate_uuid_for_existing_products, migrations.RunPython.noop),

            # EJEMPLO: Si DetalleVenta se crea aquí y producto es NOT NULL
            migrations.CreateModel(
                name='DetalleVenta',
                fields=[
                    # ... otros campos ...
                    ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detalles_venta', to='inventario.producto')),
                    # ...
                ],
                # ...
            ),
            # AÑADE ESTA OPERACIÓN RunPython JUSTO DESPUÉS DE LA CREACIÓN DEL MODELO DetalleVenta
            migrations.RunPython(populate_product_for_existing_detalleventa, migrations.RunPython.noop),

            # ... el resto de las operaciones generadas por Django ...
        ]
    