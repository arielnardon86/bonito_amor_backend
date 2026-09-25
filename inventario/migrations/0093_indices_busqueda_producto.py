from django.db import migrations


# Índices para acelerar la búsqueda de productos en Punto de Venta / Gestión de
# Productos en catálogos grandes (se detectó lentitud real con ~40.000 productos
# en una tienda). Son específicos de Postgres (trigram y expresiones UPPER()) --
# se aplican solo si el backend en uso es Postgres, para no romper `migrate` en
# desarrollo local (SQLite) donde no existen `pg_trgm` ni el mismo soporte de
# índices de expresión.
#
# Por qué estos índices puntuales:
# - `nombre__icontains` (Django lo compila en Postgres como
#   `UPPER(nombre) LIKE UPPER('%valor%')`, ver
#   https://code.djangoproject.com/ticket/25538) no puede usar un índice B-tree
#   común por el comodín inicial -- necesita GIN + pg_trgm sobre esa misma
#   expresión UPPER(nombre) para poder usarse.
# - `codigo_barras__iexact` / `codigo_interno__iexact` compilan a
#   `UPPER(campo) = UPPER('valor')` -- un índice funcional sobre UPPER(campo)
#   sí alcanza para que Postgres lo use en una igualdad exacta.
def crear_indices_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS producto_nombre_upper_trgm_idx "
            "ON inventario_producto USING gin ((UPPER(nombre)) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS producto_codigo_barras_upper_idx "
            "ON inventario_producto (UPPER(codigo_barras));"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS producto_codigo_interno_upper_idx "
            "ON inventario_producto (UPPER(codigo_interno));"
        )


def eliminar_indices_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS producto_nombre_upper_trgm_idx;")
        cursor.execute("DROP INDEX IF EXISTS producto_codigo_barras_upper_idx;")
        cursor.execute("DROP INDEX IF EXISTS producto_codigo_interno_upper_idx;")


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0092_tienda_tn_location_id'),
    ]

    operations = [
        migrations.RunPython(crear_indices_postgres, eliminar_indices_postgres),
    ]
