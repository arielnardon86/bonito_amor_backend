#!/usr/bin/env python
"""
Script para verificar el estado de las migraciones de Mercado Libre
y si los campos existen en el modelo Tienda.

Ejecutar en el shell de Django en Render:
python manage.py shell < scripts/verificar_migraciones_ml.py

O copiar y pegar el contenido directamente en el shell interactivo:
python manage.py shell
"""
import sys
import os

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
import django
django.setup()

from django.db import connection
from django.core.management import execute_from_command_line
from inventario.models import Tienda

print("=" * 60)
print("VERIFICACIÓN DE MIGRACIONES Y CAMPOS DE MERCADO LIBRE")
print("=" * 60)
print()

# 1. Verificar migraciones aplicadas
print("1. VERIFICANDO MIGRACIONES APLICADAS:")
print("-" * 60)

migraciones_ml = [
    '0014_add_mercadolibre_fields',
    '0015_add_mercadolibre_producto_fields',
    '0016_add_ml_sincronizar_and_categoria',
    '0017_create_categoria_mercadolibre',
    '0018_fix_ml_modo_test_default',
]

from django.db.migrations.recorder import MigrationRecorder
applied_migrations = MigrationRecorder.Migration.objects.filter(
    app='inventario'
).values_list('name', flat=True)

print(f"\nTotal de migraciones de inventario aplicadas: {len(applied_migrations)}")
print(f"\nMigraciones de ML esperadas:")
for mig in migraciones_ml:
    status = "✅ APLICADA" if mig in applied_migrations else "❌ NO APLICADA"
    print(f"  {status}: {mig}")

print()

# 2. Verificar campos en la base de datos
print("2. VERIFICANDO CAMPOS EN LA BASE DE DATOS:")
print("-" * 60)

campos_ml_esperados = [
    'plataforma_ecommerce',
    'ml_app_id',
    'ml_client_secret',
    'ml_modo_test',
    'ml_sync_habilitado',
    'ml_sincronizar_stock',
    'ml_sincronizar_precios',
    'ml_sincronizar_productos',
    'ml_user_id',
    'ml_token_expires_at',
    'ml_access_token',
    'ml_refresh_token',
]

with connection.cursor() as cursor:
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'inventario_tienda'
        AND (column_name LIKE 'ml_%' OR column_name = 'plataforma_ecommerce')
        ORDER BY column_name;
    """)
    columns_db = {row[0]: row[1:] for row in cursor.fetchall()}

print(f"\nCampos encontrados en la base de datos:")
for campo in campos_ml_esperados:
    if campo in columns_db:
        data_type, is_nullable, default = columns_db[campo]
        print(f"  ✅ {campo}: {data_type} (nullable: {is_nullable}, default: {default})")
    else:
        print(f"  ❌ {campo}: NO ENCONTRADO")

print()

# 3. Verificar campos en el modelo Django
print("3. VERIFICANDO CAMPOS EN EL MODELO DJANGO:")
print("-" * 60)

print(f"\nCampos del modelo Tienda:")
model_fields = [f.name for f in Tienda._meta.get_fields() if hasattr(f, 'column')]

for campo in campos_ml_esperados:
    try:
        field = Tienda._meta.get_field(campo)
        field_type = type(field).__name__
        print(f"  ✅ {campo}: {field_type} (existe en el modelo)")
    except Exception as e:
        print(f"  ❌ {campo}: NO EXISTE EN EL MODELO ({type(e).__name__})")

print()

# 4. Intentar acceder a los campos en una tienda de prueba
print("4. VERIFICANDO ACCESO A CAMPOS EN UNA TIENDA:")
print("-" * 60)

try:
    tienda = Tienda.objects.first()
    if tienda:
        print(f"\nUsando tienda de prueba: {tienda.nombre} (ID: {tienda.id})")
        print(f"\nValores actuales de campos ML:")
        for campo in campos_ml_esperados[:8]:  # Solo los primeros 8 para no mostrar tokens
            try:
                valor = getattr(tienda, campo, None)
                print(f"  {campo}: {valor}")
            except Exception as e:
                print(f"  ❌ {campo}: ERROR al acceder - {type(e).__name__}")
    else:
        print("\n⚠️  No hay tiendas en la base de datos")
except Exception as e:
    print(f"\n❌ Error al acceder a las tiendas: {e}")

print()

# 5. Resumen
print("=" * 60)
print("RESUMEN:")
print("=" * 60)

migraciones_faltantes = [m for m in migraciones_ml if m not in applied_migrations]
campos_faltantes_db = [c for c in campos_ml_esperados if c not in columns_db]
campos_faltantes_modelo = []

for campo in campos_ml_esperados:
    try:
        Tienda._meta.get_field(campo)
    except:
        campos_faltantes_modelo.append(campo)

if migraciones_faltantes:
    print(f"\n❌ Migraciones NO aplicadas ({len(migraciones_faltantes)}):")
    for mig in migraciones_faltantes:
        print(f"   - {mig}")
else:
    print(f"\n✅ Todas las migraciones de ML están aplicadas")

if campos_faltantes_db:
    print(f"\n❌ Campos NO encontrados en la base de datos ({len(campos_faltantes_db)}):")
    for campo in campos_faltantes_db:
        print(f"   - {campo}")
else:
    print(f"\n✅ Todos los campos existen en la base de datos")

if campos_faltantes_modelo:
    print(f"\n❌ Campos NO encontrados en el modelo Django ({len(campos_faltantes_modelo)}):")
    for campo in campos_faltantes_modelo:
        print(f"   - {campo}")
else:
    print(f"\n✅ Todos los campos existen en el modelo Django")

if not migraciones_faltantes and not campos_faltantes_db and not campos_faltantes_modelo:
    print("\n🎉 TODO ESTÁ CORRECTO - Los campos de ML están disponibles")
    print("\nSi aún no ves los campos en el admin, el problema podría ser:")
    print("  1. Caché del navegador (haz hard refresh con Cmd+Shift+R)")
    print("  2. El código del admin no está actualizado (verifica el deploy)")
else:
    print("\n⚠️  HAY PROBLEMAS - Revisa los puntos anteriores")
    if migraciones_faltantes:
        print("\nSOLUCIÓN: Ejecuta las migraciones faltantes:")
        print("  python manage.py migrate inventario")

print("=" * 60)
