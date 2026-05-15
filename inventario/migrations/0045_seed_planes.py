from django.db import migrations


PLANES = [
    {
        'nombre': 'starter',
        'precio_mensual': '35000.00',
        'max_productos': 1000,
        'max_usuarios': 2,
        'permite_factura_electronica': False,
        'permite_integracion_ecommerce': False,
    },
    {
        'nombre': 'pro',
        'precio_mensual': '40000.00',
        'max_productos': 2500,
        'max_usuarios': 4,
        'permite_factura_electronica': True,
        'permite_integracion_ecommerce': False,
    },
    {
        'nombre': 'advanced',
        'precio_mensual': '60000.00',
        'max_productos': None,
        'max_usuarios': None,
        'permite_factura_electronica': True,
        'permite_integracion_ecommerce': True,
    },
]


def seed_planes(apps, schema_editor):
    Plan = apps.get_model('inventario', 'Plan')
    for datos in PLANES:
        Plan.objects.update_or_create(nombre=datos['nombre'], defaults=datos)


def remove_planes(apps, schema_editor):
    Plan = apps.get_model('inventario', 'Plan')
    Plan.objects.filter(nombre__in=['starter', 'pro', 'advanced']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0044_add_plan_suscripcion'),
    ]

    operations = [
        migrations.RunPython(seed_planes, remove_planes),
    ]
