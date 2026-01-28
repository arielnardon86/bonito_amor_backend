#!/usr/bin/env python
"""
Script de prueba para la integración con Mercado Libre
Ayuda a probar el flujo OAuth y verificar la configuración
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
from django.conf import settings

def test_mercadolibre_integracion():
    print("=" * 70)
    print("PRUEBA DE INTEGRACIÓN CON MERCADO LIBRE")
    print("=" * 70)
    print()
    
    # Obtener la tienda configurada
    tiendas_ml = Tienda.objects.filter(plataforma_ecommerce='MERCADO_LIBRE')
    
    if not tiendas_ml.exists():
        print("❌ No se encontró ninguna tienda configurada con Mercado Libre")
        print("   Por favor, configura una tienda en el admin primero.")
        return
    
    tienda = tiendas_ml.first()
    print(f"✅ Tienda encontrada: {tienda.nombre}")
    print(f"   ID: {tienda.id}")
    print(f"   App ID: {tienda.ml_app_id or 'NO CONFIGURADO'}")
    print(f"   Modo Test: {tienda.ml_modo_test}")
    print(f"   Sincronización Habilitada: {tienda.ml_sync_habilitado}")
    print()
    
    # Verificar configuración básica
    if not tienda.ml_app_id:
        print("❌ ERROR: ml_app_id no está configurado")
        print("   Ve al admin y configura el App ID de Mercado Libre")
        return
    
    if not tienda.ml_client_secret:
        print("⚠️  ADVERTENCIA: ml_client_secret no está configurado")
        print("   Necesitarás configurarlo para completar el flujo OAuth")
        print()
    
    # Verificar estado de autenticación
    print("-" * 70)
    print("ESTADO DE AUTENTICACIÓN")
    print("-" * 70)
    
    if tienda.ml_access_token:
        print("✅ Access Token configurado")
        print(f"   User ID: {tienda.ml_user_id or 'NO DISPONIBLE'}")
        if tienda.ml_token_expires_at:
            print(f"   Token expira: {tienda.ml_token_expires_at}")
        else:
            print("   ⚠️  Fecha de expiración no disponible")
    else:
        print("❌ No hay Access Token - Necesitas completar el flujo OAuth")
    print()
    
    # Generar URL de autorización
    print("-" * 70)
    print("PASO 1: OBTENER URL DE AUTORIZACIÓN")
    print("-" * 70)
    
    try:
        ml_service = MercadoLibreService(tienda)
        
        # URL de callback (debe coincidir con la configurada en Mercado Libre Developers)
        redirect_uri = "https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/"
        
        print(f"Redirect URI a usar: {redirect_uri}")
        print()
        
        auth_url = ml_service.get_authorization_url(redirect_uri)
        
        print("✅ URL de autorización generada exitosamente")
        print()
        print("📋 PASOS SIGUIENTES:")
        print("   1. Copia esta URL y ábrela en tu navegador:")
        print()
        print(f"   {auth_url}")
        print()
        print("   2. Autoriza la aplicación con tu cuenta de Mercado Libre")
        print()
        print("   3. Después de autorizar, serás redirigido a:")
        print(f"      {redirect_uri}?code=TG-XXXXX")
        print()
        print("   4. Copia el código (code=TG-XXXXX) de la URL")
        print()
        print("   5. Ejecuta este comando para intercambiar el código por tokens:")
        print(f"      python manage.py ml_exchange_code {tienda.id} TG-XXXXX")
        print()
        
    except Exception as e:
        print(f"❌ Error al generar URL de autorización: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Si ya está autenticado, mostrar información adicional
    if tienda.ml_access_token:
        print("-" * 70)
        print("PRUEBAS ADICIONALES (Ya autenticado)")
        print("-" * 70)
        
        try:
            # Probar obtener información del usuario
            print("Probando obtener información del usuario...")
            user_info = ml_service.get_user_info()
            print(f"✅ Usuario autenticado: {user_info.get('nickname', 'N/A')}")
            print(f"   ID: {user_info.get('id', 'N/A')}")
        except Exception as e:
            print(f"⚠️  Error al obtener información del usuario: {e}")
            print("   Puede ser que el token haya expirado")

if __name__ == '__main__':
    test_mercadolibre_integracion()
