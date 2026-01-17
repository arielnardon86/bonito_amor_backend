# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0011_fix_missing_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='tienda',
            name='condicion_iva_emisor',
            field=models.CharField(
                choices=[
                    ('RI', 'Responsable Inscripto'),
                    ('MT', 'Monotributista'),
                    ('CF', 'Consumidor Final'),
                    ('EX', 'Exento'),
                    ('NR', 'No Responsable'),
                ],
                default='MT',
                help_text='Condición frente al IVA del emisor (tienda). Importante: Solo Responsables Inscriptos pueden emitir Factura A.',
                max_length=2,
            ),
        ),
    ]



