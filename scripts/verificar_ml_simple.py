# Script simplificado para ejecutar en Render Shell
# Copia TODO este código de una vez y pégalo en el shell

from django.db.migrations.recorder import MigrationRecorder
from django.db import connection
from inventario.models import Tienda

print("=" * 60)
print("VERIFICACIÓN DE MIGRACIONES Y CAMPOS DE MERCADO LIBRE")
print("=" * 60)
print()

# 1. Verificar migraciones aplicadas
print("1. MIGRACIONES APLICADAS:")
print("-" * 60)
migraciones_ml = [
    '0014_add_mercadolibre_fields',
    '0015_add_mercadolibre_producto_fields',
    '0016_add_ml_sincronizar_and_categoria',
    '0017_create_categoria_mercadolibre',
    '0018_fix_ml_modo_test_default',
]
applied = list(MigrationRecorder.Migration.objects.filter(app='inventario').values_list('name', flat=True))
for mig in migraciones_ml:
    status = "✅" if mig in applied else "❌"
    print(f"  {status} {mig}")
print()

# 2. Verificar campos en BD
print("2. CAMPOS EN LA BASE DE DATOS:")
print("-" * 60)
campos_ml = [
    'plataforma_ecommerce', 'ml_app_id', 'ml_client_secret', 'ml_modo_test',
    'ml_sync_habilitado', 'ml_sincronizar_stock', 'ml_sincronizar_precios',
    'ml_sincronizar_productos', 'ml_user_id', 'ml_token_expires_at',
]
with connection.cursor() as cursor:
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'inventario_tienda' AND (column_name LIKE 'ml_%%' OR column_name = 'plataforma_ecommerce')")
    columns_db = [row[0] for row in cursor.fetchall()]
for campo in campos_ml:
    status = "✅" if campo in columns_db else "❌"
    print(f"  {status} {campo}")
print()

# 3. Verificar campos en el modelo
print("3. CAMPOS EN EL MODELO DJANGO:")
print("-" * 60)
campos_faltantes_modelo = []
for campo in campos_ml:
    try:
        Tienda._meta.get_field(campo)
        print(f"  ✅ {campo}")
    except:
        print(f"  ❌ {campo} (no existe)")
        campos_faltantes_modelo.append(campo)
print()

# 4. Resumen
print("=" * 60)
print("RESUMEN:")
print("=" * 60)
mig_faltantes = [m for m in migraciones_ml if m not in applied]
campos_faltantes_bd = [c for c in campos_ml if c not in columns_db]

if mig_faltantes:
    print(f"❌ Migraciones faltantes: {len(mig_faltantes)}")
    for m in mig_faltantes:
        print(f"   - {m}")
    print("   Ejecuta: python manage.py migrate inventario")
else:
    print("✅ Todas las migraciones aplicadas")

if campos_faltantes_bd:
    print(f"❌ Campos faltantes en BD: {len(campos_faltantes_bd)}")
    for c in campos_faltantes_bd:
        print(f"   - {c}")
else:
    print("✅ Todos los campos existen en BD")

if campos_faltantes_modelo:
    print(f"❌ Campos faltantes en modelo: {len(campos_faltantes_modelo)}")
    for c in campos_faltantes_modelo:
        print(f"   - {c}")
else:
    print("✅ Todos los campos existen en modelo")

if not mig_faltantes and not campos_faltantes_bd and not campos_faltantes_modelo:
    print("\n🎉 TODO ESTÁ CORRECTO")
else:
    print("\n⚠️  HAY PROBLEMAS - Revisa arriba")
print("=" * 60)
