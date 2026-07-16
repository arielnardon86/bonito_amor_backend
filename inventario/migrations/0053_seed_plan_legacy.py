from django.db import migrations, models


TIER_CHOICES = [
    ('starter',  'Starter'),
    ('pro',      'Pro'),
    ('advanced', 'Advanced'),
    ('legacy',   'Legacy (sin restricciones)'),
]

PLAN_LEGACY = {
    'nombre': 'legacy',
    'precio_mensual': '0.00',
    'max_productos': None,
    'max_usuarios': None,
    'permite_factura_electronica': True,
    'permite_integracion_ecommerce': True,
}


def seed_plan_legacy(apps, schema_editor):
    Plan = apps.get_model('inventario', 'Plan')
    Plan.objects.update_or_create(nombre=PLAN_LEGACY['nombre'], defaults=PLAN_LEGACY)


def remove_plan_legacy(apps, schema_editor):
    Plan = apps.get_model('inventario', 'Plan')
    Plan.objects.filter(nombre='legacy').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0052_historialaccion_ajuste_stock'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plan',
            name='nombre',
            field=models.CharField(choices=TIER_CHOICES, max_length=20, unique=True),
        ),
        migrations.RunPython(seed_plan_legacy, remove_plan_legacy),
    ]
