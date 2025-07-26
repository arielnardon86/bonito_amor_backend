    # inventario/migrations/0002_auto_YYYYMMDD_HHMM.py (El nombre del archivo será diferente)

from django.db import migrations


class Migration(migrations.Migration):

        initial = True # CAMBIO CLAVE: Establecer a True

        dependencies = [
            ('auth', '0012_alter_user_first_name_max_length'), # Asegúrate de que esta dependencia exista
            # NO DEBE HABER OTRAS DEPENDENCIAS A MIGRACIONES DE 'inventario' AQUÍ
        ]

        operations = [
            # NO AÑADAS NADA AQUÍ. Las operaciones se dejarán vacías.
        ]