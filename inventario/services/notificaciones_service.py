# inventario/services/notificaciones_service.py
"""
Servicio para enviar notificaciones push usando Firebase Cloud Messaging (FCM)
"""
import os
import requests
import logging
from django.conf import settings
from inventario.models import FCMToken, User

logger = logging.getLogger(__name__)

class NotificacionesService:
    """Servicio para gestionar notificaciones push"""
    
    FCM_URL = 'https://fcm.googleapis.com/fcm/send'
    
    @staticmethod
    def get_server_key():
        """Obtiene la clave del servidor de Firebase desde las variables de entorno"""
        return os.environ.get('FIREBASE_SERVER_KEY', None)
    
    @staticmethod
    def enviar_notificacion_venta(venta):
        """
        Envía notificaciones push a todos los usuarios de la tienda cuando se crea una venta.
        
        Args:
            venta: Instancia del modelo Venta
        """
        server_key = NotificacionesService.get_server_key()
        
        if not server_key:
            logger.warning("FIREBASE_SERVER_KEY no configurada. No se pueden enviar notificaciones.")
            return
        
        # Obtener todos los tokens FCM activos de usuarios de la misma tienda
        usuarios_tienda = User.objects.filter(tienda=venta.tienda, is_active=True)
        tokens = FCMToken.objects.filter(
            user__in=usuarios_tienda,
            activo=True
        ).select_related('user')
        
        if not tokens.exists():
            logger.info(f"No hay tokens FCM registrados para usuarios de la tienda {venta.tienda.nombre}")
            return
        
        # Preparar el mensaje
        titulo = f"💰 Nueva Venta - {venta.tienda.nombre}"
        mensaje = f"Venta de ${venta.total:.2f} - {venta.metodo_pago or 'Sin método de pago'}"
        
        # Datos adicionales para la notificación
        data = {
            'type': 'nueva_venta',
            'venta_id': str(venta.id),
            'tienda_id': str(venta.tienda.id),
            'tienda_nombre': venta.tienda.nombre,
            'total': str(venta.total),
            'metodo_pago': venta.metodo_pago or '',
            'fecha_venta': venta.fecha_venta.isoformat(),
        }
        
        # Enviar notificación a cada token
        headers = {
            'Authorization': f'key={server_key}',
            'Content-Type': 'application/json'
        }
        
        resultados = {'exitosos': 0, 'fallidos': 0, 'tokens_invalidos': []}
        
        for token_obj in tokens:
            payload = {
                'to': token_obj.token,
                'notification': {
                    'title': titulo,
                    'body': mensaje,
                    'icon': '/logo192.png',  # Icono de la app
                    'sound': 'default',
                    'click_action': '/ventas'  # URL a la que redirige al hacer clic
                },
                'data': data,
                'priority': 'high'
            }
            
            try:
                response = requests.post(
                    NotificacionesService.FCM_URL,
                    json=payload,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success', 0) == 1:
                        resultados['exitosos'] += 1
                        logger.info(f"Notificación enviada exitosamente a {token_obj.user.username}")
                    else:
                        resultados['fallidos'] += 1
                        # Si el token es inválido, marcarlo como inactivo
                        if 'InvalidRegistration' in str(result) or 'NotRegistered' in str(result):
                            token_obj.activo = False
                            token_obj.save()
                            resultados['tokens_invalidos'].append(str(token_obj.id))
                        logger.warning(f"Error al enviar notificación: {result}")
                else:
                    resultados['fallidos'] += 1
                    logger.error(f"Error HTTP {response.status_code} al enviar notificación: {response.text}")
                    
            except Exception as e:
                resultados['fallidos'] += 1
                logger.error(f"Excepción al enviar notificación a {token_obj.user.username}: {str(e)}")
        
        logger.info(
            f"Notificaciones de venta enviadas: {resultados['exitosos']} exitosas, "
            f"{resultados['fallidos']} fallidas, {len(resultados['tokens_invalidos'])} tokens inválidos"
        )
        
        return resultados
    
    @staticmethod
    def registrar_token(user, token, device_info=None):
        """
        Registra o actualiza un token FCM para un usuario.
        
        Args:
            user: Instancia del modelo User
            token: Token FCM del dispositivo
            device_info: Información opcional del dispositivo
        
        Returns:
            Tuple (fcm_token_obj, created) donde created es True si se creó nuevo
        """
        fcm_token, created = FCMToken.objects.update_or_create(
            token=token,
            defaults={
                'user': user,
                'device_info': device_info,
                'activo': True
            }
        )
        return fcm_token, created
    
    @staticmethod
    def eliminar_token(token):
        """
        Elimina o desactiva un token FCM.
        
        Args:
            token: Token FCM a eliminar
        """
        try:
            fcm_token = FCMToken.objects.get(token=token)
            fcm_token.activo = False
            fcm_token.save()
            return True
        except FCMToken.DoesNotExist:
            return False
