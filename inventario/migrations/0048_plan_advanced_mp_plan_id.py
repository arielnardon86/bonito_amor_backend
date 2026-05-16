from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0047_plan_pro_mp_plan_id'),
    ]

    operations = [
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('inventario', 'Plan').objects.filter(
                nombre='advanced'
            ).update(mp_plan_id='a37d74f3744246d1a14cf181a78eb072'),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
