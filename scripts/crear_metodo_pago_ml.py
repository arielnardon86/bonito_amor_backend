#!/usr/bin/env python
"""
Script para crear o actualizar el método de pago 'Mercado Libre'
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mi_tienda_backend.settings')
django.setup()

from inventario.models import MetodoPago

def crear_metodo_pago_ml():
    """Crea o actualiza el método de pago 'Mercado Libre'"""
    try:
        metodo_ml, created = MetodoPago.objects.get_or_create(
            nombre='Mercado Libre',
            defaults={
                'descripcion': 'Ventas realizadas a través de Mercado Libre',
                'activo': True,
                'es_financiero': True  # Tiene aranceles configurables por categoría
            }
        )
        
        if created:
            print("✅ Método de pago 'Mercado Libre' creado exitosamente")
            print(f"   ID: {metodo_ml.id}")
            print(f"   Nombre: {metodo_ml.nombre}")
            print(f"   Activo: {metodo_ml.activo}")
            print(f"   Es financiero: {metodo_ml.es_financiero}")
        else:
            # Asegurar que esté marcado como financiero y activo
            updated = False
            if not metodo_ml.es_financiero:
                metodo_ml.es_financiero = True
                updated = True
            if not metodo_ml.activo:
                metodo_ml.activo = True
                updated = True
            
            if updated:
                metodo_ml.save()
                print("✅ Método de pago 'Mercado Libre' actualizado")
                print(f"   ID: {metodo_ml.id}")
                print(f"   Nombre: {metodo_ml.nombre}")
                print(f"   Activo: {metodo_ml.activo}")
                print(f"   Es financiero: {metodo_ml.es_financiero}")
            else:
                print("ℹ️  Método de pago 'Mercado Libre' ya existe y está configurado correctamente")
                print(f"   ID: {metodo_ml.id}")
                print(f"   Nombre: {metodo_ml.nombre}")
                print(f"   Activo: {metodo_ml.activo}")
                print(f"   Es financiero: {metodo_ml.es_financiero}")
        
        return metodo_ml
    except Exception as e:
        print(f"❌ Error al crear/actualizar método de pago 'Mercado Libre': {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    crear_metodo_pago_ml()
