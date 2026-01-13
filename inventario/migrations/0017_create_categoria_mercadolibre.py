# Generated manually
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0016_add_ml_sincronizar_and_categoria'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriaMercadoLibre',
            fields=[
                ('id', models.CharField(max_length=50, primary_key=True, serialize=False, help_text='ID de la categoría en Mercado Libre (ej: MLA1574)')),
                ('nombre', models.CharField(max_length=255, help_text='Nombre de la categoría')),
                ('site_id', models.CharField(default='MLA', help_text='ID del sitio (MLA=Argentina, MLB=Brasil, etc.)', max_length=10)),
                ('parent_id', models.CharField(blank=True, help_text='ID de la categoría padre', max_length=50, null=True)),
                ('is_leaf', models.BooleanField(default=False, help_text='Indica si es una categoría hoja (sin subcategorías)')),
                ('total_items', models.IntegerField(default=0, help_text='Total de items en esta categoría')),
                ('path_from_root', models.JSONField(blank=True, default=list, help_text='Ruta completa desde la raíz')),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True, help_text='Fecha de última actualización')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True, help_text='Fecha de creación del registro')),
            ],
            options={
                'verbose_name': 'Categoría Mercado Libre',
                'verbose_name_plural': 'Categorías Mercado Libre',
                'ordering': ['nombre'],
            },
        ),
        migrations.AddIndex(
            model_name='categoriamercadolibre',
            index=models.Index(fields=['site_id', 'is_leaf'], name='inventario_c_site_id_123456_idx'),
        ),
        migrations.AddIndex(
            model_name='categoriamercadolibre',
            index=models.Index(fields=['parent_id'], name='inventario_c_parent_i_123456_idx'),
        ),
    ]
