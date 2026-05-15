from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0045_seed_planes'),
    ]

    operations = [
        # 1. Agregar columna mp_plan_id al modelo Plan
        migrations.AddField(
            model_name='plan',
            name='mp_plan_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),

        # 2. Cargar el preapproval_plan_id del plan Starter creado en MP
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('inventario', 'Plan').objects.filter(
                nombre='starter'
            ).update(mp_plan_id='dd05bca060ed48d3aff16daaeb18c54f'),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
