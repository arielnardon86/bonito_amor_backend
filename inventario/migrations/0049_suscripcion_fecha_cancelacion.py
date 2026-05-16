from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0048_plan_advanced_mp_plan_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='suscripcion',
            name='fecha_cancelacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
