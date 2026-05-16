from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0046_plan_mp_plan_id'),
    ]

    operations = [
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('inventario', 'Plan').objects.filter(
                nombre='pro'
            ).update(mp_plan_id='65abf68a5abe4ec9a264595cf6db50b0'),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
