# Generated migration for FCMToken model
# Run: python manage.py migrate inventario 0020

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0019_arancel_mercado_libre'),
    ]

    operations = [
        migrations.CreateModel(
            name='FCMToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token', models.TextField(help_text='Token FCM del dispositivo', unique=True)),
                ('device_info', models.CharField(blank=True, help_text='Información del dispositivo (navegador, SO, etc.)', max_length=255, null=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('activo', models.BooleanField(default=True, help_text='Indica si el token está activo')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fcm_tokens', to='inventario.user')),
            ],
            options={
                'verbose_name': 'Token FCM',
                'verbose_name_plural': 'Tokens FCM',
                'ordering': ['-fecha_creacion'],
            },
        ),
        migrations.AddIndex(
            model_name='fcmtoken',
            index=models.Index(fields=['user', 'activo'], name='inventario__user_id_activo_idx'),
        ),
    ]
