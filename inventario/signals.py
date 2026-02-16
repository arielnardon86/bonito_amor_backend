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
    Sincroniza automáticamente el stock en Mercado Libre cuando cambia en Total Stock.
    Se ejecuta en cada venta desde Total Stock, ajustes de stock, etc.
    Requiere: producto con ml_item_id y tienda con ML configurado.
    """
    # Evitar recursión infinita
    if update_fields and ('ml_item_id' in update_fields or 'ml_sincronizado' in update_fields or 'ml_ultima_sincronizacion' in update_fields):
        return

    # Solo productos vinculados a ML (tienen ml_item_id)
    if not getattr(instance, 'ml_item_id', None):
        return

    # Tienda debe tener ML configurado
    if not hasattr(instance.tienda, 'plataforma_ecommerce') or instance.tienda.plataforma_ecommerce != 'MERCADO_LIBRE':
        return

    if not getattr(instance.tienda, 'ml_access_token', None):
        return

    if created:
        return  # Producto nuevo, no sincronizar (viene de importación ML)

    # Sincronizar stock: siempre que cambie stock (ventas, ajustes manuales, etc.)
    should_sync_stock = (update_fields is None) or ('stock' in update_fields)
    if not should_sync_stock:
        return

    try:
        from .services.mercadolibre_service import MercadoLibreService

        ml_service = MercadoLibreService(instance.tienda)
        ml_service.sync_stock(instance)
        logger.info(f"Stock sincronizado a ML: {instance.nombre} (stock={instance.stock})")
        Producto.objects.filter(id=instance.id).update(ml_ultima_sincronizacion=timezone.now())
    except Exception as e:
        error_msg = str(e)
        if '403' in error_msg or 'UNAUTHORIZED' in error_msg:
            logger.warning(f"Error 403 al sincronizar stock a ML para {instance.nombre}: {e}")
        else:
            logger.error(f"Error al sincronizar stock a ML para {instance.nombre}: {e}")


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
