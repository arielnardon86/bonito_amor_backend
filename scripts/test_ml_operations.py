#!/usr/bin/env python
"""
Script para probar operaciones básicas con Mercado Libre después de la autenticación
Uso: python manage.py test_ml_operations [tienda_id]
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
django.setup()

from inventario.models import Tienda
from inventario.services.mercadolibre_service import MercadoLibreService

def test_ml_operations(tienda_id=None):
    print("=" * 70)
    print("PRUEBA DE OPERACIONES CON MERCADO LIBRE")
    print("=" * 70)
    print()
    
    # Obtener tienda
    if tienda_id:
        try:
            tienda = Tienda.objects.get(id=tienda_id)
        except Tienda.DoesNotExist:
            print(f"❌ Tienda con ID {tienda_id} no encontrada")
            return
    else:
        tienda = Tienda.objects.filter(plataforma_ecommerce='MERCADO_LIBRE').first()
        if not tienda:
            print("❌ No se encontró ninguna tienda configurada con Mercado Libre")
            return
    
    print(f"📦 Tienda: {tienda.nombre} (ID: {tienda.id})")
    print()
    
    # Verificar autenticación
    if not tienda.ml_access_token:
        print("❌ No hay token de acceso. Debes completar el flujo OAuth primero.")
        return
    
    print("✅ Token de acceso configurado")
    print(f"   User ID: {tienda.ml_user_id}")
    print()
    
    try:
        ml_service = MercadoLibreService(tienda)
        
        # Prueba 1: Obtener información del usuario
        print("-" * 70)
        print("PRUEBA 1: Obtener información del usuario")
        print("-" * 70)
        try:
            user_info = ml_service.get_user_info()
            print("✅ Información del usuario obtenida:")
            print(f"   Nickname: {user_info.get('nickname', 'N/A')}")
            print(f"   ID: {user_info.get('id', 'N/A')}")
            print(f"   Email: {user_info.get('email', 'N/A')}")
            print(f"   Site ID: {user_info.get('site_id', 'N/A')}")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()
        
        # Prueba 2: Obtener items/publicaciones del vendedor
        print("-" * 70)
        print("PRUEBA 2: Obtener productos/publicaciones en Mercado Libre")
        print("-" * 70)
        try:
            items = ml_service.get_items(limit=5)
            if 'results' in items:
                item_ids = items['results']
                print(f"✅ Encontrados {len(item_ids)} items activos")
                if item_ids:
                    print(f"   Primeros items: {item_ids[:3]}")
                    # Obtener detalles del primer item
                    if len(item_ids) > 0:
                        print()
                        print("   Detalles del primer item:")
                        item_detail = ml_service.get_item(item_ids[0])
                        print(f"     ID: {item_detail.get('id')}")
                        print(f"     Título: {item_detail.get('title', 'N/A')}")
                        print(f"     Precio: ${item_detail.get('price', 'N/A')}")
                        print(f"     Stock: {item_detail.get('available_quantity', 'N/A')}")
                        print(f"     Estado: {item_detail.get('status', 'N/A')}")
                else:
                    print("   ⚠️  No hay productos publicados en Mercado Libre aún")
            else:
                print(f"⚠️  Respuesta inesperada: {items}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        print()
        
        # Prueba 3: Obtener categorías
        print("-" * 70)
        print("PRUEBA 3: Obtener categorías disponibles (MLA = Argentina)")
        print("-" * 70)
        try:
            categories = ml_service.get_categories('MLA')
            if categories and len(categories) > 0:
                print(f"✅ Categorías obtenidas: {len(categories)} disponibles")
                print(f"   Primeras 5 categorías:")
                for cat in categories[:5]:
                    print(f"     - {cat.get('name', 'N/A')} (ID: {cat.get('id', 'N/A')})")
            else:
                print("⚠️  No se pudieron obtener categorías")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()
        
        print("=" * 70)
        print("✅ PRUEBAS COMPLETADAS")
        print("=" * 70)
        print()
        print("Próximos pasos:")
        print("  1. Implementar sincronización de productos bidireccional")
        print("  2. Crear mapeo de categorías entre Total Stock y Mercado Libre")
        print("  3. Implementar sincronización automática de stock")
        print("  4. Crear interfaz frontend para gestionar la integración")
        print()
        
    except Exception as e:
        print(f"❌ Error general: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    import sys
    tienda_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_ml_operations(tienda_id)
