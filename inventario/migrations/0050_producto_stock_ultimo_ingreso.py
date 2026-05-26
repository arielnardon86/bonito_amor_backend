from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0049_suscripcion_fecha_cancelacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='stock_ultimo_ingreso',
            field=models.IntegerField(blank=True, null=True, help_text='Stock registrado tras el último ingreso manual'),
        ),
        migrations.AddField(
            model_name='producto',
            name='fecha_ultimo_ingreso',
            field=models.DateTimeField(blank=True, null=True, help_text='Fecha del último ingreso manual de stock'),
        ),
    ]
