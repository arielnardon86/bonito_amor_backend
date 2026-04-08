# inventario/services/mercadolibre_service.py
"""
Servicio de integración con Mercado Libre API
Proporciona métodos para autenticación OAuth y sincronización de productos
"""
import os
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

# User-Agent: CloudFront WAF bloquea requests con UA de bot. Usamos uno tipo navegador
# para OAuth (exchange_token, refresh) que recibe tráfico más estricto.
# Incluimos X-App-Name para identificar nuestra app en logs si ML lo soporta.
ML_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)
ML_USER_AGENT_API = 'TotalStock/1.0 (https://github.com/arielnardon86/bonito_amor_backend)'


def _get_oauth_headers():
    """Headers tipo navegador para OAuth. CloudFront WAF bloquea requests de datacenter/bot."""
    return {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'User-Agent': ML_USER_AGENT,
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://auth.mercadolibre.com.ar/',
        'Origin': 'https://auth.mercadolibre.com.ar',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }


def _get_oauth_proxies():
    """
    Proxy opcional para OAuth. Si ML_OAUTH_PROXY está definido (ej. http://user:pass@host:port),
    las peticiones a /oauth/token pasan por ahí. Útil si CloudFront bloquea la IP del servidor.
    """
    url = os.environ.get('ML_OAUTH_PROXY', '').strip()
    if url:
        return {'http': url, 'https': url}
    return None


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
            'User-Agent': ML_USER_AGENT_API,
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
        headers = _get_oauth_headers()
        proxies = _get_oauth_proxies()
        req_kw = {'data': data, 'headers': headers, 'timeout': 30}
        if proxies:
            req_kw['proxies'] = proxies
        
        try:
            response = requests.post(self.token_url, **req_kw)
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
        headers = _get_oauth_headers()
        proxies = _get_oauth_proxies()
        req_kw = {'data': data, 'headers': headers, 'timeout': 30}
        if proxies:
            req_kw['proxies'] = proxies
        
        try:
            response = requests.post(self.token_url, **req_kw)
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

    def get_items_with_details(self, limit=100, offset=0):
        """
        Obtiene items del vendedor con datos completos (id, title, price, thumbnail, available_quantity).
        Usa multiget /items?ids= para obtener hasta 20 items por request.
        
        Returns:
            dict con items: [{id, title, price, available_quantity, thumbnail, ...}], paging: {total}
        """
        self.ensure_valid_token()
        ids_data = self.get_items(limit=min(limit, 200), offset=offset)
        all_ids = ids_data.get('results', [])
        paging = ids_data.get('paging', {})
        total = paging.get('total', len(all_ids))
        
        items_with_details = []
        for i in range(0, len(all_ids), 20):
            batch_ids = all_ids[i:i + 20]
            ids_str = ','.join(batch_ids)
            try:
                response = requests.get(
                    f"{self.base_url}/items",
                    headers=self.get_headers(),
                    params={'ids': ids_str},
                    timeout=30
                )
                response.raise_for_status()
                batch = response.json()
                if isinstance(batch, list):
                    for r in batch:
                        if r.get('code') == 200 and r.get('body'):
                            b = r['body']
                            item_id = b.get('id')
                            thumb = ''
                            if b.get('thumbnail'):
                                thumb = b['thumbnail']
                            elif b.get('pictures') and len(b['pictures']) > 0:
                                thumb = b['pictures'][0].get('url', b['pictures'][0].get('secure_url', ''))
                            # Preferir sale_price (precio con descuento/promoción) sobre price (precio base)
                            price_val = float(b.get('price', 0))
                            sale_data = self.get_sale_price(item_id)
                            if sale_data is not None and sale_data.get('amount') is not None:
                                try:
                                    price_val = float(sale_data['amount'])
                                except (TypeError, ValueError):
                                    pass
                            items_with_details.append({
                                'id': item_id,
                                'title': b.get('title', ''),
                                'price': price_val,
                                'available_quantity': int(b.get('available_quantity', 0)),
                                'thumbnail': thumb
                            })
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error en multiget items: {e}")
        
        return {'items': items_with_details, 'paging': {'total': total, 'offset': offset, 'limit': limit}}
    
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
            status: Estado de las órdenes a filtrar (opcional). Ej: 'confirmed', 'payment_required', 'payment_in_process', 'paid'
            
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
        # Preferir sale_price (precio con descuento) sobre price (precio base)
        precio = None
        sale_data = self.get_sale_price(ml_item_id)
        if sale_data is not None and sale_data.get('amount') is not None:
            try:
                precio = float(sale_data['amount'])
            except (TypeError, ValueError):
                pass
        if precio is None or precio <= 0:
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
                'Content-Type': 'application/json',
                'User-Agent': ML_USER_AGENT_API,
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
                            'Content-Type': 'application/json',
                            'User-Agent': ML_USER_AGENT_API,
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
    
    def get_payment(self, payment_id):
        """
        Obtiene datos de un pago desde /collections/{payment_id}.
        Devuelve el dict 'collection' con marketplace_fee, shipping_cost,
        taxes_amount y order_id, o None si hay error.
        """
        self.ensure_valid_token()
        try:
            url = f"{self.base_url}/collections/{payment_id}"
            headers = {
                'Authorization': f'Bearer {self.tienda.ml_access_token}',
                'Content-Type': 'application/json',
                'User-Agent': ML_USER_AGENT_API,
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Payment {payment_id} obtenido exitosamente")
            return data.get('collection') or data
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.warning(f"Payment {payment_id} no encontrado")
            else:
                logger.warning(f"Error al obtener payment {payment_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al obtener payment {payment_id}: {e}")
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
                'User-Agent': ML_USER_AGENT_API,
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