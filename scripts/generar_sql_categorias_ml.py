#!/usr/bin/env python
"""
Script para generar un archivo SQL con todas las categorías de Mercado Libre
Este script descarga las categorías desde la API y genera un archivo SQL que puedes
ejecutar directamente en DBeaver o en la base de datos de producción.

Uso:
    python scripts/generar_sql_categorias_ml.py --site_id MLA --output categorias_ml.sql
"""
import requests
import gzip
import json
import argparse
import sys
from datetime import datetime
from pathlib import Path

def escape_sql_string(s):
    """Escapa strings para SQL"""
    if s is None:
        return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"

def escape_json_for_sql(data):
    """Convierte un objeto Python a JSON string escapado para SQL"""
    if data is None:
        return 'NULL'
    json_str = json.dumps(data, ensure_ascii=False)
    return escape_sql_string(json_str)

def download_categories(site_id='MLA'):
    """Descarga todas las categorías desde la API de Mercado Libre"""
    url = f'https://api.mercadolibre.com/sites/{site_id}/categories/all'
    
    print(f"📥 Descargando categorías desde: {url}")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    
    # Intentar detectar si la respuesta está comprimida
    content_encoding = response.headers.get('content-encoding', '').lower()
    
    if content_encoding == 'gzip' or response.content[:2] == b'\x1f\x8b':
        try:
            content = gzip.decompress(response.content)
            categories_data = json.loads(content.decode('utf-8'))
            print('✅ Respuesta descomprimida desde gzip')
        except Exception as e:
            print(f'⚠️  No se pudo descomprimir como gzip, intentando como JSON: {e}')
            categories_data = response.json()
    else:
        categories_data = response.json()
        print('✅ Respuesta recibida como JSON directo')
    
    # Normalizar estructura
    if isinstance(categories_data, dict):
        categories_list = list(categories_data.values())
        print(f'📋 Estructura detectada: diccionario con {len(categories_data)} categorías')
    elif isinstance(categories_data, list):
        categories_list = categories_data
        print(f'📋 Estructura detectada: lista con {len(categories_data)} categorías')
    else:
        raise ValueError(f"Formato de respuesta inesperado: {type(categories_data)}")
    
    return categories_list

def process_category(cat_data, parent_id=None, categories_processed=None):
    """Procesa recursivamente una categoría y sus hijos"""
    if categories_processed is None:
        categories_processed = []
    
    if isinstance(cat_data, str) or not isinstance(cat_data, dict):
        return categories_processed
    
    cat_id = cat_data.get('id')
    if not cat_id:
        return categories_processed
    
    cat_name = cat_data.get('name', '')
    children = cat_data.get('children_categories', [])
    is_leaf = len(children) == 0
    path_from_root = cat_data.get('path_from_root', [])
    total_items = cat_data.get('total_items_in_this_category', 0)
    
    # Agregar categoría a la lista
    categories_processed.append({
        'id': cat_id,
        'nombre': cat_name,
        'site_id': 'MLA',  # Por defecto, puedes ajustarlo
        'parent_id': parent_id,
        'is_leaf': is_leaf,
        'total_items': total_items,
        'path_from_root': path_from_root
    })
    
    # Procesar hijos recursivamente
    for child in children:
        process_category(child, parent_id=cat_id, categories_processed=categories_processed)
    
    return categories_processed

def generate_sql(categories, site_id='MLA', output_file='categorias_ml.sql'):
    """Genera el archivo SQL con todas las categorías"""
    print(f"\n💾 Generando archivo SQL: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # Escribir encabezado
        f.write(f"-- Script SQL para cargar categorías de Mercado Libre\n")
        f.write(f"-- Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"-- Site ID: {site_id}\n")
        f.write(f"-- Total de categorías: {len(categories)}\n\n")
        
        # Verificar si la tabla existe, si no, crearla
        f.write("-- Asegurarse de que la tabla existe\n")
        f.write("-- Si la migración 0017 no se aplicó, ejecuta primero:\n")
        f.write("-- python manage.py migrate inventario 0017\n\n")
        
        # Limpiar categorías existentes (opcional, comentado por defecto)
        f.write("-- Opcional: Limpiar categorías existentes antes de insertar\n")
        f.write("-- DELETE FROM inventario_categoriamercadolibre WHERE site_id = 'MLA';\n\n")
        
        # Generar INSERT statements
        f.write("-- Insertar categorías\n")
        f.write("BEGIN;\n\n")
        
        total_hoja = 0
        for i, cat in enumerate(categories, 1):
            if cat['is_leaf']:
                total_hoja += 1
            
            # Construir el INSERT
            parent_id_sql = escape_sql_string(cat['parent_id']) if cat['parent_id'] else 'NULL'
            path_json = escape_json_for_sql(cat['path_from_root'])
            
            sql = f"""INSERT INTO inventario_categoriamercadolibre (
    id, nombre, site_id, parent_id, is_leaf, total_items, path_from_root, 
    fecha_creacion, fecha_actualizacion
) VALUES (
    {escape_sql_string(cat['id'])},
    {escape_sql_string(cat['nombre'])},
    {escape_sql_string(cat['site_id'])},
    {parent_id_sql},
    {cat['is_leaf']},
    {cat['total_items']},
    {path_json}::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    site_id = EXCLUDED.site_id,
    parent_id = EXCLUDED.parent_id,
    is_leaf = EXCLUDED.is_leaf,
    total_items = EXCLUDED.total_items,
    path_from_root = EXCLUDED.path_from_root,
    fecha_actualizacion = NOW();
"""
            f.write(sql)
            
            if i % 100 == 0:
                print(f"   Procesadas {i}/{len(categories)} categorías...")
        
        f.write("\nCOMMIT;\n\n")
        f.write(f"-- Total de categorías insertadas: {len(categories)}\n")
        f.write(f"-- Categorías hoja: {total_hoja}\n")
    
    print(f"✅ Archivo SQL generado: {output_file}")
    print(f"   Total de categorías: {len(categories):,}")
    print(f"   Categorías hoja: {total_hoja:,}")
    return len(categories), total_hoja

def main():
    parser = argparse.ArgumentParser(description='Generar script SQL con categorías de Mercado Libre')
    parser.add_argument('--site_id', type=str, default='MLA', help='ID del sitio (MLA=Argentina, MLB=Brasil, etc.)')
    parser.add_argument('--output', type=str, default='categorias_ml.sql', help='Nombre del archivo SQL de salida')
    
    args = parser.parse_args()
    
    try:
        print(f"\n🔄 Generando script SQL para categorías de Mercado Libre ({args.site_id})\n")
        
        # Descargar categorías
        categories_list = download_categories(args.site_id)
        
        # Procesar todas las categorías
        print(f"\n💾 Procesando {len(categories_list)} categorías...")
        all_categories = []
        for cat in categories_list:
            process_category(cat, parent_id=None, categories_processed=all_categories)
        
        # Actualizar site_id para todas
        for cat in all_categories:
            cat['site_id'] = args.site_id
        
        # Generar SQL
        total, hoja = generate_sql(all_categories, site_id=args.site_id, output_file=args.output)
        
        print(f"\n✅ ¡Completado!")
        print(f"   Archivo generado: {args.output}")
        print(f"   Total de categorías: {total:,}")
        print(f"   Categorías hoja: {hoja:,}")
        print(f"\n📝 Próximos pasos:")
        print(f"   1. Abre el archivo {args.output} en DBeaver")
        print(f"   2. Conéctate a tu base de datos de producción")
        print(f"   3. Ejecuta el script completo")
        print(f"   4. Verifica que se insertaron todas las categorías")
        
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
