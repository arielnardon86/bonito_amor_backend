"""
Comando de Django para descargar y actualizar categorías de Mercado Libre
Uso: python manage.py actualizar_categorias_ml [--site_id MLA]
"""
import requests
import gzip
import json
import logging
from django.core.management.base import BaseCommand
from inventario.models import CategoriaMercadoLibre

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Descarga y actualiza todas las categorías de Mercado Libre desde la API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--site_id',
            type=str,
            default='MLA',
            help='ID del sitio de Mercado Libre (MLA=Argentina, MLB=Brasil, etc.)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar actualización incluso si las categorías ya existen'
        )

    def handle(self, *args, **options):
        site_id = options['site_id']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS(f'\n🔄 Descargando categorías de Mercado Libre para {site_id}...\n'))
        
        try:
            # Descargar todas las categorías desde el endpoint oficial
            url = f'https://api.mercadolibre.com/sites/{site_id}/categories/all'
            
            self.stdout.write(f'📥 Descargando desde: {url}')
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Intentar detectar si la respuesta está comprimida con gzip
            # La API de ML puede devolver JSON comprimido o sin comprimir
            content_encoding = response.headers.get('content-encoding', '').lower()
            
            if content_encoding == 'gzip' or response.content[:2] == b'\x1f\x8b':  # Magic number de gzip
                try:
                    content = gzip.decompress(response.content)
                    categories_data = json.loads(content.decode('utf-8'))
                    self.stdout.write('✅ Respuesta descomprimida desde gzip')
                except Exception as e:
                    # Si falla la descompresión, intentar como JSON directo
                    self.stdout.write(f'⚠️  No se pudo descomprimir como gzip, intentando como JSON: {e}')
                    categories_data = response.json()
            else:
                # La respuesta viene como JSON directo
                categories_data = response.json()
                self.stdout.write('✅ Respuesta recibida como JSON directo')
            
            # La respuesta puede ser un diccionario donde las claves son los IDs de las categorías
            # o una lista de categorías. Necesitamos normalizar esto.
            if isinstance(categories_data, dict):
                # Si es un diccionario, convertir a lista de valores
                categories_list = list(categories_data.values())
                self.stdout.write(f'📋 Estructura detectada: diccionario con {len(categories_data)} categorías')
            elif isinstance(categories_data, list):
                categories_list = categories_data
                self.stdout.write(f'📋 Estructura detectada: lista con {len(categories_data)} categorías')
            else:
                raise ValueError(f"Formato de respuesta inesperado: {type(categories_data)}")
            
            self.stdout.write(self.style.SUCCESS(f'✅ Procesando {len(categories_list)} categorías\n'))
            
            # Procesar y guardar categorías
            saved_count = 0
            updated_count = 0
            leaf_count = 0
            
            def process_category(cat_data, parent_id=None, depth=0):
                """Procesa recursivamente una categoría y sus hijos"""
                nonlocal saved_count, updated_count, leaf_count
                
                # Si cat_data es un string (ID), necesitamos obtener la información completa
                if isinstance(cat_data, str):
                    # Es solo un ID, necesitamos obtener la información de la categoría
                    # Por ahora, saltamos estas categorías ya que no tenemos la info completa
                    return
                
                # Verificar que sea un diccionario
                if not isinstance(cat_data, dict):
                    self.stdout.write(self.style.WARNING(f'⚠️  Categoría con formato inesperado: {type(cat_data)}'))
                    return
                
                cat_id = cat_data.get('id')
                if not cat_id:
                    # Si no tiene ID, intentar usar la clave si es un diccionario anidado
                    return
                
                cat_name = cat_data.get('name', '')
                children = cat_data.get('children_categories', [])
                is_leaf = len(children) == 0
                path_from_root = cat_data.get('path_from_root', [])
                total_items = cat_data.get('total_items_in_this_category', 0)
                
                if is_leaf:
                    leaf_count += 1
                
                # Crear o actualizar la categoría
                categoria, created = CategoriaMercadoLibre.objects.update_or_create(
                    id=cat_id,
                    defaults={
                        'nombre': cat_name,
                        'site_id': site_id,
                        'parent_id': parent_id,
                        'is_leaf': is_leaf,
                        'total_items': total_items,
                        'path_from_root': path_from_root,
                    }
                )
                
                if created:
                    saved_count += 1
                    if depth == 0:
                        self.stdout.write(f'  ✅ Guardada: {cat_name} ({cat_id})')
                else:
                    updated_count += 1
                
                # Procesar categorías hijas recursivamente
                for child in children:
                    process_category(child, parent_id=cat_id, depth=depth + 1)
            
            # Procesar todas las categorías
            self.stdout.write('💾 Guardando categorías en la base de datos...\n')
            
            for cat in categories_list:
                process_category(cat)
            
            # Resumen
            self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
            self.stdout.write(self.style.SUCCESS('✅ Actualización completada\n'))
            self.stdout.write(f'   📊 Total de categorías: {len(categories_data)}')
            self.stdout.write(f'   ➕ Nuevas categorías: {saved_count}')
            self.stdout.write(f'   🔄 Categorías actualizadas: {updated_count}')
            self.stdout.write(f'   🍃 Categorías hoja: {leaf_count}')
            self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))
            
            # Mostrar algunas categorías hoja como ejemplo
            self.stdout.write('\n📋 Ejemplos de categorías hoja disponibles:\n')
            categorias_hoja = CategoriaMercadoLibre.objects.filter(
                site_id=site_id,
                is_leaf=True
            ).order_by('nombre')[:20]
            
            for cat in categorias_hoja:
                self.stdout.write(f'   • {cat.nombre} ({cat.id})')
            
            if categorias_hoja.count() > 20:
                self.stdout.write(f'   ... y {categorias_hoja.count() - 20} más\n')
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error al descargar categorías: {e}\n'))
            if hasattr(e, 'response') and e.response is not None:
                self.stdout.write(self.style.ERROR(f'   Respuesta: {e.response.text[:200]}\n'))
            return
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error inesperado: {e}\n'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
            return
