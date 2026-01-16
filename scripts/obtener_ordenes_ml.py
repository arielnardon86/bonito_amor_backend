#!/usr/bin/env python3
"""
Script para obtener IDs de órdenes reales de Mercado Libre
Uso: python obtener_ordenes_ml.py
"""

import os
import sys
import django

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
django.setup()

from inventario.models import Tienda
from inventario.services.mercadolibre_service import MercadoLibreService
import json
from datetime import datetime, timedelta

def obtener_ordenes_ml(tienda_id=None, limit=10):
    """
    Obtiene las últimas órdenes de Mercado Libre para una tienda
    
    Args:
        tienda_id: UUID de la tienda (opcional, si no se proporciona usa la primera con ML configurado)
        limit: Cantidad de órdenes a obtener (máximo 50)
    """
    try:
        # Obtener la tienda
        if tienda_id:
            tienda = Tienda.objects.get(pk=tienda_id)
        else:
            # Buscar la primera tienda con ML configurado
            tienda = Tienda.objects.filter(
                plataforma_ecommerce='MERCADO_LIBRE',
                ml_access_token__isnull=False
            ).exclude(ml_access_token='').first()
        
        if not tienda:
            print("❌ No se encontró ninguna tienda con Mercado Libre configurado")
            print("\nPor favor, configura Mercado Libre primero o proporciona un tienda_id")
            return
        
        print(f"📦 Tienda: {tienda.nombre}")
        print(f"   ID: {tienda.id}")
        print(f"   User ID ML: {tienda.ml_user_id}")
        print()
        
        # Crear servicio de ML
        ml_service = MercadoLibreService(tienda)
        
        # Verificar que tenga token
        if not ml_service.access_token:
            print("❌ La tienda no tiene token de acceso configurado")
            return
        
        # Obtener órdenes desde la API de Mercado Libre usando el método del servicio
        user_id = tienda.ml_user_id
        if not user_id:
            print("❌ La tienda no tiene ml_user_id configurado")
            return
        
        print(f"🔍 Buscando órdenes para el usuario {user_id}...")
        print()
        
        try:
            # Usar el método del servicio para obtener órdenes
            # Filtrar solo órdenes en estados procesables
            data = ml_service.get_orders(
                limit=limit,
                offset=0,
                status='confirmed,payment_required,payment_in_process'
            )
            
            if not data:
                print("❌ No se pudo obtener las órdenes. Verifica el token de acceso.")
                return
            
            orders = data.get('results', [])
            
            if not orders:
                print("⚠️  No se encontraron órdenes en estados procesables")
                print("\n💡 Intenta buscar órdenes en otros estados o verifica que tengas ventas recientes")
                return
            
            print(f"✅ Se encontraron {len(orders)} órdenes")
            print()
            print("="*60)
            print("  📋 Órdenes Encontradas")
            print("="*60)
            print()
            
            for i, order in enumerate(orders, 1):
                order_id = order.get('id')
                status = order.get('status', 'N/A')
                date_created = order.get('date_created', 'N/A')
                total_amount = order.get('total_amount', 0)
                
                # Obtener información de los items
                order_items = order.get('order_items', [])
                items_count = len(order_items)
                
                print(f"{i}. Orden ID: {order_id}")
                print(f"   Estado: {status}")
                print(f"   Fecha: {date_created}")
                print(f"   Total: ${total_amount}")
                print(f"   Items: {items_count}")
                
                # Mostrar algunos items
                if order_items:
                    print(f"   Productos:")
                    for item in order_items[:3]:  # Mostrar solo los primeros 3
                        item_id = item.get('item', {}).get('id', 'N/A')
                        title = item.get('item', {}).get('title', 'N/A')
                        quantity = item.get('quantity', 0)
                        print(f"      - {title} (x{quantity}) - ML Item ID: {item_id}")
                    if len(order_items) > 3:
                        print(f"      ... y {len(order_items) - 3} más")
                
                print()
            
            print("="*60)
            print("  💡 Cómo usar estos IDs")
            print("="*60)
            print()
            print("Para probar el webhook con una de estas órdenes, usa:")
            print()
            if orders:
                first_order_id = orders[0].get('id')
                print(f"curl -k -X POST \\")
                print(f"  \"https://bonito-amor-backend.onrender.com/api/tiendas/{tienda.id}/mercadolibre/webhook/\" \\")
                print(f"  -H \"Content-Type: application/json\" \\")
                print(f"  -d '{{\"resource\": \"/orders/{first_order_id}\", \"topic\": \"orders\"}}'")
                print()
                print("O usando el script:")
                print(f"./probar_webhook_ml.sh {first_order_id}")
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if e.response.status_code == 401:
                    print("❌ Error de autenticación: El token puede haber expirado")
                    print("   Intenta renovar el token desde la interfaz de integración")
                elif e.response.status_code == 404:
                    print("❌ Endpoint no encontrado. Verifica que la API de ML esté disponible")
                else:
                    print(f"❌ Error HTTP {e.response.status_code}: {e.response.text}")
            else:
                print(f"❌ Error al obtener órdenes: {e}")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            import traceback
            traceback.print_exc()
            
    except Tienda.DoesNotExist:
        print(f"❌ No se encontró la tienda con ID: {tienda_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Función principal"""
    print("="*60)
    print("  🔍 Obtener Órdenes de Mercado Libre")
    print("="*60)
    print()
    
    # Obtener tienda_id de argumentos si se proporciona
    tienda_id = None
    if len(sys.argv) > 1:
        tienda_id = sys.argv[1]
        print(f"📦 Tienda ID proporcionado: {tienda_id}")
        print()
    
    # Obtener limit de argumentos si se proporciona
    limit = 10
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  El segundo argumento debe ser un número. Usando limit=10 por defecto")
    
    obtener_ordenes_ml(tienda_id, limit)

if __name__ == "__main__":
    main()
