#!/usr/bin/env python
"""
Script rápido para verificar cuántas categorías de Mercado Libre hay en la base de datos
Uso: python manage.py shell < scripts/verificar_categorias_ml.py
O ejecutar directamente: python scripts/verificar_categorias_ml.py
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
django.setup()

from inventario.models import CategoriaMercadoLibre

# Verificar categorías
total = CategoriaMercadoLibre.objects.count()
total_hoja = CategoriaMercadoLibre.objects.filter(is_leaf=True).count()
total_raiz = CategoriaMercadoLibre.objects.filter(parent_id__isnull=True).count()

print("\n" + "=" * 60)
print("📊 ESTADÍSTICAS DE CATEGORÍAS DE MERCADO LIBRE")
print("=" * 60)
print(f"✅ Total de categorías: {total:,}")
print(f"🍃 Categorías hoja (sin subcategorías): {total_hoja:,}")
print(f"🌳 Categorías raíz: {total_raiz:,}")
print("=" * 60)

# Verificar por site_id
sites = CategoriaMercadoLibre.objects.values_list('site_id', flat=True).distinct()
print(f"\n🌍 Sites disponibles: {', '.join(sites) or 'Ninguno'}")

for site in sites:
    count = CategoriaMercadoLibre.objects.filter(site_id=site).count()
    count_hoja = CategoriaMercadoLibre.objects.filter(site_id=site, is_leaf=True).count()
    print(f"   {site}: {count:,} categorías ({count_hoja:,} hojas)")

# Mostrar algunas categorías hoja como ejemplo
print("\n📋 Ejemplos de categorías hoja (primeras 10):")
categorias_ejemplo = CategoriaMercadoLibre.objects.filter(is_leaf=True).order_by('nombre')[:10]
for cat in categorias_ejemplo:
    print(f"   • {cat.nombre} ({cat.id})")

if total_hoja > 10:
    print(f"   ... y {total_hoja - 10:,} más")

# Verificar si hay suficientes categorías
print("\n" + "=" * 60)
if total_hoja < 100:
    print("⚠️  ADVERTENCIA: Parece que hay muy pocas categorías hoja.")
    print("   Se esperan al menos 1,000-2,000 categorías hoja para MLA (Argentina).")
    print("   Considera re-ejecutar: python manage.py actualizar_categorias_ml --site_id MLA")
elif total_hoja < 1000:
    print("⚠️  ADVERTENCIA: Hay menos categorías de las esperadas.")
    print("   Se esperan al menos 1,000-2,000 categorías hoja para MLA (Argentina).")
    print("   Puede que el comando se haya interrumpido.")
else:
    print("✅ Parece que hay una cantidad razonable de categorías.")
print("=" * 60 + "\n")
