# Instrucciones para Verificar Campos ML en Render

## Paso 1: Entrar al Shell de Python

En el shell de Render, ejecuta:

```bash
python manage.py shell
```

Deberías ver algo como:
```
Python 3.12.12 (main, Jan 13 2026, 03:13:28) [GCC 12.2.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
(InteractiveConsole)
>>>
```

**IMPORTANTE**: Debes ver el prompt `>>>` que indica que estás en el shell de Python, NO en bash (`#`).

## Paso 2: Ejecutar el Código de Verificación

Una vez que estés en el shell de Python (`>>>`), copia y pega ESTE código completo de una vez:

```python
from django.db.migrations.recorder import MigrationRecorder
from django.db import connection
from inventario.models import Tienda

print("=" * 60)
print("VERIFICACIÓN DE CAMPOS DE MERCADO LIBRE")
print("=" * 60)

# Verificar qué campos faltan en el modelo
campos_ml = ['plataforma_ecommerce', 'ml_app_id', 'ml_client_secret', 'ml_modo_test', 'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios', 'ml_sincronizar_productos', 'ml_user_id', 'ml_token_expires_at']
campos_faltantes = []
print("\nCampos en el modelo Django:")
for campo in campos_ml:
    try:
        Tienda._meta.get_field(campo)
        print(f"  ✅ {campo}")
    except Exception as e:
        print(f"  ❌ {campo}: {type(e).__name__}")
        campos_faltantes.append(campo)

print("\n" + "=" * 60)
print(f"RESUMEN: {len(campos_faltantes)} campos faltantes en el modelo")
if campos_faltantes:
    print("Campos faltantes:")
    for c in campos_faltantes:
        print(f"  - {c}")
else:
    print("✅ Todos los campos existen en el modelo")
print("=" * 60)
```

## Paso 3: Verificar Campos en la Base de Datos

Sigue en el shell de Python (`>>>`) y ejecuta:

```python
# Verificar campos en BD
with connection.cursor() as cursor:
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'inventario_tienda' AND (column_name LIKE 'ml_%%' OR column_name = 'plataforma_ecommerce')")
    columns_db = [row[0] for row in cursor.fetchall()]

print("\nCampos en la base de datos:")
campos_ml = ['plataforma_ecommerce', 'ml_app_id', 'ml_client_secret', 'ml_modo_test', 'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios', 'ml_sincronizar_productos', 'ml_user_id', 'ml_token_expires_at']
for campo in campos_ml:
    if campo in columns_db:
        print(f"  ✅ {campo}")
    else:
        print(f"  ❌ {campo}")
```

## Notas Importantes

1. **Debes estar en el shell de Python** (prompt `>>>`), NO en bash (prompt `#`)
2. Si ves errores de sintaxis, asegúrate de copiar TODO el bloque de código de una vez
3. Si el código es muy largo, puedes ejecutarlo línea por línea, pero asegúrate de mantener la indentación correcta
4. Para salir del shell de Python, escribe: `exit()` o presiona `Ctrl+D`
