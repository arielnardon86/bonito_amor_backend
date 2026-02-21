# inventario/services/notificaciones_service.py
"""
Servicio para enviar notificaciones push usando Firebase Cloud Messaging (FCM).
Usa la API HTTP v1 (Firebase Admin SDK) para compatibilidad con Safari PWA y navegadores web.
"""
import os
import json
import logging
from inventario.models import FCMToken, User

logger = logging.getLogger(__name__)

# Firebase Admin (v1) - inicialización perezosa
_firebase_app = None


def _get_firebase_app():
    """Inicializa Firebase Admin una sola vez. Usa FCM v1 (compatible con Safari/Web)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', '').strip()
    json_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning(
            "firebase-admin no instalado. Para notificaciones en Safari PWA añade "
            "'firebase-admin' a requirements y configura FIREBASE_SERVICE_ACCOUNT_*."
        )
        return None

    if path and os.path.isfile(path):
        cred = credentials.Certificate(path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin inicializado con FIREBASE_SERVICE_ACCOUNT_PATH (FCM v1)")
        return _firebase_app

    if json_str:
        try:
            if json_str.startswith('{'):
                info = json.loads(json_str)
            else:
                import base64
                info = json.loads(base64.b64decode(json_str).decode('utf-8'))
            cred = credentials.Certificate(info)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin inicializado con FIREBASE_SERVICE_ACCOUNT_JSON (FCM v1)")
            return _firebase_app
        except json.JSONDecodeError as e:
            logger.error("FIREBASE_SERVICE_ACCOUNT_JSON no es JSON válido: %s", e)
            return None
        except Exception as e:
            logger.exception("Error al cargar FIREBASE_SERVICE_ACCOUNT_JSON: %s", e)
            return None

    logger.info(
        "FCM v1 no configurado: definir FIREBASE_SERVICE_ACCOUNT_JSON o FIREBASE_SERVICE_ACCOUNT_PATH en el servidor."
    )
    return None


def _enviar_v1(venta, tokens, titulo, mensaje, data):
    """Envía notificaciones usando Firebase Admin SDK (FCM HTTP v1). Compatible con Safari/Web."""
    from firebase_admin import messaging

    app = _get_firebase_app()
    if not app:
        return {'exitosos': 0, 'fallidos': len(tokens), 'tokens_invalidos': []}

    resultados = {'exitosos': 0, 'fallidos': 0, 'tokens_invalidos': []}
    data_str = {k: str(v) for k, v in data.items()}

    for token_obj in tokens:
        try:
            # Mensaje data-only: sin payload "notification" para que FCM no lo maneje
            # automáticamente en background y siempre pase por el service worker.
            # El SW lee title/body desde data['title'] y data['body'].
            data_with_notif = dict(data_str)
            data_with_notif.setdefault('title', titulo)
            data_with_notif.setdefault('body', mensaje)
            message = messaging.Message(
                token=token_obj.token,
                data=data_with_notif,
                webpush=messaging.WebpushConfig(
                    headers={'Urgency': 'high'},
                ),
            )
            msg_id = messaging.send(message)
            resultados['exitosos'] += 1
            logger.info("Notificación v1 enviada a %s (message_id=%s)", token_obj.user.username, msg_id)
        except messaging.UnregisteredError:
            resultados['fallidos'] += 1
            resultados['tokens_invalidos'].append(str(token_obj.id))
            token_obj.activo = False
            token_obj.save()
            logger.warning("Token inválido o no registrado para %s", token_obj.user.username)
        except messaging.SenderIdMismatchError:
            resultados['fallidos'] += 1
            logger.error("SenderId no coincide para %s (revisa proyecto Firebase)", token_obj.user.username)
        except Exception as e:
            resultados['fallidos'] += 1
            logger.exception("Error al enviar notificación v1 a %s: %s", token_obj.user.username, e)

    return resultados


def _enviar_legacy(venta, tokens, titulo, mensaje, data):
    """Fallback: API legacy (no compatible con Safari/Web en muchos casos)."""
    import requests

    server_key = os.environ.get('FIREBASE_SERVER_KEY', None)
    if not server_key:
        logger.warning("FIREBASE_SERVER_KEY no configurada. Usa FCM v1 con FIREBASE_SERVICE_ACCOUNT_PATH/JSON para Safari.")
        return {'exitosos': 0, 'fallidos': len(tokens), 'tokens_invalidos': []}

    url = 'https://fcm.googleapis.com/fcm/send'
    headers = {'Authorization': f'key={server_key}', 'Content-Type': 'application/json'}
    resultados = {'exitosos': 0, 'fallidos': 0, 'tokens_invalidos': []}

    for token_obj in tokens:
        payload = {
            'to': token_obj.token,
            'notification': {
                'title': titulo,
                'body': mensaje,
                'icon': '/logo192.png',
                'sound': 'default',
                'click_action': '/ventas',
            },
            'data': data,
            'priority': 'high',
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('success', 0) == 1:
                    resultados['exitosos'] += 1
                    logger.info("Notificación (legacy) enviada a %s", token_obj.user.username)
                else:
                    resultados['fallidos'] += 1
                    if 'InvalidRegistration' in str(result) or 'NotRegistered' in str(result):
                        token_obj.activo = False
                        token_obj.save()
                        resultados['tokens_invalidos'].append(str(token_obj.id))
                    logger.warning("Error legacy: %s", result)
            else:
                resultados['fallidos'] += 1
                logger.error("HTTP %s: %s", response.status_code, response.text)
        except Exception as e:
            resultados['fallidos'] += 1
            logger.exception("Excepción enviando (legacy) a %s: %s", token_obj.user.username, e)

    return resultados


class NotificacionesService:
    """Servicio para gestionar notificaciones push (FCM v1 preferido para Safari/Web)."""

    @staticmethod
    def get_server_key():
        """Obtiene la clave del servidor de Firebase (solo para API legacy)."""
        return os.environ.get('FIREBASE_SERVER_KEY', None)

    @staticmethod
    def enviar_notificacion_venta(venta):
        """
        Envía notificaciones push a todos los usuarios de la tienda cuando se crea una venta.
        Usa FCM HTTP v1 si está configurada la cuenta de servicio (recomendado para Safari PWA).
        """
        usuarios_tienda = User.objects.filter(tienda=venta.tienda, is_active=True)
        tokens_qs = (
            FCMToken.objects.filter(
                user__in=usuarios_tienda,
                activo=True,
            )
            .select_related('user')
            .order_by('user_id', '-fecha_actualizacion')
        )
        # Un solo token por usuario (el más reciente) para no duplicar notificaciones
        seen_users = set()
        tokens = []
        for t in tokens_qs:
            if t.user_id in seen_users:
                continue
            seen_users.add(t.user_id)
            tokens.append(t)

        if not tokens:
            logger.info(
                "No hay tokens FCM registrados para usuarios de la tienda %s",
                venta.tienda.nombre,
            )
            return {'exitosos': 0, 'fallidos': 0, 'tokens_invalidos': []}

        titulo = f"Nueva Venta - {venta.tienda.nombre}"
        mensaje = f"Venta de ${venta.total:.2f} - {venta.metodo_pago or 'Sin método de pago'}"

        data = {
            'type': 'nueva_venta',
            'venta_id': str(venta.id),
            'tienda_id': str(venta.tienda.id),
            'tienda_nombre': venta.tienda.nombre,
            'total': str(venta.total),
            'metodo_pago': venta.metodo_pago or '',
            'fecha_venta': venta.fecha_venta.isoformat(),
        }

        firebase_app = _get_firebase_app()
        if firebase_app is not None:
            resultados = _enviar_v1(venta, tokens, titulo, mensaje, data)
        else:
            logger.warning(
                "Notificaciones NO enviadas: configura FIREBASE_SERVICE_ACCOUNT_JSON en Render (valor = contenido "
                "completo del JSON de cuenta de servicio). La API legacy de FCM fue retirada (404)."
            )
            resultados = {'exitosos': 0, 'fallidos': len(tokens), 'tokens_invalidos': []}

        logger.info(
            "Notificaciones de venta: %s exitosas, %s fallidas, %s tokens inválidos",
            resultados['exitosos'],
            resultados['fallidos'],
            len(resultados['tokens_invalidos']),
        )
        return resultados

    @staticmethod
    def registrar_token(user, token, device_info=None):
        """
        Registra o actualiza un token FCM para un usuario.
        """
        fcm_token, created = FCMToken.objects.update_or_create(
            token=token,
            defaults={
                'user': user,
                'device_info': device_info,
                'activo': True,
            },
        )
        return fcm_token, created

    @staticmethod
    def eliminar_token(token):
        """Elimina o desactiva un token FCM."""
        try:
            fcm_token = FCMToken.objects.get(token=token)
            fcm_token.activo = False
            fcm_token.save()
            return True
        except FCMToken.DoesNotExist:
            return False
