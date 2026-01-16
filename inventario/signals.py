"""
Signals para sincronización automática con Mercado Libre
"""
import logging
from django.db.models.signals import post_save, pre_save, post_migrate
from django.dispatch import receiver
from django.utils import timezone
from django.apps import apps
from .models import Producto, Tienda, MetodoPago

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Producto)
def sync_producto_to_mercadolibre(sender, instance, created, update_fields, **kwargs):
    """
    Sincroniza automáticamente el producto con Mercado Libre cuando:
    - El producto está marcado como sincronizado (ml_sincronizado=True)
    - La tienda tiene habilitada la sincronización automática
    - Se actualiza stock o precio (si está habilitado)
    """
    # Evitar recursión infinita si el save es disparado por la propia sincronización
    if update_fields and ('ml_item_id' in update_fields or 'ml_sincronizado' in update_fields or 'ml_ultima_sincronizacion' in update_fields):
        return
    
    # Solo sincronizar si el producto ya está vinculado a ML
    if not instance.ml_sincronizado or not instance.ml_item_id:
        return
    
    # Verificar que la tienda tenga ML configurado y sincronización habilitada
    if not hasattr(instance.tienda, 'plataforma_ecommerce'):
        return
    
    if instance.tienda.plataforma_ecommerce != 'MERCADO_LIBRE':
        return
    
    if not getattr(instance.tienda, 'ml_sync_habilitado', False):
        return
    
    if not getattr(instance.tienda, 'ml_access_token', None):
        logger.warning(f"No hay token de acceso ML para tienda {instance.tienda.id}")
        return
    
    # Si el producto acaba de ser creado y sincronizado, no intentar actualizar inmediatamente
    # ML puede tener restricciones temporales después de crear un item
    # Solo actualizar si hay cambios específicos en stock o precio
    if created:
        # Si es un producto nuevo que acaba de ser sincronizado, no hacer nada
        # La sincronización inicial ya se hizo en sync_producto_to_ml
        logger.debug(f"Producto {instance.id} acaba de ser creado, omitiendo actualización automática inmediata")
        return
    
    try:
        from .services.mercadolibre_service import MercadoLibreService
        
        ml_service = MercadoLibreService(instance.tienda)
        
        # Solo sincronizar si hay cambios específicos en stock o precio
        # Si update_fields está disponible, solo sincronizar los campos que cambiaron
        should_sync_stock = False
        should_sync_price = False
        
        if update_fields:
            should_sync_stock = 'stock' in update_fields and getattr(instance.tienda, 'ml_sincronizar_stock', True)
            should_sync_price = 'precio' in update_fields and getattr(instance.tienda, 'ml_sincronizar_precios', True)
        else:
            # Si no hay update_fields, sincronizar ambos por seguridad
            should_sync_stock = getattr(instance.tienda, 'ml_sincronizar_stock', True)
            should_sync_price = getattr(instance.tienda, 'ml_sincronizar_precios', True)
        
        # Sincronizar stock si está habilitado y cambió
        if should_sync_stock:
            try:
                ml_service.sync_stock(instance)
                logger.info(f"Stock sincronizado automáticamente para producto {instance.id}")
            except Exception as e:
                # Si es un error 403, puede ser una restricción temporal de ML
                error_msg = str(e)
                if '403' in error_msg or 'UNAUTHORIZED' in error_msg:
                    logger.warning(f"Error 403 al sincronizar stock para producto {instance.id}: {e}. Puede ser una restricción temporal de ML.")
                else:
                    logger.error(f"Error al sincronizar stock para producto {instance.id}: {e}")
        
        # Sincronizar precio si está habilitado y cambió
        if should_sync_price:
            try:
                ml_service.sync_precio(instance)
                logger.info(f"Precio sincronizado automáticamente para producto {instance.id}")
            except Exception as e:
                # Si es un error 403, puede ser una restricción temporal de ML
                error_msg = str(e)
                if '403' in error_msg or 'UNAUTHORIZED' in error_msg:
                    logger.warning(f"Error 403 al sincronizar precio para producto {instance.id}: {e}. Puede ser una restricción temporal de ML.")
                else:
                    logger.error(f"Error al sincronizar precio para producto {instance.id}: {e}")
        
        # Actualizar fecha de última sincronización solo si hubo una sincronización exitosa
        if should_sync_stock or should_sync_price:
            instance.ml_ultima_sincronizacion = timezone.now()
            # Usar update para evitar recursión infinita del signal
            Producto.objects.filter(id=instance.id).update(
                ml_ultima_sincronizacion=instance.ml_ultima_sincronizacion
            )
        
    except Exception as e:
        logger.error(f"Error general al sincronizar producto {instance.id} con ML: {e}", exc_info=True)


@receiver(post_migrate)
def crear_metodo_pago_mercadolibre(sender, **kwargs):
    """
    Crea automáticamente el método de pago 'Mercado Libre' si no existe.
    Se ejecuta después de cada migración.
    """
    # Solo ejecutar para la app 'inventario'
    if sender.name != 'inventario':
        return
    
    try:
        MetodoPago = apps.get_model('inventario', 'MetodoPago')
        metodo_ml, created = MetodoPago.objects.get_or_create(
            nombre='Mercado Libre',
            defaults={
                'descripcion': 'Ventas realizadas a través de Mercado Libre',
                'activo': True,
                'es_financiero': True  # Tiene aranceles configurables por categoría
            }
        )
        if created:
            logger.info("✅ Método de pago 'Mercado Libre' creado automáticamente")
        else:
            # Asegurar que esté marcado como financiero
            if not metodo_ml.es_financiero:
                metodo_ml.es_financiero = True
                metodo_ml.save()
                logger.info("✅ Método de pago 'Mercado Libre' actualizado: marcado como financiero")
    except Exception as e:
        logger.error(f"Error al crear método de pago 'Mercado Libre': {e}", exc_info=True)
