# inventario/services/mercadolibre_service.py
"""
Servicio de integración con Mercado Libre API
Proporciona métodos para autenticación OAuth y sincronización de productos
"""
import requests
import json
import re
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Importar Producto para poder actualizar los registros
from inventario.models import Producto


class MercadoLibreReconnectRequired(Exception):
    """
    Se lanza cuando el refresh_token ya no es válido (ej. cambió la cuenta o la App de ML).
    La tienda debe volver a autorizar desde Configuración > Mercado Libre.
    """
    pass


class MercadoLibreService:
    """
    Servicio para interactuar con la API de Mercado Libre
    
    Documentación oficial: https://developers.mercadolibre.com.ar/es_ar
    """
    
    # URLs base según el ambiente
    # NOTA: Mercado Libre usa el mismo dominio para todos los ambientes
    # La diferencia entre test y production se maneja con la aplicación y permisos
    BASE_URLS = {
        'production': 'https://api.mercadolibre.com',
        'test': 'https://api.mercadolibre.com',  # Mismo dominio, diferente comportamiento según app
    }
    
    # Endpoints OAuth
    # Todos usan el mismo dominio, el site se determina por la aplicación
    OAUTH_URLS = {
        'production': 'https://auth.mercadolibre.com.ar/authorization',
        'test': 'https://auth.mercadolibre.com.ar/authorization',  # Mismo para ambos
    }
    
    TOKEN_URLS = {
        'production': 'https://api.mercadolibre.com/oauth/token',
        'test': 'https://api.mercadolibre.com/oauth/token',  # Mismo dominio
    }
    
    def __init__(self, tienda):
        """
        Inicializa el servicio con la configuración de la tienda
        
        Args:
            tienda: Instancia del modelo Tienda con configuración de Mercado Libre
        """
        self.tienda = tienda
        self.modo_test = tienda.ml_modo_test if hasattr(tienda, 'ml_modo_test') else True
        self.ambiente = 'test' if self.modo_test else 'production'
        self.base_url = self.BASE_URLS[self.ambiente]
        self.token_url = self.TOKEN_URLS[self.ambiente]
        self.access_token = tienda.ml_access_token if hasattr(tienda, 'ml_access_token') else None
        self.refresh_token = tienda.ml_refresh_token if hasattr(tienda, 'ml_refresh_token') else None
        self.app_id = tienda.ml_app_id if hasattr(tienda, 'ml_app_id') else None
        self.client_secret = tienda.ml_client_secret if hasattr(tienda, 'ml_client_secret') else None
        self.user_id = tienda.ml_user_id if hasattr(tienda, 'ml_user_id') else None
    
    def get_headers(self, include_auth=True):
        """
        Retorna los headers para las peticiones HTTP
        
        Args:
            include_auth: Si incluir el token de autorización
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if include_auth and self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        
        return headers
    
    def get_authorization_url(self, redirect_uri, state=None):
        """
        Genera la URL de autorización OAuth para que el usuario autentique la aplicación
        
        Args:
            redirect_uri: URL de redirección después de la autorización
            state: Parámetro opcional de estado (puede usarse para pasar tienda_id)
            
        Returns:
            URL completa para autorización
        """
        if not self.app_id:
            raise ValueError("App ID (ml_app_id) no configurado en la tienda")
        
        # Scopes necesarios para la integración:
        # - offline_access: Para obtener refresh token
        # - read: Para leer información de items y categorías
        # - write: Para crear y actualizar items
        scopes = 'offline_access read write'
        
        params = {
            'response_type': 'code',
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'scope': scopes,
        }
        
        # Agregar state si se proporciona (útil para identificar la tienda en el callback)
        if state:
            params['state'] = state
        
        auth_url = self.OAUTH_URLS[self.ambiente]
        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        
        return f"{auth_url}?{query_string}"
    
    def exchange_code_for_token(self, code, redirect_uri):
        """
        Intercambia el código de autorización por un access token y refresh token
        
        Args:
            code: Código de autorización obtenido después del OAuth flow
            redirect_uri: URL de redirección (debe coincidir con la usada en get_authorization_url)
            
        Returns:
            dict con access_token, refresh_token, expires_in, user_id, etc.
        """
        if not self.app_id or not self.client_secret:
            raise ValueError("App ID o Client Secret no configurado en la tienda")
        
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.app_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        }
        
        # IMPORTANTE: OAuth requiere application/x-www-form-urlencoded, NO JSON
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        
        try:
            response = requests.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            
            # Actualizar tokens en la tienda
            self.tienda.ml_access_token = token_data.get('access_token')
            self.tienda.ml_refresh_token = token_data.get('refresh_token')
            self.tienda.ml_user_id = token_data.get('user_id')
            
            # Calcular fecha de expiración
            expires_in = token_data.get('expires_in', 21600)  # 6 horas por defecto
            self.tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            self.tienda.save()
            
            # Actualizar tokens locales
            self.access_token = self.tienda.ml_access_token
            self.refresh_token = self.tienda.ml_refresh_token
            self.user_id = self.tienda.ml_user_id
            
            logger.info(f"Tokens de Mercado Libre actualizados para tienda {self.tienda.nombre}")
            
            return token_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al intercambiar código por token: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise
    
    def refresh_access_token(self):
        """
        Renueva el access token usando el refresh token
        
        Returns:
            dict con los nuevos tokens
        """
        if not self.refresh_token or not self.app_id or not self.client_secret:
            raise ValueError("Refresh token, App ID o Client Secret no configurado")
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.app_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token,
        }
        
        # IMPORTANTE: OAuth requiere application/x-www-form-urlencoded, NO JSON
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        
        try:
            response = requests.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            
            # Actualizar tokens
            self.tienda.ml_access_token = token_data.get('access_token')
            
            # El refresh token puede cambiar, actualizarlo si viene en la respuesta
            if 'refresh_token' in token_data:
                self.tienda.ml_refresh_token = token_data.get('refresh_token')
            
            expires_in = token_data.get('expires_in', 21600)
            self.tienda.ml_token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            self.tienda.save()
            
            self.access_token = self.tienda.ml_access_token
            if 'refresh_token' in token_data:
                self.refresh_token = self.tienda.ml_refresh_token
            
            logger.info(f"Access token renovado para tienda {self.tienda.nombre}")
            
            return token_data
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                try:
                    body = e.response.json()
                    err = body.get('error', '') or ''
                    msg = (body.get('message') or e.response.text or '')
                    if err == 'invalid_grant' or 'client_id does not match' in msg:
                        logger.warning(
                            "Token de ML inválido (cuenta o App distinta). Limpiando tokens para tienda %s",
                            self.tienda.nombre,
                        )
                        self.tienda.ml_access_token = None
                        self.tienda.ml_refresh_token = None
                        if hasattr(self.tienda, 'ml_token_expires_at'):
                            self.tienda.ml_token_expires_at = None
                        self.tienda.save()
                        self.access_token = None
                        self.refresh_token = None
                        raise MercadoLibreReconnectRequired(
                            "La cuenta o la aplicación de Mercado Libre no coinciden con la autorización guardada. "
                            "Reconectá la integración desde Configuración > Mercado Libre."
                        )
                except (ValueError, KeyError):
                    pass
            logger.error(f"Error al renovar token: {e}")
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al renovar token: {e}")
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'text'):
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise
    
    def ensure_valid_token(self):
        """
        Verifica que el token sea válido y lo renueva si es necesario
        """
        if not self.access_token:
            raise ValueError("Access token no configurado")
        
        # Verificar si el token está expirado o está por expirar (5 minutos antes)
        if self.tienda.ml_token_expires_at:
            if timezone.now() >= (self.tienda.ml_token_expires_at - timedelta(minutes=5)):
                logger.info(f"Token expirado o por expirar, renovando...")
                self.refresh_access_token()
    
    def get_user_info(self):
        """
        Obtiene información del usuario autenticado
        
        Returns:
            dict con información del usuario
        """
        self.ensure_valid_token()
        
        try:
            response = requests.get(
                f"{self.base_url}/users/me",
                headers=self.get_headers()
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener información del usuario: {e}")
            raise
    
    def get_items(self, limit=50, offset=0):
        """
        Obtiene los productos/publicaciones del vendedor
        
        Args:
            limit: Cantidad de items a retornar (máx 50)
            offset: Offset para paginación
            
        Returns:
            dict con los items y metadata de paginación
        """
        self.ensure_valid_token()
        
        if not self.user_id:
            raise ValueError("User ID no configurado. Complete el flujo OAuth primero.")
        
        try:
            response = requests.get(
                f"{self.base_url}/users/{self.user_id}/items/search",
                headers=self.get_headers(),
                params={
                    'limit': min(limit, 50),
                    'offset': offset,
                    'status': 'active'  # Solo items activos
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener items: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Respuesta del servidor: {e.response.text}")
            raise
    
    def get_item(self, item_id):
        """
        Obtiene información detallada de un item/producto
        
        Args:
            item_id: ID del item en Mercado Libre
            
        Returns:
            dict con información completa del item
        """
        self.ensure_valid_token()
        
        try:
            response = requests.get(
                f"{self.base_url}/items/{item_id}",
                headers=self.get_headers()
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener item {item_id}: {e}")
            raise
    
    def get_sale_price(self, item_id):
        """
        Obtiene el precio de venta actual del item (incluye precio con promoción/descuento si aplica).
        API: GET /items/{id}/sale_price - devuelve el precio ganador mostrado al comprador.
        
        Args:
            item_id: ID del item en Mercado Libre
            
        Returns:
            dict con amount (precio actual), regular_amount (precio original si hay promo), currency_id, etc.
            None si el endpoint no está disponible o falla.
        """
        self.ensure_valid_token()
        try:
            response = requests.get(
                f"{self.base_url}/items/{item_id}/sale_price",
                headers=self.get_headers(),
                params={'context': 'channel_marketplace'},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                logger.debug(f"sale_price no disponible para item {item_id}")
            else:
                logger.debug(f"Error al obtener sale_price para {item_id}: {e}")
            return None
    
    def create_producto_from_ml_item(self, tienda, item_data):
        """
        Crea o actualiza un Producto en la base de datos a partir de los datos de un item de Mercado Libre.
        Se usa al importar productos desde ML o al registrar una venta de ML cuyo producto no existía localmente.
        
        Args:
            tienda: Instancia del modelo Tienda
            item_data: dict con la respuesta de get_item (id, title, price, available_quantity, etc.)
            
        Returns:
            Instancia de Producto creada o actualizada, o None si falla
        """
        if not item_data or not isinstance(item_data, dict):
            logger.warning("create_producto_from_ml_item: item_data inválido o vacío")
            return None
        
        ml_item_id = item_data.get('id')
        if not ml_item_id:
            logger.warning("create_producto_from_ml_item: el item no tiene id")
            return None
        
        title = (item_data.get('title') or '').strip()
        if not title:
            title = f"Producto ML {ml_item_id}"
        
        # Preferir precio con promoción (sale_price) si existe; si no, usar price del item
        price = None
        sale_data = self.get_sale_price(ml_item_id)
        if sale_data is not None and sale_data.get('amount') is not None:
            try:
                price = float(sale_data['amount'])
            except (TypeError, ValueError):
                pass
        if price is None:
            try:
                price = float(item_data.get('price', 0))
            except (TypeError, ValueError):
                price = 0
        if price < 0:
            price = 0
        
        try:
            available_quantity = int(item_data.get('available_quantity', 0))
        except (TypeError, ValueError):
            available_quantity = 0
        if available_quantity < 0:
            available_quantity = 0
        
        # Descripción: ML puede devolver un objeto con plain_text
        description = None
        if item_data.get('descriptions') and isinstance(item_data['descriptions'], list) and len(item_data['descriptions']) > 0:
            desc_id = item_data['descriptions'][0]
            if isinstance(desc_id, dict) and desc_id.get('id'):
                # Se podría hacer otra llamada para obtener el texto, por ahora dejamos None
                pass
        codigo_barras = f"ML-{ml_item_id}"  # Código único para productos importados de ML
        # Usar ml_item_id como talle para cumplir unique_together (nombre, tienda, talle) sin colisiones
        talle_ml = ml_item_id[:50] if len(ml_item_id) <= 50 else ml_item_id[:47] + "..."
        
        from django.db import IntegrityError
        base_codigo = codigo_barras
        intento = 0
        while intento < 100:
            try:
                producto, created = Producto.objects.update_or_create(
                    tienda=tienda,
                    ml_item_id=ml_item_id,
                    defaults={
                        'nombre': title[:200],
                        'precio': price,
                        'stock': available_quantity,
                        'talle': talle_ml,
                        'descripcion': description,
                        'codigo_barras': codigo_barras,
                        'ml_sincronizado': True,
                        'ml_ultima_sincronizacion': timezone.now(),
                    }
                )
                if created:
                    logger.info(f"Producto creado desde ML: {producto.nombre} (ml_item_id={ml_item_id})")
                else:
                    logger.info(f"Producto actualizado desde ML: {producto.nombre} (ml_item_id={ml_item_id})")
                return producto
            except IntegrityError as e:
                if 'codigo_barras' in str(e) or 'unique' in str(e).lower():
                    intento += 1
                    codigo_barras = f"{base_codigo}-{intento}"
                else:
                    raise
        logger.error(f"create_producto_from_ml_item: no se pudo asignar codigo_barras único para {ml_item_id}")
        return None
    
    def create_item(self, item_data):
        """
        Crea un nuevo producto/publicación en Mercado Libre
        
        Args:
            item_data: dict con los datos del producto según formato ML
            
        Returns:
            dict con el item creado
        """
        self.ensure_valid_token()
        
        if not self.user_id:
            raise ValueError("User ID no configurado")
        
        try:
            # IMPORTANTE: No enviar seller_id en el body, ML lo obtiene automáticamente del token
            # Crear una copia del item_data sin seller_id por si acaso
            item_data_clean = {k: v for k, v in item_data.items() if k != 'seller_id'}
            
            response = requests.post(
                f"{self.base_url}/items",
                json=item_data_clean,
                headers=self.get_headers()
            )
            
            # Verificar si hay errores o solo warnings
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    # Verificar si solo hay warnings de shipping
                    causes = error_data.get('cause', [])
                    only_shipping_warnings = True
                    real_errors = []
                    
                    for cause in causes:
                        cause_type = cause.get('type', 'error')
                        cause_code = cause.get('code', '')
                        cause_department = cause.get('department', '')
                        
                        # Si hay un error que no sea de shipping o sea un error real, no es solo warnings
                        if cause_type == 'error' and cause_department != 'shipping':
                            only_shipping_warnings = False
                            real_errors.append(cause)
                        elif cause_type == 'error' and cause_department == 'shipping' and 'lost' not in cause_code.lower():
                            # Errores de shipping que no sean "lost" (que son warnings) son errores reales
                            only_shipping_warnings = False
                            real_errors.append(cause)
                        elif cause_type == 'warning' and cause_department == 'shipping':
                            # Warnings de shipping se pueden ignorar
                            logger.warning(f"Warning de shipping ignorado: {cause.get('message', '')}")
                    
                    # Verificar si el mensaje del error principal indica un problema real (no solo warnings)
                    error_message_main = error_data.get('message', '')
                    # Errores que NO son solo warnings de shipping:
                    real_error_indicators = ['listing type', 'temporarily unavailable', 'available_quantity', 'invalid', 'required', 'missing']
                    has_real_error_in_message = any(indicator in error_message_main.lower() for indicator in real_error_indicators)
                    
                    # Si solo hay warnings de shipping Y no hay indicadores de error real en el mensaje principal
                    if only_shipping_warnings and not real_errors and not has_real_error_in_message:
                        logger.warning(f"ML devolvió 400 pero solo con warnings de shipping. Intentando obtener el item creado...")
                        # A veces ML crea el item a pesar de los warnings
                        # No podemos obtener el ID directamente, así que lanzar un error más descriptivo
                        warning_messages = [c.get('message', '') for c in causes if c.get('type') == 'warning']
                        logger.warning(f"Warnings de shipping: {', '.join(warning_messages)}")
                        # Lanzar error para que el código de arriba pueda manejarlo
                        raise ValueError(f"Error de validación: {error_data.get('message', 'Error desconocido')}. Solo hay warnings de shipping que pueden ser ignorados. Verifica la configuración de envío en Mercado Libre.")
                    
                    # Si hay errores reales o indicadores de error real en el mensaje, lanzar el error normalmente
                    if real_errors or has_real_error_in_message:
                        # Si hay un error de cantidad disponible, incluir información detallada
                        quantity_error = None
                        for cause in causes:
                            if cause.get('code') == 'item.available_quantity.invalid':
                                quantity_error = cause.get('message', '')
                                break
                        
                        if real_errors:
                            error_messages = [e.get('message', '') for e in real_errors]
                            error_msg = ', '.join(error_messages)
                            # Si hay error de cantidad, agregar información adicional
                            if quantity_error:
                                error_msg = f"{error_msg} (Cantidad: {quantity_error})"
                            raise ValueError(f"Error de validación: {error_msg}")
                        else:
                            error_msg = error_message_main
                            # Si hay error de cantidad, agregar información adicional
                            if quantity_error:
                                error_msg = f"{error_msg} (Cantidad: {quantity_error})"
                            raise ValueError(f"Error de validación: {error_msg}")
                    
                except ValueError:
                    # Re-lanzar nuestros ValueError personalizados
                    raise
                except Exception:
                    # Si no podemos parsear, continuar con el manejo normal de errores
                    pass
            
            response.raise_for_status()
            
            created_item = response.json()
            logger.info(f"Item creado en Mercado Libre: {created_item.get('id')}")
            
            return created_item
            
        except requests.exceptions.HTTPError as e:
            # Manejar errores HTTP específicos
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"{e.response.status_code} {e.response.reason}: {error_data}"
                    logger.error(f"Error detallado ML: {error_data}")
                except:
                    error_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
                    logger.error(f"Error al crear item: {error_msg}")
            raise ValueError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"{e.response.status_code} {e.response.reason}: {error_data}"
                    logger.error(f"Error detallado ML: {error_data}")
                except:
                    error_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
                    logger.error(f"Error al crear item: {error_msg}")
            logger.error(f"Error al crear item: {error_msg}")
            raise ValueError(error_msg)
    
    def update_item(self, item_id, item_data):
        """
        Actualiza un producto/publicación existente en Mercado Libre
        
        Args:
            item_id: ID del item en Mercado Libre
            item_data: dict con los datos a actualizar (solo campos modificados)
            
        Returns:
            dict con el item actualizado
            
        Raises:
            requests.exceptions.RequestException: Si hay un error HTTP
            ValueError: Si hay un error de validación con información detallada
        """
        self.ensure_valid_token()
        
        logger.debug(f"Actualizando item {item_id} con datos: {item_data}")
        
        try:
            response = requests.put(
                f"{self.base_url}/items/{item_id}",
                json=item_data,
                headers=self.get_headers(),
                timeout=30
            )
            
            # Si hay un error 400, intentar parsear el error para dar información más útil
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_message = error_data.get('message', 'Error de validación')
                    causes = error_data.get('cause', [])
                    
                    # Detectar si el error es porque el item no es modificable
                    error_lower = error_message.lower()
                    causes_lower = []
                    for cause in causes:
                        cause_msg = cause.get('message', '').lower()
                        causes_lower.append(cause_msg)
                    
                    is_not_modifiable = (
                        'not_modifiable' in error_lower or 
                        'is not modifiable' in error_lower or
                        'cannot be modified' in error_lower or
                        'no se puede modificar' in error_lower or
                        any('not modifiable' in msg for msg in causes_lower) or
                        any('is not modifiable' in msg for msg in causes_lower)
                    )
                    
                    # Si el item no es modificable, lanzar un error especial que será manejado arriba
                    if is_not_modifiable:
                        logger.warning(f"Item {item_id} no es modificable. Error: {error_message}")
                        raise ValueError(f"El producto no se puede modificar en Mercado Libre. Puede estar vendido, cerrado o en un estado que no permite modificaciones. Error: {error_message}")
                    
                    # Buscar errores específicos de cantidad
                    for cause in causes:
                        if cause.get('code') == 'item.available_quantity.invalid':
                            message = cause.get('message', '')
                            logger.error(f"Error de cantidad al actualizar item {item_id}: {message}")
                            raise ValueError(f"Error al actualizar stock: {message}")
                    
                    # Si hay otros errores, lanzar ValueError con información
                    if causes:
                        error_messages = [c.get('message', '') for c in causes if c.get('type') == 'error']
                        if error_messages:
                            raise ValueError(f"Error de validación: {', '.join(error_messages)}")
                    
                    # Si no hay causas específicas, usar el mensaje general
                    raise ValueError(f"Error de validación: {error_message}")
                except ValueError:
                    # Re-lanzar ValueError
                    raise
                except Exception:
                    # Si no se puede parsear, continuar con el manejo normal
                    pass
            
            response.raise_for_status()
            
            updated_item = response.json()
            logger.info(f"Item {item_id} actualizado exitosamente en Mercado Libre")
            logger.debug(f"Datos actualizados: {updated_item.get('available_quantity', 'N/A')} unidades")
            
            return updated_item
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al actualizar item {item_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Status code: {e.response.status_code}")
                logger.error(f"Respuesta del servidor: {e.response.text[:500]}")
            raise
    
    def update_stock(self, item_id, available_quantity):
        """
        Actualiza solo el stock de un item
        
        Args:
            item_id: ID del item en Mercado Libre
            available_quantity: Cantidad disponible en stock
            
        Returns:
            dict con el item actualizado
            
        Raises:
            ValueError: Si hay un error al actualizar, con información sobre limitaciones
        """
        self.ensure_valid_token()
        
        logger.info(f"Actualizando stock del item {item_id} a {available_quantity} unidades")
        
        try:
            result = self.update_item(item_id, {'available_quantity': available_quantity})
            logger.info(f"Stock actualizado exitosamente a {available_quantity} unidades para item {item_id}")
            return result
        except requests.exceptions.RequestException as e:
            # Si el error es por cantidad máxima permitida, intentar con el máximo
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    if e.response.status_code == 400 and error_data.get('error') == 'validation_error':
                        # Buscar error específico de cantidad máxima
                        causes = error_data.get('cause', [])
                        for cause in causes:
                            if cause.get('code') == 'item.available_quantity.invalid':
                                message = cause.get('message', '')
                                # Extraer el máximo del mensaje (ej: "Available quantity max. value is 1 for category...")
                                max_match = re.search(r'max\.?\s*value\s*is\s*(\d+)', message, re.IGNORECASE)
                                if max_match:
                                    max_allowed = int(max_match.group(1))
                                    logger.warning(f"Cantidad {available_quantity} excede el máximo permitido ({max_allowed}) para este item. Ajustando a {max_allowed}.")
                                    # Intentar con el máximo permitido
                                    try:
                                        result = self.update_item(item_id, {'available_quantity': max_allowed})
                                        logger.info(f"Stock ajustado al máximo permitido ({max_allowed}) para item {item_id}")
                                        return result
                                    except Exception as update_error:
                                        # Si aún falla, lanzar error con información útil
                                        logger.error(f"Error al actualizar stock al máximo permitido ({max_allowed}): {update_error}")
                                        raise ValueError(
                                            f"Este producto tiene una limitación de stock máximo de {max_allowed} unidades "
                                            f"en Mercado Libre debido a su categoría. Stock solicitado: {available_quantity}. "
                                            f"No se pudo actualizar el stock."
                                        )
                                else:
                                    # No se pudo extraer el máximo, lanzar error genérico
                                    raise ValueError(
                                        f"El stock solicitado ({available_quantity}) excede el máximo permitido para esta categoría en Mercado Libre. "
                                        f"Error: {message}"
                                    )
                except (ValueError, json.JSONDecodeError) as parse_error:
                    # Si hay un ValueError, re-lanzarlo (ya tiene información útil)
                    if isinstance(parse_error, ValueError):
                        raise
                    # Si es JSONDecodeError, continuar con el manejo normal
                    pass
            
            # Si no es un error de validación de cantidad, re-lanzar el error original
            logger.error(f"Error al actualizar stock del item {item_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text[:500]}")
            raise ValueError(f"Error al actualizar stock: {str(e)}")
    
    def update_price(self, item_id, price):
        """
        Actualiza solo el precio de un item
        
        Args:
            item_id: ID del item en Mercado Libre
            price: Nuevo precio (número, sin formato de moneda)
            
        Returns:
            dict con el item actualizado
        """
        return self.update_item(item_id, {'price': price})
    
    def close_item(self, item_id):
        """
        Cierra una publicación (la marca como pausada)
        
        Args:
            item_id: ID del item en Mercado Libre
        """
        self.ensure_valid_token()
        
        try:
            response = requests.put(
                f"{self.base_url}/items/{item_id}",
                json={'status': 'paused'},
                headers=self.get_headers()
            )
            response.raise_for_status()
            logger.info(f"Item pausado en Mercado Libre: {item_id}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al pausar item {item_id}: {e}")
            raise
    
    def get_categories(self, site_id='MLA', use_auth=True):
        """
        Obtiene las categorías disponibles en Mercado Libre
        
        Args:
            site_id: ID del sitio (MLA = Argentina, MLB = Brasil, etc.)
            use_auth: Si usar autenticación (algunas veces ML bloquea sin auth)
            
        Returns:
            Lista de categorías
        """
        try:
            # Intentar primero sin autenticación (endpoint público)
            try:
                response = requests.get(
                    f"{self.base_url}/sites/{site_id}/categories",
                    headers=self.get_headers(include_auth=False),
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                # Si falla con 403 y tenemos autenticación, intentar con auth
                if e.response.status_code == 403 and use_auth and self.access_token:
                    logger.warning(f"Error 403 obteniendo categorías sin auth, intentando con autenticación...")
                    try:
                        response = requests.get(
                            f"{self.base_url}/sites/{site_id}/categories",
                            headers=self.get_headers(include_auth=True),
                            timeout=10
                        )
                        response.raise_for_status()
                        logger.info(f"Categorías obtenidas exitosamente con autenticación")
                        return response.json()
                    except requests.exceptions.HTTPError as e2:
                        logger.error(f"Error al obtener categorías con autenticación: {e2.response.status_code if e2.response else 'No response'}")
                        if hasattr(e2, 'response') and e2.response is not None:
                            logger.error(f"Respuesta del servidor con auth: {e2.response.text[:500]}")
                        # Re-lanzar el error original para que se maneje en el nivel superior
                        raise e
                else:
                    raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener categorías: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Respuesta del servidor: {e.response.text[:500]}")
            raise
    
    def get_category_info(self, category_id, site_id='MLA'):
        """
        Obtiene información detallada de una categoría, incluyendo atributos requeridos
        
        Args:
            category_id: ID de la categoría (ej: MLA5726)
            site_id: ID del sitio (MLA = Argentina)
            
        Returns:
            dict con información de la categoría
        """
        try:
            response = requests.get(
                f"{self.base_url}/categories/{category_id}",
                headers=self.get_headers(include_auth=False)
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener información de categoría {category_id}: {e}")
            raise
    
    def is_leaf_category(self, category_id, site_id='MLA'):
        """
        Verifica si una categoría es una hoja (leaf category), es decir, no tiene subcategorías
        
        Args:
            category_id: ID de la categoría (ej: MLA5726)
            site_id: ID del sitio (MLA = Argentina)
            
        Returns:
            bool: True si es una categoría hoja, False si tiene subcategorías
        """
        try:
            category_info = self.get_category_info(category_id, site_id)
            children = category_info.get('children_categories', [])
            return len(children) == 0
        except Exception as e:
            logger.error(f"Error al verificar si categoría {category_id} es hoja: {e}")
            return False
    
    def get_leaf_category_from_parent(self, category_id, site_id='MLA', max_depth=3):
        """
        Si una categoría no es hoja, busca una categoría hoja dentro de sus subcategorías
        
        Args:
            category_id: ID de la categoría padre
            site_id: ID del sitio
            max_depth: Profundidad máxima de búsqueda
            
        Returns:
            str: ID de una categoría hoja, o None si no se encuentra
        """
        try:
            leaf_categories = self.get_leaf_categories(category_id, site_id, max_depth)
            if leaf_categories:
                return leaf_categories[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error al buscar categoría hoja desde {category_id}: {e}")
            return None
    
    def get_leaf_categories(self, parent_category_id='MLA1574', site_id='MLA', max_depth=2):
        """
        Obtiene las categorías hoja (leaf categories) de una categoría padre
        OPTIMIZADO: Limita la profundidad y cantidad de llamadas para ser más rápido
        
        Args:
            parent_category_id: ID de la categoría padre
            site_id: ID del sitio (MLA = Argentina)
            max_depth: Profundidad máxima de búsqueda (default: 2 para ser rápido)
            
        Returns:
            Lista de categorías hoja
        """
        try:
            category_info = self.get_category_info(parent_category_id, site_id)
            children = category_info.get('children_categories', [])
            
            # Si no tiene hijos, esta categoría es una hoja
            if not children:
                return [category_info]
            
            # Si alcanzamos la profundidad máxima, no buscar más
            if max_depth <= 0:
                return []
            
            leaf_categories = []
            # Limitar a las primeras 10 categorías hijas para ser más rápido
            for child in children[:10]:
                try:
                    child_info = self.get_category_info(child['id'], site_id)
                    # Si no tiene hijos, es una categoría hoja
                    if not child_info.get('children_categories'):
                        leaf_categories.append(child_info)
                        # Si ya tenemos suficientes, parar
                        if len(leaf_categories) >= 10:
                            break
                    else:
                        # Recursivamente buscar categorías hoja (con profundidad reducida)
                        sub_leafs = self.get_leaf_categories(child['id'], site_id, max_depth - 1)
                        if sub_leafs:
                            leaf_categories.extend(sub_leafs[:3])  # Limitar a 3 por categoría padre
                            # Si ya tenemos suficientes, parar
                            if len(leaf_categories) >= 10:
                                break
                except:
                    continue  # Continuar con la siguiente si hay error
            
            return leaf_categories
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al obtener categorías hoja de {parent_category_id}: {e}")
            return []
    
    def sync_producto_to_ml(self, producto, categoria_ml_id=None, condicion='new', listing_type_id='free'):
        """
        Sincroniza un producto de Total Stock a Mercado Libre
        
        Args:
            producto: Instancia del modelo Producto
            categoria_ml_id: ID de la categoría en Mercado Libre. Si es None, intenta obtener una categoría hoja válida.
            condicion: Condición del producto ('new', 'used', 'not_specified')
            listing_type_id: Tipo de publicación ('free', 'bronze', 'silver', 'gold')
            
        Returns:
            dict con el item creado en Mercado Libre
        """
        self.ensure_valid_token()
        
        if not self.user_id:
            raise ValueError("User ID no configurado. Complete el flujo OAuth primero.")
        
        # Validar que la categoría sea una hoja si está especificada
        if categoria_ml_id:
            # Verificar si es una categoría hoja
            is_leaf = self.is_leaf_category(categoria_ml_id)
            if not is_leaf:
                logger.warning(f"La categoría {categoria_ml_id} no es una hoja. Buscando categoría hoja dentro de esta categoría...")
                # Buscar una categoría hoja dentro de esta categoría
                leaf_category = self.get_leaf_category_from_parent(categoria_ml_id)
                if leaf_category:
                    logger.info(f"✅ Encontrada categoría hoja {leaf_category} dentro de {categoria_ml_id}. Usando esta categoría.")
                    categoria_ml_id = leaf_category
                else:
                    # Si no se encuentra una hoja, buscar categorías hoja con más profundidad
                    logger.warning(f"No se encontró categoría hoja inmediata para {categoria_ml_id}. Buscando con más profundidad...")
                    leaf_categories = self.get_leaf_categories(categoria_ml_id, max_depth=3)
                    if leaf_categories:
                        # Usar la primera categoría hoja encontrada
                        categoria_ml_id = leaf_categories[0]['id']
                        logger.info(f"✅ Encontrada categoría hoja {categoria_ml_id} ({leaf_categories[0].get('name', '')}) dentro de la categoría seleccionada.")
                    else:
                        logger.error(f"❌ No se encontró ninguna categoría hoja para {categoria_ml_id}. Esto puede causar que ML asigne una categoría incorrecta.")
                        raise ValueError(f"La categoría {categoria_ml_id} no tiene subcategorías hoja válidas. Por favor, selecciona una categoría más específica (categoría hoja).")
        
        # Si no se especifica categoría o es una categoría inválida, usar una categoría por defecto simple
        # OPTIMIZACIÓN: Evitar hacer múltiples llamadas a la API que tardan mucho tiempo
        if not categoria_ml_id or categoria_ml_id in ['MLA5726', 'MLA1575', 'MLA414027']:
            # Usar una categoría genérica conocida que funciona bien: MLA1574 (Otros)
            # Esta categoría generalmente es más permisiva y no requiere tantos atributos específicos
            try:
                # Verificar si MLA1574 es una categoría hoja
                cat_info = self.get_category_info('MLA1574')
                if not cat_info.get('children_categories'):
                    # Es una hoja, usarla
                    categoria_ml_id = 'MLA1574'
                    logger.info(f"Usando categoría por defecto: MLA1574 (Otros)")
                else:
                    # No es hoja, determinar categoría según el tipo de producto
                    # Primero intentar usar una categoría de muebles si parece ser un mueble según el nombre del producto
                    nombre_producto_lower = producto.nombre.lower()
                    es_mueble = any(word in nombre_producto_lower for word in ['mesa', 'silla', 'mueble', 'escritorio', 'cama', 'sillón', 'sofa', 'estante', 'rack', 'biblioteca'])
                    
                    categoria_encontrada = False
                    if es_mueble:
                        # Intentar buscar categorías de muebles usando MLA1574 (Hogar, Muebles y Decoración)
                        # y luego filtrar por categorías relacionadas con muebles
                        try:
                            # Buscar categorías hijas de MLA1574 que sean relacionadas con muebles
                            hogar_categories = self.get_category_info('MLA1574').get('children_categories', [])
                            if hogar_categories:
                                for cat in hogar_categories[:15]:
                                    cat_name = cat.get('name', '').lower()
                                    # Buscar categorías relacionadas con muebles (ser más específico)
                                    # Priorizar "mueble" pero también incluir otras palabras relacionadas
                                    # Evitar decoración que no es mueble
                                    if 'mueble' in cat_name or ('mesa' in cat_name and 'mueble' not in cat_name) or ('silla' in cat_name and 'mueble' not in cat_name):
                                        # No usar si es claramente decoración
                                        if any(word in cat_name for word in ['decoración', 'decorativa', 'adorno', 'banderín', 'guirnalda', 'ornamento']):
                                            continue
                                        try:
                                            # Obtener categorías hoja de esta categoría
                                            muebles_leafs = self.get_leaf_categories(cat['id'], max_depth=1)
                                            if muebles_leafs:
                                                for leaf in muebles_leafs[:10]:
                                                    leaf_name = leaf.get('name', '').lower()
                                                    # Evitar categorías problemáticas (incluyendo decoración que no es mueble)
                                                    if any(word in leaf_name for word in ['alcancía', 'atrapasueños', 'bandeja', 'bandejas', 'decoración', 'regalo', 'juguete', 'adorno', 'banderín', 'banderines', 'guirnalda', 'guirnaldas', 'ornamento', 'adornos']):
                                                        continue
                                                    categoria_ml_id = leaf['id']
                                                    logger.info(f"Usando categoría de muebles: {categoria_ml_id} ({leaf.get('name', '')})")
                                                    categoria_encontrada = True
                                                    break
                                                if categoria_encontrada:
                                                    break
                                        except Exception as e:
                                            logger.debug(f"Error al obtener hojas de {cat['id']}: {e}")
                                            continue
                        except Exception as e:
                            logger.warning(f"Error al buscar categorías de muebles: {e}. Usando categoría genérica.")
                    
                    # Si no es mueble o no encontramos categoría de muebles, usar "Otros"
                    if not categoria_encontrada or categoria_ml_id in ['MLA1574', 'MLA1575', 'MLA414027', 'MLA457167']:
                        leaf_categories = self.get_leaf_categories('MLA1574')
                        if leaf_categories:
                            # Evitar categorías muy específicas o problemáticas
                            categoria_seleccionada = None
                            for cat in leaf_categories[:10]:  # Revisar más categorías
                                cat_name = cat.get('name', '').lower()
                                # Evitar categorías muy específicas o problemáticas (incluyendo Atrapasueños, Bandejas y Banderines)
                                if any(word in cat_name for word in ['alcancía', 'atrapasueños', 'juguete', 'decoración', 'regalo', 'fabricante', 'sueño', 'bandeja', 'bandejas', 'adorno', 'banderín', 'banderines', 'guirnalda', 'guirnaldas', 'ornamento', 'adornos']):
                                    continue
                                categoria_seleccionada = cat
                                break
                            
                            if categoria_seleccionada:
                                categoria_ml_id = categoria_seleccionada['id']
                                logger.info(f"Usando categoría hoja automática: {categoria_ml_id} ({categoria_seleccionada.get('name', '')})")
                            else:
                                # Si no encontramos una mejor, usar MLA1574 directamente
                                categoria_ml_id = 'MLA1574'
                                logger.info(f"No se encontró categoría adecuada, usando MLA1574 (Otros)")
                        else:
                            # Fallback: usar MLA1574 aunque no sea hoja (ML puede aceptarlo)
                            categoria_ml_id = 'MLA1574'
                            logger.warning(f"No se encontraron categorías hoja, usando MLA1574 como fallback")
            except Exception as e:
                logger.error(f"Error al obtener categoría: {e}")
                # Fallback final: usar MLA1574
                categoria_ml_id = 'MLA1574'
                logger.warning(f"Usando categoría fallback: MLA1574")
        
        # Validar que el precio sea mayor a 0
        precio = float(producto.precio)
        if precio <= 0:
            raise ValueError(f"El precio del producto '{producto.nombre}' debe ser mayor a 0")
        
        # Validar precio mínimo (ML generalmente requiere mínimo $100 ARS)
        if precio < 100:
            raise ValueError(f"El precio del producto '{producto.nombre}' debe ser al menos $100 ARS (precio actual: ${precio})")
        
        # Validar que el título no esté vacío
        if not producto.nombre or len(producto.nombre.strip()) == 0:
            raise ValueError(f"El producto debe tener un nombre")
        
        # Validar longitud mínima del título (ML requiere mínimo 10 caracteres)
        titulo = producto.nombre.strip()
        if len(titulo) < 10:
            raise ValueError(f"El título del producto '{producto.nombre}' debe tener al menos 10 caracteres (actual: {len(titulo)} caracteres)")
        
        # Obtener información de la categoría para conocer requisitos
        # OPTIMIZACIÓN: Cachear esta información o hacerla opcional para ser más rápido
        required_attributes = []
        try:
            category_info = self.get_category_info(categoria_ml_id)
            # Obtener atributos requeridos de la categoría
            # Limitar a los primeros 20 atributos para ser más rápido
            for attr in category_info.get('attributes', [])[:20]:
                # Verificar si es requerido (puede estar en tags.required o tags.catalog_required)
                tags = attr.get('tags', {})
                is_required = tags.get('required', False) or tags.get('catalog_required', False)
                if is_required:
                    required_attributes.append(attr)
                    logger.debug(f"Atributo requerido encontrado: {attr.get('id')} ({attr.get('name')})")
                    # Si ya tenemos muchos atributos requeridos, parar
                    if len(required_attributes) >= 10:
                        break
            
            logger.info(f"Atributos requeridos encontrados para categoría {categoria_ml_id}: {[a.get('id') for a in required_attributes]}")
        except Exception as e:
            logger.warning(f"No se pudo obtener información de la categoría {categoria_ml_id}: {e}")
            # Continuar sin atributos requeridos - ML rechazará si falta algo importante
            required_attributes = []
        
        # Preparar datos del producto para Mercado Libre
        # Usar 'free' como listing_type_id por defecto (no requiere imágenes)
        # 'bronze' requiere al menos una imagen, 'free' no
        listing_type = listing_type_id if listing_type_id else 'free'
        
        # Determinar cantidad disponible (algunas categorías limitan a 1)
        available_quantity = max(1, producto.stock)
        # Si la categoría tiene restricciones de cantidad, ajustar
        # Por ahora, si el stock es mayor a 1, usar 1 para evitar errores
        # (esto se puede mejorar consultando las restricciones de la categoría)
        if available_quantity > 1:
            # Intentar con el stock real, pero si falla, ajustaremos a 1
            pass
        
        item_data = {
            'title': titulo[:60],  # ML limita a 60 caracteres, mínimo 10
            'category_id': categoria_ml_id,
            'price': precio,
            'currency_id': 'ARS',  # Peso argentino
            'available_quantity': available_quantity,
            'buying_mode': 'buy_it_now',
            'listing_type_id': listing_type,
            'condition': condicion,
            'sale_terms': [],
            # ML requiere al menos una imagen para todos los tipos de publicación
            # Usamos una imagen placeholder de ML o una URL genérica
            'pictures': [
                {
                    'source': 'https://http2.mlstatic.com/storage/developers-site-cms-admin/openapi/319968599067-mp.png'
                }
            ],
            # No incluir 'shipping_mode' ni 'free_shipping' - se configuran después o automáticamente
        }
        
        # Agregar descripción solo si existe
        if producto.descripcion and producto.descripcion.strip():
            item_data['description'] = {
                'plain_text': producto.descripcion[:5000].strip()  # ML limita a 5000 caracteres
            }
        else:
            # ML requiere descripción, usar el nombre si no hay descripción
            item_data['description'] = {
                'plain_text': producto.nombre[:5000]
            }
        
        # Atributos básicos requeridos por ML
        attributes = []
        attribute_ids_added = set()  # Para evitar duplicados
        
        # Agregar marca si es posible (algunas categorías lo requieren)
        # Intentamos agregar marca, pero si la categoría no la requiere, ML lo ignorará
        attributes.append({
            'id': 'BRAND',
            'value_name': 'Sin marca'
        })
        attribute_ids_added.add('BRAND')
        
        # Agregar MODEL y MANUFACTURER siempre, ya que muchas categorías los requieren
        # aunque no estén marcados como "required" en los tags de la API
        # Usar el nombre del producto como modelo
        model_value = producto.nombre[:50] if producto.nombre else 'Modelo genérico'
        attributes.append({
            'id': 'MODEL',
            'value_name': model_value
        })
        attribute_ids_added.add('MODEL')
        
        # Agregar MANUFACTURER (Fabricante)
        attributes.append({
            'id': 'MANUFACTURER',
            'value_name': 'Sin marca'
        })
        attribute_ids_added.add('MANUFACTURER')
        
        # Agregar atributos requeridos por la categoría
        for req_attr in required_attributes:
            attr_id = req_attr.get('id')
            attr_name = req_attr.get('name', '')
            value_type = req_attr.get('value_type', 'string')
            
            # Evitar duplicados
            if attr_id in attribute_ids_added:
                continue
            
            # Construir el atributo según su tipo
            # NOTA: Según la documentación de ML, solo necesitamos 'id' y 'value_name' o 'value_id'
            # El campo 'name' es opcional y puede causar problemas
            attr_data = {
                'id': attr_id
            }
            
            # Si es MODEL, usar el nombre del producto o un valor genérico
            if attr_id == 'MODEL':
                model_value = producto.nombre[:50] if producto.nombre else 'Modelo genérico'
                # Si tiene valores predefinidos, intentar encontrar uno que coincida
                if req_attr.get('values') and len(req_attr.get('values', [])) > 0:
                    # Buscar un valor que coincida con el nombre del producto
                    matching_value = None
                    for val in req_attr.get('values', []):
                        if model_value.lower() in val.get('name', '').lower() or val.get('name', '').lower() in model_value.lower():
                            matching_value = val
                            break
                    
                    if matching_value:
                        # Usar value_id si está disponible
                        attr_data['value_id'] = matching_value.get('id')
                        attr_data['value_name'] = matching_value.get('name')
                    else:
                        # Si no hay coincidencia, usar value_name con el nombre del producto
                        attr_data['value_name'] = model_value
                else:
                    # Si no hay valores predefinidos, usar value_name
                    attr_data['value_name'] = model_value
                
                attributes.append(attr_data)
                attribute_ids_added.add('MODEL')
            # Si es MANUFACTURER (Fabricante), usar un valor genérico
            elif attr_id == 'MANUFACTURER':
                # Si tiene valores predefinidos, usar el primero disponible o "Sin marca"
                if req_attr.get('values') and len(req_attr.get('values', [])) > 0:
                    first_value = req_attr.get('values', [{}])[0]
                    if first_value.get('id'):
                        attr_data['value_id'] = first_value.get('id')
                    attr_data['value_name'] = first_value.get('name', 'Sin marca')
                else:
                    attr_data['value_name'] = 'Sin marca'
                
                attributes.append(attr_data)
                attribute_ids_added.add('MANUFACTURER')
            # Agregar otros atributos requeridos con valores por defecto si es necesario
            elif attr_id not in ['BRAND', 'SIZE']:  # Ya los agregamos o los agregaremos
                # Según el tipo de valor, usar value_id o value_name
                if value_type == 'number':
                    default_value = req_attr.get('default_value') or '0'
                    attr_data['value_name'] = str(default_value)
                elif req_attr.get('values') and len(req_attr.get('values', [])) > 0:
                    # Si tiene valores predefinidos, usar el primero disponible
                    first_value = req_attr.get('values', [{}])[0]
                    if first_value.get('id'):
                        attr_data['value_id'] = first_value.get('id')
                    attr_data['value_name'] = first_value.get('name', 'No especificado')
                else:
                    # Intentar obtener un valor por defecto o usar "No especificado"
                    default_value = req_attr.get('default_value') or 'No especificado'
                    attr_data['value_name'] = default_value
                
                attributes.append(attr_data)
                attribute_ids_added.add(attr_id)
        
        # Si tiene talle, agregarlo como atributo
        if producto.talle and producto.talle != 'UNICA' and producto.talle.strip():
            if 'SIZE' not in attribute_ids_added:
                attributes.append({
                    'id': 'SIZE',
                    'name': 'Talle',
                    'value_name': producto.talle.strip()
                })
                attribute_ids_added.add('SIZE')
        
        # Siempre agregar atributos, incluso si está vacío (ML puede requerirlo)
        item_data['attributes'] = attributes
        
        # Log para debugging - mostrar qué atributos se están enviando
        logger.info(f"Atributos agregados para {producto.nombre}: {[a.get('id') for a in attributes]}")
        logger.debug(f"Detalles de atributos enviados: {json.dumps(attributes, indent=2, ensure_ascii=False)}")
        
        # Verificar que los atributos requeridos estén presentes
        required_attr_ids = [attr.get('id') for attr in required_attributes]
        sent_attr_ids = [a.get('id') for a in attributes]
        missing_attrs = [attr_id for attr_id in required_attr_ids if attr_id not in sent_attr_ids]
        
        # Siempre verificar que MODEL, MANUFACTURER y MATERIAL (si está en requeridos) estén presentes
        # aunque no estén marcados como "required" en los tags de la API
        critical_attrs = ['MODEL', 'MANUFACTURER']
        # Agregar MATERIAL a críticos si está en los atributos requeridos
        if any(attr.get('id') == 'MATERIAL' for attr in required_attributes):
            critical_attrs.append('MATERIAL')
        for critical_attr in critical_attrs:
            if critical_attr not in sent_attr_ids:
                if critical_attr == 'MODEL':
                    attributes.append({
                        'id': 'MODEL',
                        'value_name': producto.nombre[:50] if producto.nombre else 'Modelo genérico'
                    })
                    logger.warning(f"Agregando MODEL crítico faltante con valor: {producto.nombre[:50] if producto.nombre else 'Modelo genérico'}")
                elif critical_attr == 'MANUFACTURER':
                    attributes.append({
                        'id': 'MANUFACTURER',
                        'value_name': 'Sin marca'
                    })
                    logger.warning(f"Agregando MANUFACTURER crítico faltante con valor: Sin marca")
                elif critical_attr == 'MATERIAL':
                    # Buscar el atributo MATERIAL en required_attributes para obtener valores posibles
                    material_attr = next((attr for attr in required_attributes if attr.get('id') == 'MATERIAL'), None)
                    if material_attr and material_attr.get('values') and len(material_attr.get('values', [])) > 0:
                        # Usar el primer valor disponible (generalmente "Madera" para muebles)
                        first_value = material_attr.get('values', [{}])[0]
                        material_value = {
                            'id': 'MATERIAL',
                        }
                        if first_value.get('id'):
                            material_value['value_id'] = first_value.get('id')
                        material_value['value_name'] = first_value.get('name', 'Madera')
                        attributes.append(material_value)
                        logger.warning(f"Agregando MATERIAL crítico faltante con valor: {material_value.get('value_name')}")
                    else:
                        # Si no hay valores predefinidos, usar "Madera" como valor por defecto para muebles
                        attributes.append({
                            'id': 'MATERIAL',
                            'value_name': 'Madera'
                        })
                        logger.warning(f"Agregando MATERIAL crítico faltante con valor: Madera")
        
        if missing_attrs:
            logger.error(f"⚠️ ERROR: Atributos requeridos faltantes para {producto.nombre}: {missing_attrs}")
            logger.error(f"   Atributos requeridos: {required_attr_ids}")
            logger.error(f"   Atributos enviados: {sent_attr_ids}")
            
            # Intentar agregar los atributos faltantes con valores por defecto
            for missing_attr_id in missing_attrs:
                if missing_attr_id not in ['MODEL', 'MANUFACTURER', 'MATERIAL']:  # Ya los agregamos arriba
                    # Buscar el atributo en required_attributes para obtener más información
                    missing_attr_info = next((attr for attr in required_attributes if attr.get('id') == missing_attr_id), None)
                    
                    attr_to_add = {'id': missing_attr_id}
                    if missing_attr_info:
                        # Si tiene valores predefinidos, usar el primero disponible
                        if missing_attr_info.get('values') and len(missing_attr_info.get('values', [])) > 0:
                            first_value = missing_attr_info.get('values', [{}])[0]
                            if first_value.get('id'):
                                attr_to_add['value_id'] = first_value.get('id')
                            attr_to_add['value_name'] = first_value.get('name', 'No especificado')
                        else:
                            # Si no hay valores predefinidos, usar un valor por defecto según el tipo
                            if missing_attr_info.get('value_type') == 'number':
                                attr_to_add['value_name'] = str(missing_attr_info.get('default_value', '0'))
                            else:
                                attr_to_add['value_name'] = missing_attr_info.get('default_value', 'No especificado')
                    else:
                        attr_to_add['value_name'] = 'No especificado'
                    
                    attributes.append(attr_to_add)
                    logger.warning(f"Agregando {missing_attr_id} faltante con valor: {attr_to_add.get('value_name')}")
        
        try:
            # Si el producto ya está sincronizado, intentar actualizar
            item_updated = False
            if hasattr(producto, 'ml_item_id') and producto.ml_item_id:
                logger.info(f"Actualizando producto existente en ML: {producto.ml_item_id}")
                try:
                    updated_item = self.update_item(producto.ml_item_id, {
                        'title': item_data['title'],
                        'price': item_data['price'],
                        'available_quantity': item_data['available_quantity'],
                        'description': item_data.get('description')
                    })
                    
                    # Actualizar fecha de sincronización
                    producto.ml_ultima_sincronizacion = timezone.now()
                    producto.save()
                    
                    return updated_item
                except (requests.exceptions.HTTPError, ValueError) as e:
                    error_data = None
                    error_message = ""
                    
                    # Si es un ValueError, el mensaje ya está en str(e)
                    if isinstance(e, ValueError):
                        error_message = str(e)
                        # Si el ValueError menciona "no se puede modificar", limpiar y crear nuevo
                        if 'no se puede modificar' in error_message.lower() or 'cannot be modified' in error_message.lower():
                            logger.warning(f"Item {producto.ml_item_id} no se puede modificar. Limpiando ml_item_id y creando producto nuevo.")
                            logger.warning(f"Error detallado: {error_message}")
                            # Limpiar ml_item_id para crear como nuevo
                            Producto.objects.filter(id=producto.id).update(ml_item_id=None, ml_sincronizado=False)
                            producto.ml_item_id = None
                            producto.ml_sincronizado = False
                            item_updated = False  # Marcar para crear nuevo
                            # Continuar para crear nuevo producto
                        else:
                            # Si es otro ValueError, re-lanzarlo
                            raise
                    else:
                        # Es un HTTPError
                        # Obtener información del error
                        if e.response is not None:
                            try:
                                error_data = e.response.json()
                                error_message = error_data.get('message', '')
                            except:
                                error_message = str(e)
                        
                        # Si el item está cerrado o no existe, crear uno nuevo
                        if e.response is not None and e.response.status_code == 400:
                            # Detectar si el error es porque el item no es modificable
                            # ML puede devolver errores como "is not modifiable", "not_modifiable", etc.
                            error_lower = error_message.lower()
                            causes_lower = []
                            if error_data and 'cause' in error_data:
                                for cause in error_data.get('cause', []):
                                    cause_msg = cause.get('message', '').lower()
                                    causes_lower.append(cause_msg)
                            
                            is_not_modifiable = (
                                'not_modifiable' in error_lower or 
                                'is not modifiable' in error_lower or
                                'cannot be modified' in error_lower or
                                'no se puede modificar' in error_lower or
                                any('not modifiable' in msg for msg in causes_lower) or
                                any('is not modifiable' in msg for msg in causes_lower)
                            )
                            
                            if 'status:closed' in error_message or is_not_modifiable:
                                logger.warning(f"Item {producto.ml_item_id} está cerrado o no se puede modificar. Limpiando ml_item_id y creando producto nuevo.")
                                logger.warning(f"Error detallado: {error_message}")
                                # Limpiar ml_item_id para crear como nuevo
                                Producto.objects.filter(id=producto.id).update(ml_item_id=None, ml_sincronizado=False)
                                producto.ml_item_id = None
                                producto.ml_sincronizado = False
                                item_updated = False  # Marcar para crear nuevo
                        
                        # Si es un error 403, puede ser una restricción de política de ML
                        if e.response is not None and e.response.status_code == 403:
                            logger.warning(f"Error 403 al actualizar item {producto.ml_item_id}. Verificando si el item existe...")
                            try:
                                # Intentar obtener el item para verificar que existe
                                existing_item = self.get_item(producto.ml_item_id)
                                if existing_item:
                                    item_status = existing_item.get('status', '')
                                    # Si el item está cerrado, limpiar y crear nuevo
                                    if item_status == 'closed':
                                        logger.warning(f"Item {producto.ml_item_id} está cerrado. Limpiando ml_item_id y creando producto nuevo.")
                                        Producto.objects.filter(id=producto.id).update(ml_item_id=None, ml_sincronizado=False)
                                        producto.ml_item_id = None
                                        producto.ml_sincronizado = False
                                        item_updated = False  # Marcar para crear nuevo
                                    else:
                                        logger.warning(f"Item {producto.ml_item_id} existe en ML pero no se pudo actualizar (403). Esto puede ser una restricción temporal de ML.")
                                        # Considerar la sincronización como exitosa aunque no se pudo actualizar
                                        producto.ml_ultima_sincronizacion = timezone.now()
                                        producto.save()
                                        return existing_item
                            except Exception as get_error:
                                logger.warning(f"Error al verificar item {producto.ml_item_id}: {get_error}. Limpiando ml_item_id y creando producto nuevo.")
                                # Si no se puede obtener el item, limpiar y crear nuevo
                                Producto.objects.filter(id=producto.id).update(ml_item_id=None, ml_sincronizado=False)
                                producto.ml_item_id = None
                                producto.ml_sincronizado = False
                                item_updated = False  # Marcar para crear nuevo
                        else:
                            # Para otros errores HTTP, lanzar el error original
                            if not isinstance(e, ValueError):
                                raise
            
            # Si el producto no tiene ml_item_id o no se pudo actualizar, crear uno nuevo
            if not hasattr(producto, 'ml_item_id') or not producto.ml_item_id:
                logger.info(f"Creando nuevo producto en ML: {producto.nombre}")
                
                # Intentar crear el producto, si falla por cantidad, extraer el máximo permitido
                try:
                    created_item = self.create_item(item_data)
                except (ValueError, requests.exceptions.RequestException) as e:
                    error_str = str(e)
                    # Si el error es por cantidad disponible, intentar extraer el máximo permitido
                    if 'available_quantity' in error_str.lower() or 'quantity max' in error_str.lower() or 'max. value' in error_str.lower():
                        # Intentar extraer el máximo del mensaje de error
                        max_allowed = None
                        max_match = re.search(r'max\.?\s*value\s*is\s*(\d+)', error_str, re.IGNORECASE)
                        if max_match:
                            max_allowed = int(max_match.group(1))
                            logger.warning(f"Error por cantidad disponible. Máximo permitido para esta categoría: {max_allowed}. Ajustando cantidad.")
                        else:
                            # Si no se puede extraer, intentar obtener el error completo de la respuesta
                            if hasattr(e, 'response') and e.response is not None:
                                try:
                                    error_data = e.response.json()
                                    causes = error_data.get('cause', [])
                                    for cause in causes:
                                        if cause.get('code') == 'item.available_quantity.invalid':
                                            message = cause.get('message', '')
                                            max_match = re.search(r'max\.?\s*value\s*is\s*(\d+)', message, re.IGNORECASE)
                                            if max_match:
                                                max_allowed = int(max_match.group(1))
                                                logger.warning(f"Error por cantidad disponible. Máximo permitido para esta categoría: {max_allowed}. Ajustando cantidad.")
                                                break
                                except:
                                    pass
                        
                        # Si no se pudo extraer el máximo, usar 1 como fallback
                        if max_allowed is None:
                            logger.warning(f"Error por cantidad disponible, no se pudo extraer el máximo. Intentando con cantidad 1")
                            max_allowed = 1
                        
                        item_data['available_quantity'] = max_allowed
                        try:
                            created_item = self.create_item(item_data)
                            logger.info(f"Producto creado con cantidad {max_allowed} (máximo permitido para esta categoría)")
                        except Exception as e2:
                            logger.error(f"No se pudo crear el producto ni con cantidad {max_allowed}: {e2}")
                            raise ValueError(
                                f"Este producto tiene una limitación de stock máximo de {max_allowed} unidades "
                                f"en Mercado Libre debido a su categoría. Stock en sistema: {producto.stock}. "
                                f"Error: {str(e2)}"
                            )
                    # Si el error es por listing type temporalmente no disponible, intentar con otro listing type
                    elif 'listing type' in error_str.lower() and 'temporarily unavailable' in error_str.lower():
                        logger.warning(f"Listing type '{listing_type}' temporalmente no disponible, intentando con 'bronze'")
                        # Intentar con listing type 'bronze' que puede estar disponible
                        item_data['listing_type_id'] = 'bronze'
                        # 'bronze' requiere al menos una imagen, asegurar que esté presente
                        if 'pictures' not in item_data or not item_data.get('pictures'):
                            item_data['pictures'] = [{
                                'source': 'https://http2.mlstatic.com/storage/developers-site-cms-admin/openapi/319968599067-mp.png'
                            }]
                        try:
                            created_item = self.create_item(item_data)
                            logger.info(f"Producto creado exitosamente con listing type 'bronze'")
                        except ValueError as e2:
                            logger.error(f"No se pudo crear con listing type 'bronze' tampoco: {e2}")
                            raise ValueError(
                                f"El tipo de publicación está temporalmente no disponible en Mercado Libre. "
                                f"Por favor, intenta nuevamente más tarde. "
                                f"Detalle: {error_str}"
                            )
                    # Si el error es de shipping, dar un mensaje más claro
                    elif 'shipping' in error_str.lower() or 'lost_me1' in error_str.lower() or 'mode me1' in error_str.lower():
                        logger.error(f"Error de configuración de envío en Mercado Libre: {error_str}")
                        raise ValueError(
                            f"No se puede crear el producto debido a problemas de configuración de envío en Mercado Libre. "
                            f"Por favor, configura tus preferencias de envío en tu cuenta de Mercado Libre. "
                            f"Detalle: {error_str}"
                        )
                    else:
                        raise
                
                # Guardar el ID de Mercado Libre en el producto
                # Usar update para evitar que el signal se dispare y cause problemas
                ml_item_id = created_item.get('id')
                if ml_item_id:
                    # Actualizar en la base de datos
                    updated_count = Producto.objects.filter(id=producto.id).update(
                        ml_item_id=ml_item_id,
                        ml_sincronizado=True,
                        ml_ultima_sincronizacion=timezone.now()
                    )
                    
                    if updated_count == 0:
                        logger.error(f"Error: No se pudo actualizar el producto {producto.id} con ml_item_id {ml_item_id}")
                        raise ValueError(f"No se pudo guardar el ml_item_id en la base de datos")
                    
                    # Actualizar también el objeto en memoria para que esté sincronizado
                    producto.ml_item_id = ml_item_id
                    producto.ml_sincronizado = True
                    producto.ml_ultima_sincronizacion = timezone.now()
                    
                    logger.info(f"Producto {producto.nombre} sincronizado exitosamente. ML Item ID guardado: {ml_item_id}")
                    
                    # Verificar que se guardó correctamente
                    producto_verificado = Producto.objects.get(id=producto.id)
                    if producto_verificado.ml_item_id != ml_item_id:
                        logger.error(f"ERROR CRÍTICO: ml_item_id no se guardó correctamente. Esperado: {ml_item_id}, Obtenido: {producto_verificado.ml_item_id}")
                        raise ValueError(f"El ml_item_id no se guardó correctamente en la base de datos")
                else:
                    logger.error(f"Error: El item creado en ML no tiene ID. Respuesta: {created_item}")
                    raise ValueError("El item creado en ML no tiene ID válido")
                
                return created_item
                
        except (requests.exceptions.RequestException, ValueError) as e:
            error_msg = str(e)
            logger.error(f"Error al sincronizar producto {producto.id} a ML: {error_msg}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Error detallado ML: {error_data}")
                    # Extraer mensaje más descriptivo
                    if isinstance(error_data, dict):
                        if 'message' in error_data:
                            error_msg = error_data['message']
                        elif 'error' in error_data:
                            error_msg = error_data['error']
                        elif 'cause' in error_data and isinstance(error_data['cause'], list):
                            error_msg = '; '.join([c.get('message', str(c)) for c in error_data['cause']])
                except:
                    if hasattr(e.response, 'text'):
                        logger.error(f"Respuesta del servidor: {e.response.text}")
            raise ValueError(error_msg)
    
    def sync_stock(self, producto):
        """
        Sincroniza solo el stock de un producto a Mercado Libre
        
        Args:
            producto: Instancia del modelo Producto con ml_item_id configurado
            
        Returns:
            dict con el item actualizado
            
        Raises:
            ValueError: Si hay un error al actualizar el stock
        """
        if not hasattr(producto, 'ml_item_id') or not producto.ml_item_id:
            raise ValueError(f"Producto {producto.id} no está sincronizado con Mercado Libre (falta ml_item_id)")
        
        stock_real = max(0, producto.stock)
        logger.info(f"Intentando actualizar stock de {producto.nombre} (ML Item: {producto.ml_item_id}) a {stock_real} unidades")
        
        try:
            return self.update_stock(producto.ml_item_id, stock_real)
        except ValueError as e:
            # Re-lanzar ValueError con información adicional
            error_msg = str(e)
            # Si el error menciona un máximo permitido, incluir información del stock real
            if 'limitación' in error_msg.lower() or 'máximo' in error_msg.lower():
                raise ValueError(
                    f"Stock en sistema: {stock_real} unidades. {error_msg}"
                )
            raise
    
    def sync_precio(self, producto):
        """
        Sincroniza solo el precio de un producto a Mercado Libre
        
        Args:
            producto: Instancia del modelo Producto con ml_item_id configurado
            
        Returns:
            dict con el item actualizado
        """
        if not hasattr(producto, 'ml_item_id') or not producto.ml_item_id:
            raise ValueError(f"Producto {producto.id} no está sincronizado con Mercado Libre (falta ml_item_id)")
        
        return self.update_price(producto.ml_item_id, float(producto.precio))
    
    def get_orders(self, limit=50, offset=0, status=None):
        """
        Obtiene la lista de órdenes del vendedor desde Mercado Libre
        
        Args:
            limit: Cantidad de órdenes a retornar (máx 50)
            offset: Offset para paginación
            status: Estado de las órdenes a filtrar (opcional). Ej: 'confirmed', 'payment_required', 'payment_in_process'
            
        Returns:
            dict con las órdenes y metadata de paginación, o None si hay error
        """
        self.ensure_valid_token()
        
        if not self.user_id:
            raise ValueError("User ID no configurado. Complete el flujo OAuth primero.")
        
        try:
            url = f"{self.base_url}/orders/search"
            headers = self.get_headers()
            params = {
                'seller': self.user_id,
                'limit': min(limit, 50),
                'offset': offset
            }
            
            # Agregar filtro de estado si se proporciona
            if status:
                params['order.status'] = status
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            orders_data = response.json()
            logger.info(f"Órdenes obtenidas exitosamente: {len(orders_data.get('results', []))} órdenes")
            return orders_data
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if e.response.status_code == 401:
                    logger.error(f"Token inválido al obtener órdenes")
                    self.refresh_access_token()
                    # Reintentar una vez
                    try:
                        response = requests.get(url, headers=headers, params=params, timeout=30)
                        response.raise_for_status()
                        return response.json()
                    except:
                        return None
                else:
                    logger.error(f"Error HTTP {e.response.status_code} al obtener órdenes: {e.response.text}")
            logger.error(f"Error al obtener órdenes: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al obtener órdenes: {e}")
            return None
    
    def create_producto_from_ml_item(self, tienda, ml_item_data):
        """
        Crea o actualiza un producto en Total Stock a partir de los datos de un item de Mercado Libre.
        
        Args:
            tienda: Instancia del modelo Tienda
            ml_item_data: dict con los datos del item de ML (de get_item o de order_items)
            
        Returns:
            Producto: La instancia del producto creada o actualizada, o None si falla
        """
        ml_item_id = ml_item_data.get('id') or (ml_item_data.get('item', {}).get('id') if isinstance(ml_item_data.get('item'), dict) else None)
        if not ml_item_id:
            logger.error("No se pudo obtener ml_item_id de los datos del item")
            return None
        
        # Obtener datos del item - puede venir de get_item (completo) o de order_items (parcial)
        if 'item' in ml_item_data and isinstance(ml_item_data.get('item'), dict):
            item_info = ml_item_data.get('item', {})
        else:
            item_info = ml_item_data
        
        nombre = item_info.get('title') or item_info.get('name') or f"Producto ML {ml_item_id}"
        precio = float(item_info.get('price', 0))
        stock = int(item_info.get('available_quantity', 0))
        categoria_ml_id = item_info.get('category_id')
        descripcion = None
        if isinstance(item_info.get('description'), dict):
            descripcion = item_info.get('description', {}).get('plain_text', '')
        elif isinstance(item_info.get('description'), str):
            descripcion = item_info.get('description', '')
        
        # Buscar si ya existe el producto vinculado
        producto_existente = Producto.objects.filter(tienda=tienda, ml_item_id=ml_item_id).first()
        
        if producto_existente:
            # Actualizar producto existente
            producto_existente.nombre = nombre[:200]
            producto_existente.precio = precio if precio > 0 else producto_existente.precio
            producto_existente.stock = stock
            if descripcion:
                producto_existente.descripcion = descripcion[:5000]
            if categoria_ml_id:
                producto_existente.ml_categoria_id = categoria_ml_id
            producto_existente.ml_sincronizado = True
            producto_existente.ml_ultima_sincronizacion = timezone.now()
            producto_existente.save()
            logger.info(f"Producto actualizado desde ML: {producto_existente.nombre} (ml_item_id: {ml_item_id})")
            return producto_existente
        
        # Crear nuevo producto (nombre + sufijo ML para unicidad con unique_together)
        nombre_final = f"{nombre[:185]} (ML-{ml_item_id})" if len(nombre) > 185 else f"{nombre} (ML-{ml_item_id})"
        producto = Producto.objects.create(
            tienda=tienda,
            nombre=nombre_final,
            descripcion=descripcion[:5000] if descripcion else None,
            precio=Decimal(str(precio)) if precio > 0 else Decimal('0.01'),
            stock=max(0, stock),
            ml_item_id=ml_item_id,
            ml_sincronizado=True,
            ml_ultima_sincronizacion=timezone.now(),
            ml_categoria_id=categoria_ml_id or None
        )
        logger.info(f"Producto creado desde ML: {producto.nombre} (ml_item_id: {ml_item_id})")
        return producto
    
    def get_order(self, order_id):
        """
        Obtiene información de una orden/pedido de Mercado Libre
        
        Args:
            order_id: ID de la orden en Mercado Libre
            
        Returns:
            dict con la información de la orden, o None si hay error
        """
        self.ensure_valid_token()
        
        try:
            url = f"{self.base_url}/orders/{order_id}"
            headers = {
                'Authorization': f'Bearer {self.tienda.ml_access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            order_data = response.json()
            logger.info(f"Orden {order_id} obtenida exitosamente")
            return order_data
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if e.response.status_code == 404:
                    logger.warning(f"Orden {order_id} no encontrada")
                    return None
                elif e.response.status_code == 401:
                    logger.error(f"Token inválido al obtener orden {order_id}")
                    self.refresh_access_token()
                    # Reintentar una vez
                    try:
                        headers = {
                            'Authorization': f'Bearer {self.tienda.ml_access_token}',
                            'Content-Type': 'application/json'
                        }
                        response = requests.get(url, headers=headers, timeout=10)
                        response.raise_for_status()
                        return response.json()
                    except:
                        return None
            logger.error(f"Error al obtener orden {order_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al obtener orden {order_id}: {e}")
            return None
    
    def get_order_billing_info(self, order_id):
        """
        Obtiene datos de facturación del comprador para una orden (nombre, apellido, documento, dirección).
        Útil para emitir facturas con datos reales del cliente.
        Documentación: https://developers.mercadolibre.com.ar/es_ar/billing-data
        
        Args:
            order_id: ID de la orden en Mercado Libre
            
        Returns:
            dict con name, last_name, identification (type + number), address, o None si no está disponible
        """
        self.ensure_valid_token()
        try:
            url = f"{self.base_url}/orders/{order_id}/billing_info"
            headers = {
                'Authorization': f'Bearer {self.tienda.ml_access_token}',
                'Content-Type': 'application/json',
                'x-version': '2',
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Billing info obtenido para orden {order_id}")
            return data
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.debug(f"Billing info no disponible para orden {order_id}")
            else:
                logger.warning(f"Error al obtener billing info para orden {order_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error inesperado al obtener billing info {order_id}: {e}")
            return None
