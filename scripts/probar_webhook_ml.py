#!/usr/bin/env python3
"""
Script para probar el webhook de Mercado Libre
Permite probar el endpoint y ver qué información devuelve
"""

import requests
import json
import sys
from datetime import datetime

# Configuración
TIENDA_ID = "e265d339-39ec-4ec5-a73c-d5a31904d29a"
BASE_URL = "https://bonito-amor-backend.onrender.com"
WEBHOOK_URL = f"{BASE_URL}/api/tiendas/{TIENDA_ID}/mercadolibre/webhook/"

def print_section(title):
    """Imprime un título de sección"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")

def test_get_webhook():
    """Prueba el endpoint GET (validación de Mercado Libre)"""
    print_section("1. Probando GET (Validación de Mercado Libre)")
    
    try:
        response = requests.get(WEBHOOK_URL, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"\nRespuesta:")
        
        try:
            data = response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except:
            print(response.text)
        
        if response.status_code == 200:
            print("\n✅ GET exitoso - El endpoint está configurado correctamente")
        else:
            print(f"\n⚠️ GET devolvió código {response.status_code}")
        
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al hacer GET: {e}")
        return False

def test_post_webhook(order_id=None):
    """Prueba el endpoint POST con una notificación simulada"""
    print_section("2. Probando POST (Notificación de Mercado Libre)")
    
    # Si no se proporciona un order_id, usar uno de ejemplo
    if not order_id:
        order_id = "123456789"  # ID de ejemplo
        print(f"⚠️ Usando ID de orden de ejemplo: {order_id}")
        print("   Para probar con una orden real, proporciona el ID como argumento:")
        print(f"   python {sys.argv[0]} <ORDER_ID>")
    else:
        print(f"📦 Usando ID de orden: {order_id}")
    
    # Estructura típica de notificación de Mercado Libre
    payload = {
        "resource": f"/orders/{order_id}",
        "topic": "orders"
    }
    
    print(f"\nPayload enviado:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"\nRespuesta:")
        
        try:
            data = response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except:
            print(response.text)
        
        if response.status_code == 200:
            print("\n✅ POST exitoso - La notificación fue procesada")
            
            # Verificar si hay información útil en la respuesta
            try:
                data = response.json()
                if 'status' in data:
                    if data['status'] == 'success':
                        print("✅ La orden fue procesada correctamente")
                    elif data['status'] == 'error':
                        print(f"⚠️ Hubo un error: {data.get('message', 'Error desconocido')}")
                    elif data['status'] == 'skipped':
                        print(f"ℹ️ La orden fue omitida: {data.get('message', 'Razón desconocida')}")
            except:
                pass
        else:
            print(f"\n⚠️ POST devolvió código {response.status_code}")
        
        return response.status_code == 200
        
    except requests.exceptions.Timeout:
        print("❌ Timeout - El servidor tardó demasiado en responder")
        print("   Esto puede indicar que el webhook está procesando la orden...")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al hacer POST: {e}")
        return False

def test_with_custom_payload():
    """Permite probar con un payload personalizado"""
    print_section("3. Prueba con Payload Personalizado")
    
    # Ejemplo de diferentes tipos de notificaciones que ML puede enviar
    test_cases = [
        {
            "name": "Notificación de orden confirmada",
            "payload": {
                "resource": "/orders/123456789",
                "topic": "orders"
            }
        },
        {
            "name": "Notificación de pago",
            "payload": {
                "resource": "/payments/123456789",
                "topic": "payments"
            }
        },
        {
            "name": "Notificación de item",
            "payload": {
                "resource": "/items/MLA123456789",
                "topic": "items"
            }
        }
    ]
    
    print("Casos de prueba disponibles:")
    for i, test_case in enumerate(test_cases, 1):
        print(f"  {i}. {test_case['name']}")
    
    print("\nNota: El webhook actualmente solo procesa notificaciones de tipo 'orders'")
    print("      Otras notificaciones serán recibidas pero no procesadas")

def main():
    """Función principal"""
    print_section("🧪 Prueba de Webhook de Mercado Libre")
    print(f"URL: {WEBHOOK_URL}")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Obtener order_id de los argumentos si se proporciona
    order_id = None
    if len(sys.argv) > 1:
        order_id = sys.argv[1]
        print(f"\n📦 ID de orden proporcionado: {order_id}")
    
    # Ejecutar pruebas
    get_success = test_get_webhook()
    post_success = test_post_webhook(order_id)
    
    # Resumen
    print_section("📊 Resumen")
    print(f"GET (Validación):  {'✅ Exitoso' if get_success else '❌ Falló'}")
    print(f"POST (Notificación): {'✅ Exitoso' if post_success else '❌ Falló'}")
    
    if get_success and post_success:
        print("\n✅ Todas las pruebas pasaron correctamente")
    elif get_success:
        print("\n⚠️ GET funciona, pero POST puede tener problemas")
        print("   Revisa los logs del servidor para más detalles")
    else:
        print("\n❌ El endpoint no está respondiendo correctamente")
        print("   Verifica que:")
        print("   1. El servidor esté corriendo")
        print("   2. La URL sea correcta")
        print("   3. El ID de tienda sea válido")
    
    # Información adicional
    print("\n" + "="*60)
    print("💡 Información Adicional")
    print("="*60)
    print("\nPara ver los logs del servidor en Render:")
    print("  1. Ve a tu dashboard de Render")
    print("  2. Selecciona tu servicio")
    print("  3. Ve a la pestaña 'Logs'")
    print("\nPara probar con una orden real de Mercado Libre:")
    print("  1. Obtén el ID de una orden real desde tu cuenta de ML")
    print(f"  2. Ejecuta: python {sys.argv[0]} <ORDER_ID_REAL>")
    print("\nPara probar con curl:")
    print(f'  curl -X GET "{WEBHOOK_URL}"')
    print(f'  curl -X POST "{WEBHOOK_URL}" \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"resource": "/orders/123456789", "topic": "orders"}\'')

if __name__ == "__main__":
    main()
