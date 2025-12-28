"""
Servicio de facturación electrónica para AFIP y ARCA
"""
import base64
import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from django.conf import settings

# Importaciones opcionales para AFIP
try:
    from pyafipws.wsaa import WSAA
    from pyafipws.wsfev1 import WSFEv1
    PYAFIPWS_AVAILABLE = True
except ImportError:
    WSAA = None
    WSFEv1 = None
    PYAFIPWS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class FacturacionService:
    """Servicio para emitir facturas electrónicas a través de AFIP o ARCA"""
    
    def __init__(self, tienda):
        self.tienda = tienda
        self.sistema = tienda.tipo_facturacion
        
    def emitir_factura(self, venta, cliente_data: Dict) -> Tuple[bool, Dict, Optional[str]]:
        """
        Emite una factura electrónica para una venta.
        
        Args:
            venta: Instancia del modelo Venta
            cliente_data: Diccionario con datos del cliente (nombre, cuit, domicilio, etc.)
            
        Returns:
            Tuple con (éxito: bool, datos_factura: dict, error: str o None)
        """
        if self.sistema == 'AFIP':
            return self._emitir_afip(venta, cliente_data)
        elif self.sistema == 'ARCA':
            return self._emitir_arca(venta, cliente_data)
        else:
            return False, {}, "Sistema de facturación no configurado para esta tienda"
    
    def _emitir_afip(self, venta, cliente_data: Dict) -> Tuple[bool, Dict, Optional[str]]:
        """Emitir factura a través de AFIP"""
        if not PYAFIPWS_AVAILABLE:
            return False, {}, "pyafipws no está instalado. Instala con: pip install pyafipws"
        
        try:
            # Validar configuración
            if not self.tienda.cuit:
                return False, {}, "CUIT no configurado para la tienda"
            
            if not self.tienda.certificado_afip or not self.tienda.clave_privada_afip:
                return False, {}, "Certificados AFIP no configurados"
            
            # Decodificar certificados
            try:
                # Limpiar el base64 (remover saltos de línea, espacios, etc.)
                cert_b64 = self.tienda.certificado_afip.strip().replace('\n', '').replace('\r', '').replace(' ', '')
                key_b64 = self.tienda.clave_privada_afip.strip().replace('\n', '').replace('\r', '').replace(' ', '')
                
                # Remover encabezados/footers si existen (BEGIN CERTIFICATE, etc.)
                cert_b64 = cert_b64.replace('-----BEGINCERTIFICATE-----', '').replace('-----ENDCERTIFICATE-----', '')
                cert_b64 = cert_b64.replace('-----BEGIN CERTIFICATE-----', '').replace('-----END CERTIFICATE-----', '')
                key_b64 = key_b64.replace('-----BEGINPRIVATEKEY-----', '').replace('-----ENDPRIVATEKEY-----', '')
                key_b64 = key_b64.replace('-----BEGIN PRIVATE KEY-----', '').replace('-----END PRIVATE KEY-----', '')
                key_b64 = key_b64.replace('-----BEGINRSAPRIVATEKEY-----', '').replace('-----ENDRSAPRIVATEKEY-----', '')
                key_b64 = key_b64.replace('-----BEGIN RSA PRIVATE KEY-----', '').replace('-----END RSA PRIVATE KEY-----', '')
                
                # Verificar que el base64 sea válido (solo contiene caracteres válidos de base64)
                import re
                base64_pattern = re.compile(r'^[A-Za-z0-9+/=]+$')
                
                if not base64_pattern.match(cert_b64):
                    return False, {}, f"Error: El certificado AFIP no parece estar en formato base64 válido. Usa el comando 'python manage.py convertir_certificados_afip certificado.crt clave.key' para convertir los certificados correctamente."
                
                if not base64_pattern.match(key_b64):
                    return False, {}, f"Error: La clave privada AFIP no parece estar en formato base64 válido. Usa el comando 'python manage.py convertir_certificados_afip certificado.crt clave.key' para convertir los certificados correctamente."
                
                # Decodificar base64 a binario
                try:
                    cert_data = base64.b64decode(cert_b64, validate=True)
                    key_data = base64.b64decode(key_b64, validate=True)
                except base64.binascii.Error as e:
                    return False, {}, f"Error al decodificar certificados base64: {str(e)}. Los certificados no están correctamente codificados en base64. Usa el comando 'python manage.py convertir_certificados_afip certificado.crt clave.key' para convertirlos correctamente."
                except Exception as e:
                    return False, {}, f"Error al decodificar certificados: {str(e)}. Verifica que los certificados estén correctamente codificados en base64."
                
                # Verificar que los datos decodificados no estén vacíos
                if not cert_data or len(cert_data) == 0:
                    return False, {}, "Error: El certificado decodificado está vacío. Verifica que el certificado base64 sea correcto."
                
                if not key_data or len(key_data) == 0:
                    return False, {}, "Error: La clave privada decodificada está vacía. Verifica que la clave privada base64 sea correcta."
                
                # Verificar que los certificados tengan formato PEM válido
                # Los archivos PEM deben empezar con "-----BEGIN" y terminar con "-----END"
                cert_str = cert_data.decode('utf-8', errors='ignore')
                key_str = key_data.decode('utf-8', errors='ignore')
                
                if not cert_str.strip().startswith('-----BEGIN'):
                    logger.warning(f"⚠️ El certificado no parece tener formato PEM válido. Primeros 100 caracteres: {cert_str[:100]}")
                    # Intentar detectar si es DER y convertirlo
                    try:
                        from cryptography import x509
                        from cryptography.hazmat.backends import default_backend
                        # Intentar cargar como DER
                        cert_obj = x509.load_der_x509_certificate(cert_data, default_backend())
                        # Convertir a PEM
                        from cryptography.hazmat.primitives import serialization
                        cert_pem = cert_obj.public_bytes(serialization.Encoding.PEM)
                        cert_data = cert_pem
                        logger.info(f"✅ Certificado convertido de DER a PEM")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo convertir certificado DER a PEM: {e}")
                        # Continuar de todas formas, algunos archivos pueden funcionar sin headers
                
                if not key_str.strip().startswith('-----BEGIN'):
                    logger.warning(f"⚠️ La clave privada no parece tener formato PEM válido. Primeros 100 caracteres: {key_str[:100]}")
                    # Intentar detectar si es DER y convertirlo
                    try:
                        from cryptography.hazmat.primitives import serialization
                        from cryptography.hazmat.backends import default_backend
                        # Intentar cargar como DER
                        key_obj = serialization.load_der_private_key(key_data, password=None, backend=default_backend())
                        # Convertir a PEM
                        key_pem = key_obj.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption()
                        )
                        key_data = key_pem
                        logger.info(f"✅ Clave privada convertida de DER a PEM")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo convertir clave DER a PEM: {e}")
                        # Continuar de todas formas
                
                logger.info(f"✅ Certificados decodificados correctamente. Certificado: {len(cert_data)} bytes, Clave: {len(key_data)} bytes")
                
            except UnicodeDecodeError as e:
                return False, {}, f"Error: Los certificados no están en formato base64 válido. Puede que hayas pegado el contenido del archivo directamente sin convertirlo a base64. Usa el comando 'python manage.py convertir_certificados_afip certificado.crt clave.key' para convertir los certificados correctamente. Error: {str(e)}"
            except Exception as e:
                return False, {}, f"Error al procesar certificados: {str(e)}. Asegúrate de usar el comando 'python manage.py convertir_certificados_afip certificado.crt clave.key' para convertir los certificados a base64 antes de pegarlos en el admin."
            
            # Configurar WSAA (Web Service de Autenticación y Autorización)
            wsaa = WSAA()
            
            # Generar archivos temporales para certificados
            import tempfile
            import os
            
            # Asegurarnos de que los datos sean bytes
            if isinstance(cert_data, str):
                cert_data = cert_data.encode('utf-8')
            if isinstance(key_data, str):
                key_data = key_data.encode('utf-8')
            
            # Verificar que los archivos sean PEM válidos antes de escribirlos
            try:
                cert_str = cert_data.decode('utf-8') if isinstance(cert_data, bytes) else cert_data
                if not cert_str.strip().startswith('-----BEGIN'):
                    logger.warning(f"⚠️ Advertencia: El certificado podría no tener formato PEM válido")
                    logger.debug(f"Primeros 200 caracteres del certificado: {cert_str[:200]}")
            except:
                pass
            
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.crt') as cert_file:
                cert_file.write(cert_data)
                cert_file.flush()  # Asegurar que se escriba al disco
                cert_path = cert_file.name
                os.chmod(cert_path, 0o600)  # Permisos de lectura/escritura solo para el usuario
                logger.info(f"✅ Certificado temporal creado: {cert_path}")
            
            try:
                key_str = key_data.decode('utf-8') if isinstance(key_data, bytes) else key_data
                if not key_str.strip().startswith('-----BEGIN'):
                    logger.warning(f"⚠️ Advertencia: La clave privada podría no tener formato PEM válido")
                    logger.debug(f"Primeros 200 caracteres de la clave: {key_str[:200]}")
            except:
                pass
            
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.key') as key_file:
                key_file.write(key_data)
                key_file.flush()  # Asegurar que se escriba al disco
                key_path = key_file.name
                os.chmod(key_path, 0o600)  # Permisos de lectura/escritura solo para el usuario
                logger.info(f"✅ Clave privada temporal creada: {key_path}")
            
            try:
                # Obtener ticket de acceso (TA)
                modo = 'testing' if self.tienda.modo_test_afip else 'prod'
                
                # Verificar que los archivos existen y tienen contenido
                if not os.path.exists(cert_path) or os.path.getsize(cert_path) == 0:
                    return False, {}, "Error: El archivo de certificado no se creó correctamente"
                if not os.path.exists(key_path) or os.path.getsize(key_path) == 0:
                    return False, {}, "Error: El archivo de clave privada no se creó correctamente"
                
                # URLs correctas para WSAA según el ambiente (verificadas con AFIP)
                # IMPORTANTE: pyafipws agrega automáticamente ?wsdl al final, así que NO debemos incluirlo
                # Testing/Homologación: https://wsaahomo.afip.gov.ar/ws/services/LoginCms
                # Producción: https://wsaa.afip.gov.ar/ws/services/LoginCms
                wsaa_url = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms" if modo == 'testing' \
                          else "https://wsaa.afip.gov.ar/ws/services/LoginCms"
                
                logger.info(f"=== Iniciando autenticación AFIP ===")
                logger.info(f"Modo: {modo}")
                logger.info(f"CUIT: {self.tienda.cuit}")
                logger.info(f"Punto de venta: {self.tienda.punto_venta}")
                logger.info(f"URL WSAA: {wsaa_url}")
                logger.info(f"Certificado: {cert_path}")
                logger.info(f"Clave privada: {key_path}")
                
                # Limpiar cache de pyafipws para evitar usar archivos corruptos
                # pyafipws puede cachear respuestas incorrectas (HTML en lugar de XML)
                # Esto soluciona el error "junk after document element"
                try:
                    import pyafipws
                    import hashlib
                    import site
                    
                    # Buscar directorio de pyafipws
                    pyafipws_path = os.path.dirname(pyafipws.__file__)
                    cache_dir = os.path.join(pyafipws_path, 'cache')
                    
                    if os.path.exists(cache_dir):
                        # Calcular hash de la URL para encontrar el archivo de cache específico
                        cache_hash = hashlib.md5(wsaa_url.encode()).hexdigest()
                        cache_file = os.path.join(cache_dir, f"{cache_hash}.xml")
                        
                        if os.path.exists(cache_file):
                            logger.warning(f"⚠️ Eliminando archivo de cache posiblemente corrupto: {cache_file}")
                            try:
                                # Verificar si el archivo contiene HTML en lugar de XML
                                with open(cache_file, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read(200)  # Leer primeros 200 caracteres
                                    if '<h1>' in content or '<html' in content.lower():
                                        logger.warning(f"⚠️ El cache contiene HTML, eliminando...")
                                        os.remove(cache_file)
                                        logger.info(f"✅ Cache corrupto eliminado")
                                    else:
                                        logger.info(f"✅ Cache parece válido, no se elimina")
                            except Exception as e:
                                logger.warning(f"⚠️ No se pudo verificar/eliminar cache: {e}")
                        
                        # También eliminar todos los caches si hay muchos archivos (pueden estar corruptos)
                        cache_files = [f for f in os.listdir(cache_dir) if f.endswith('.xml')]
                        if len(cache_files) > 10:
                            logger.warning(f"⚠️ Muchos archivos de cache ({len(cache_files)}), limpiando todos...")
                            for cf in cache_files:
                                try:
                                    os.remove(os.path.join(cache_dir, cf))
                                except:
                                    pass
                            logger.info(f"✅ Todos los caches limpiados")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo limpiar cache (continuando de todas formas): {e}")
                
                # Usar cache compartido para pyafipws
                # Estrategia: Verificar si hay un TA válido en el cache ANTES de intentar autenticarnos
                # Si AFIP dice "alreadyAuthenticated", significa que ya hay un TA válido, así que debemos usarlo del cache
                import tempfile
                import hashlib
                import xml.etree.ElementTree as ET
                import time
                
                # Crear un cache compartido basado en el CUIT (permite reutilizar TAs válidos)
                cuit_hash = hashlib.md5(self.tienda.cuit.encode()).hexdigest()[:8]
                shared_cache = os.path.join(tempfile.gettempdir(), f"pyafipws_cache_shared_{cuit_hash}")
                os.makedirs(shared_cache, exist_ok=True)
                
                logger.info(f"Usando cache compartido: {shared_cache}")
                
                # Función auxiliar para verificar si un TA del cache es válido
                def verificar_ta_cache(cache_dir, wsaa_url_hash):
                    """Verifica si hay un TA válido en el cache"""
                    try:
                        import hashlib
                        
                        # pyafipws guarda los TAs con formato "TA-{hash}.xml"
                        # Buscar archivos que empiecen con "TA-" y terminen en ".xml"
                        ta_files = []
                        
                        if os.path.exists(cache_dir):
                            try:
                                all_files = os.listdir(cache_dir)
                                # Filtrar solo archivos de TA (empiezan con "TA-")
                                ta_files = [f for f in all_files if f.startswith('TA-') and f.endswith('.xml')]
                                
                                if ta_files:
                                    # Ordenar por fecha de modificación (más reciente primero)
                                    ta_files.sort(key=lambda f: os.path.getmtime(os.path.join(cache_dir, f)), reverse=True)
                                    logger.debug(f"Archivos TA encontrados en cache: {ta_files}")
                                else:
                                    logger.debug(f"No se encontraron archivos TA-*.xml en el cache")
                            except Exception as e:
                                logger.debug(f"No se pudieron listar archivos del cache: {e}")
                        
                        # Intentar con el archivo más reciente
                        for ta_file in ta_files:
                            cache_file = os.path.join(cache_dir, ta_file)
                            logger.debug(f"Verificando archivo TA del cache: {cache_file}")
                            
                            try:
                                # Leer el contenido del archivo
                                with open(cache_file, 'r', encoding='utf-8') as f:
                                    ta_content = f.read()
                                
                                if not ta_content or len(ta_content.strip()) == 0:
                                    logger.debug(f"⚠️ Archivo de cache está vacío: {ta_file}")
                                    continue
                                
                                # Verificar que el archivo sea realmente un TA (no un WSDL)
                                # Los TAs contienen <loginTicketResponse> o <credentials>
                                # Los WSDLs contienen <wsdl:definitions>
                                if '<wsdl:definitions' in ta_content or 'targetNamespace="https://wsaahomo' in ta_content or '<wsdl:' in ta_content:
                                    logger.debug(f"⚠️ El archivo {ta_file} es un WSDL, no un TA. Saltando...")
                                    continue
                                
                                if not ('<loginTicketResponse' in ta_content or '<credentials' in ta_content or 'loginTicketResponse' in ta_content):
                                    logger.debug(f"⚠️ El archivo {ta_file} no parece ser un TA válido (no contiene loginTicketResponse ni credentials). Saltando...")
                                    continue
                                
                                logger.info(f"✅ Archivo TA válido encontrado: {cache_file} ({len(ta_content)} caracteres)")
                                
                                # Parsear XML para verificar fecha de expiración
                                try:
                                    root = ET.fromstring(ta_content)
                                    # Buscar fecha de expiración en diferentes namespaces posibles
                                    expiration = None
                                    namespaces = [
                                        'http://wsaa.view.sua.dvadac.desein.afip.gov',
                                        '{http://wsaa.view.sua.dvadac.desein.afip.gov}',
                                    ]
                                    
                                    for ns in namespaces:
                                        expiration = root.find(f'.//{ns}expirationTime')
                                        if expiration is not None:
                                            break
                                    
                                    # Si no se encuentra con namespace, buscar sin namespace
                                    if expiration is None:
                                        expiration = root.find('.//expirationTime')
                                    
                                    if expiration is not None and expiration.text:
                                        from datetime import datetime
                                        exp_time_str = expiration.text
                                        logger.info(f"Fecha de expiración encontrada en TA: {exp_time_str}")
                                        
                                        try:
                                            # Intentar parsear la fecha (puede venir en diferentes formatos)
                                            exp_time_str_clean = exp_time_str.replace('Z', '+00:00')
                                            exp_time = datetime.fromisoformat(exp_time_str_clean)
                                            
                                            # Obtener hora actual con timezone si el TA tiene uno
                                            now = datetime.now(exp_time.tzinfo) if exp_time.tzinfo else datetime.now()
                                            
                                            # Verificar si el TA aún es válido (con margen de 10 minutos para estar seguros)
                                            time_diff = (exp_time - now).total_seconds()
                                            
                                            if time_diff > 600:  # Más de 10 minutos restantes
                                                logger.info(f"✅ TA válido encontrado en cache (expira en {time_diff/60:.1f} minutos)")
                                                return ta_content
                                            else:
                                                logger.warning(f"⚠️ TA en cache expirará pronto o ya expiró (restan {time_diff/60:.1f} minutos)")
                                                # De todas formas devolverlo, pyafipws puede manejarlo
                                                return ta_content
                                        except Exception as e:
                                            logger.warning(f"⚠️ No se pudo parsear fecha de expiración '{exp_time_str}': {e}")
                                            # Si no se puede parsear, asumir que es válido (pyafipws lo manejará)
                                            logger.info(f"✅ Usando TA del cache (no se pudo verificar expiración, pero existe)")
                                            return ta_content
                                    else:
                                        logger.info(f"✅ Usando TA del cache (no se encontró fecha de expiración, pero el archivo existe)")
                                        return ta_content
                                except ET.ParseError as e:
                                    logger.warning(f"⚠️ Error al parsear XML del TA del cache: {e}")
                                    # Aun así, devolver el contenido si parece ser XML válido
                                    if '<?xml' in ta_content or '<' in ta_content:
                                        logger.info(f"✅ Usando TA del cache (XML con formato inesperado pero parece válido)")
                                        return ta_content
                                    continue
                                except Exception as e:
                                    logger.warning(f"⚠️ Error al procesar TA del cache: {e}")
                                    # Si parece ser XML, devolverlo de todas formas
                                    if '<?xml' in ta_content or '<' in ta_content:
                                        logger.info(f"✅ Usando TA del cache (error al procesar pero parece válido)")
                                        return ta_content
                                    continue
                            except Exception as e:
                                logger.debug(f"⚠️ Error al leer archivo TA {ta_file}: {e}")
                                continue
                        
                        logger.debug(f"⚠️ No se encontraron archivos TA válidos en el cache")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al verificar cache: {e}")
                    
                    return None
                
                # Verificar si hay un TA válido en el cache ANTES de intentar autenticarnos
                ta_cache = verificar_ta_cache(shared_cache, wsaa_url)
                
                # Intentar autenticación
                ta = None
                max_intentos = 3
                
                for intento in range(max_intentos):
                    try:
                        ta = wsaa.Autenticar(
                            "wsfe",  # Servicio: Web Service de Facturación Electrónica
                            cert_path,
                            key_path,
                            cache=shared_cache,  # Cache compartido por CUIT
                            wsdl=wsaa_url
                        )
                        
                        if ta:
                            logger.info(f"✅ Autenticación exitosa (intento {intento + 1})")
                            break
                        else:
                            error_msg = wsaa.Excepcion or "Error desconocido al autenticar"
                            raise Exception(error_msg)
                            
                    except Exception as auth_error:
                        error_str = str(auth_error)
                        
                        # Si es "alreadyAuthenticated", significa que ya hay un TA válido activo
                        # En este caso, intentar usar el TA del cache directamente
                        if 'alreadyAuthenticated' in error_str or 'ya posee un TA valido' in error_str.lower():
                            logger.warning(f"⚠️ Error 'alreadyAuthenticated' en intento {intento + 1}. Intentando usar TA del cache...")
                            
                            # Verificar nuevamente el cache (puede haberse actualizado o haber múltiples archivos)
                            ta_cache = verificar_ta_cache(shared_cache, wsaa_url)
                            
                            if ta_cache:
                                logger.info(f"✅ TA encontrado en cache. Usando directamente (AFIP indica que ya hay un TA válido activo)")
                                # El TA del cache es XML, pyafipws lo espera en ese formato
                                # Limpiar el TA si tiene múltiples documentos (como antes)
                                if '<?xml' in ta_cache:
                                    # Extraer solo el primer documento XML si hay múltiples
                                    parts = ta_cache.split('<?xml')
                                    if len(parts) > 2:
                                        ta_cache_clean = '<?xml' + parts[1]
                                        logger.info(f"✅ Limpiado TA del cache (eliminados {len(parts)-2} documentos XML adicionales)")
                                    elif len(parts) == 2:
                                        ta_cache_clean = '<?xml' + parts[1]
                                    else:
                                        ta_cache_clean = ta_cache
                                else:
                                    ta_cache_clean = ta_cache
                                
                                ta = ta_cache_clean
                                logger.info(f"✅ TA del cache configurado, continuando con la facturación...")
                                break
                            else:
                                logger.warning(f"⚠️ No se encontró TA válido en el cache. Esto puede significar que el TA fue eliminado o nunca se guardó correctamente.")
                                logger.info(f"Listando archivos en cache: {shared_cache}")
                                try:
                                    if os.path.exists(shared_cache):
                                        files = os.listdir(shared_cache)
                                        logger.info(f"Archivos en cache: {files}")
                                except Exception as e:
                                    logger.warning(f"No se pudieron listar archivos del cache: {e}")
                            
                            # Si no hay TA en cache o el siguiente intento, esperar un poco
                            if intento < max_intentos - 1:
                                wait_time = (intento + 1) * 2  # 2, 4, 6 segundos
                                logger.info(f"Esperando {wait_time} segundos antes del siguiente intento...")
                                time.sleep(wait_time)
                                
                                # Verificar nuevamente el cache antes del siguiente intento
                                ta_cache = verificar_ta_cache(shared_cache, wsaa_url)
                                
                                # Crear nueva instancia de WSAA para el siguiente intento
                                wsaa = WSAA()
                            else:
                                # Último intento falló
                                logger.error(f"❌ Todos los intentos fallaron con 'alreadyAuthenticated'")
                                error_msg = f"Error al autenticar: {error_str}"
                                error_msg += " | SOLUCIÓN: AFIP indica que ya hay un Ticket de Acceso (TA) válido activo para este CUIT. Esto puede ocurrir con múltiples solicitudes simultáneas. El sistema intentará usar el TA del cache automáticamente. Si el error persiste, espera 30 segundos y vuelve a intentar. Los TA de AFIP duran 12 horas."
                                return False, {}, f"Error temporal de autenticación con AFIP: {error_msg}"
                        else:
                            # Otro tipo de error en el primer intento, propagarlo
                            if intento == 0:
                                raise
                            # Si es un reintento y hay otro error, también propagarlo
                            raise
                
                if not ta:
                    # Si después de todos los intentos no tenemos un TA, retornar error
                    error_msg = wsaa.Excepcion if hasattr(wsaa, 'Excepcion') and wsaa.Excepcion else "Error desconocido al autenticar"
                    logger.error(f"❌ Error al autenticar con AFIP después de {max_intentos} intentos: {error_msg}")
                    logger.error(f"URL utilizada: {wsaa_url}")
                    logger.error(f"Modo: {modo}")
                    
                    # Mensajes de ayuda específicos
                    if hasattr(wsaa, 'Errores') and wsaa.Errores:
                        logger.error(f"Errores detallados: {wsaa.Errores}")
                    
                    # Mensajes de ayuda detallados para errores comunes
                    if 'cms.cert.untrusted' in str(error_msg):
                        error_msg += " | SOLUCIÓN: Los certificados no son válidos para homologación. Debes obtener certificados de homologación desde https://www.afip.gob.ar/fe/. Los certificados de producción NO funcionan en modo testing. Verifica que los certificados sean específicos de homologación y estén emitidos por una AC de confianza de AFIP."
                    elif 'cms.sign.invalid' in str(error_msg):
                        error_msg += " | SOLUCIÓN: El certificado y la clave privada no coinciden. Asegúrate de usar el certificado (.crt) y la clave privada (.key) que pertenecen al mismo par generado en AFIP."
                    elif 'coe.notAuthorized' in str(error_msg) or 'notAuthorized' in str(error_msg):
                        error_msg += " | SOLUCIÓN: El CUIT o punto de venta no está habilitado en AFIP. Ve a https://www.afip.gob.ar/fe/ y verifica que el servicio de facturación electrónica esté ACTIVO para este CUIT y punto de venta. En modo testing, asegúrate de usar un CUIT de prueba válido."
                    elif 'alreadyAuthenticated' in str(error_msg) or 'ya posee un TA valido' in str(error_msg).lower():
                        error_msg += " | SOLUCIÓN: Este error ocurre cuando hay múltiples solicitudes simultáneas o un TA reciente aún está activo. El sistema intenta usar el TA del cache automáticamente. Si el error persiste, espera 30 segundos y vuelve a intentar."
                    
                    return False, {}, f"Error al autenticar con AFIP: {error_msg}"
                
                logger.info(f"✅ Autenticación exitosa. Ticket de acceso obtenido.")
                
                # Verificar que el ticket de acceso sea válido
                if not isinstance(ta, str) or len(ta) < 10:
                    error_msg = f"El ticket de acceso parece inválido: {type(ta)}"
                    logger.error(f"❌ {error_msg}")
                    return False, {}, f"Error: {error_msg}"
                
                # Limpiar el ticket de acceso - puede venir con múltiples documentos XML
                # pyafipws a veces devuelve el ticket con contenido extra
                ta_clean = ta.strip()
                
                # Si el ticket contiene múltiples documentos XML, tomar solo el primero
                # Buscar el primer </loginTicketResponse> o </ticket> para cortar allí
                ta_match = re.search(r'(<\?xml.*?</loginTicketResponse>)', ta_clean, re.DOTALL)
                if ta_match:
                    ta_clean = ta_match.group(1)
                else:
                    # Intentar con otro patrón común
                    ta_match = re.search(r'(<\?xml.*?</ticket>)', ta_clean, re.DOTALL)
                    if ta_match:
                        ta_clean = ta_match.group(1)
                
                logger.info(f"Ticket de acceso original (longitud): {len(ta)}")
                logger.info(f"Ticket de acceso limpiado (longitud): {len(ta_clean)}")
                logger.info(f"Ticket de acceso (primeros 200 caracteres): {ta_clean[:200]}...")
                
                # Usar el ticket limpiado
                ta = ta_clean
                
                # Configurar WSFEv1 (Web Service de Facturación Electrónica)
                wsfev1 = WSFEv1()
                
                wsfev1.LanzarExcepciones = True
                
                # URLs correctas para WSFEv1 según el ambiente
                # IMPORTANTE: pyafipws agrega automáticamente ?wsdl al final, así que NO debemos incluirlo
                # Testing: https://wswhomo.afip.gov.ar/wsfev1/service.asmx
                # Producción: https://servicios1.afip.gov.ar/wsfev1/service.asmx
                wsfev1_url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx" if modo == 'testing' \
                            else "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
                
                logger.info(f"Conectando a WSFEv1 en modo {modo}: {wsfev1_url}")
                
                try:
                    wsfev1.Conectar(
                        cache="",
                        wsdl=wsfev1_url
                    )
                except Exception as e:
                    error_msg = f"Error al conectar con WSFEv1: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    logger.error(f"URL utilizada: {wsfev1_url}")
                    return False, {}, error_msg
                
                try:
                    logger.info(f"⚠️ Estableciendo ticket de acceso en WSFEv1...")
                    logger.info(f"Longitud del ticket a establecer: {len(ta)}")
                    # Verificar que el ticket empiece con <?xml
                    if not ta.strip().startswith('<?xml'):
                        logger.warning(f"⚠️ El ticket no empieza con <?xml. Añadiendo declaración XML si es necesario...")
                        if not ta.strip().startswith('<'):
                            error_msg = "El ticket de acceso no parece ser un XML válido"
                            logger.error(f"❌ {error_msg}")
                            logger.error(f"Primeros 100 caracteres del ticket: {ta[:100]}")
                            return False, {}, error_msg
                    
                    wsfev1.SetTicketAcceso(ta)
                    logger.info(f"✅ Ticket de acceso establecido correctamente")
                except Exception as e:
                    error_msg = f"Error al establecer ticket de acceso: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    logger.error(f"Tipo de ticket: {type(ta)}")
                    logger.error(f"Longitud del ticket: {len(str(ta))}")
                    logger.error(f"Primeros 500 caracteres del ticket: {ta[:500]}")
                    if 'junk after document element' in str(e).lower():
                        error_msg += " (Problema al parsear XML del ticket de acceso. El ticket puede tener múltiples documentos XML o formato incorrecto)"
                        error_msg += " | SUGERENCIA: Verifica que los certificados sean válidos y del ambiente correcto (testing vs producción)"
                    return False, {}, error_msg
                wsfev1.Cuit = self.tienda.cuit.replace('-', '')
                logger.info(f"✅ WSFEv1 configurado correctamente. CUIT: {wsfev1.Cuit}")
                
                # Determinar tipo de comprobante
                tipo_comprobante = self._determinar_tipo_comprobante(cliente_data)
                logger.info(f"Tipo de comprobante: {tipo_comprobante}")
                
                # Obtener último número de comprobante
                punto_venta = self.tienda.punto_venta
                logger.info(f"Consultando último número autorizado para tipo {tipo_comprobante}, punto venta {punto_venta}...")
                
                try:
                    ultimo_numero_result = wsfev1.CompUltimoAutorizado(tipo_comprobante, punto_venta)
                    
                    # Convertir a entero si es necesario
                    if ultimo_numero_result is None:
                        ultimo_numero = 0
                        logger.warning(f"⚠️ No se pudo obtener último número, usando 0 como base")
                    elif isinstance(ultimo_numero_result, str):
                        try:
                            ultimo_numero = int(ultimo_numero_result)
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ No se pudo convertir último número '{ultimo_numero_result}' a entero, usando 0")
                            ultimo_numero = 0
                    elif isinstance(ultimo_numero_result, (int, float)):
                        ultimo_numero = int(ultimo_numero_result)
                    else:
                        logger.warning(f"⚠️ Tipo inesperado para último número: {type(ultimo_numero_result)}, usando 0")
                        ultimo_numero = 0
                    
                    nuevo_numero = ultimo_numero + 1
                    logger.info(f"✅ Último número autorizado: {ultimo_numero}, Nuevo número: {nuevo_numero}")
                except Exception as e:
                    error_msg = f"Error al obtener último número autorizado: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    logger.error(f"Tipo de error: {type(e).__name__}")
                    if 'junk after document element' in str(e).lower():
                        error_msg += " (Problema al parsear XML de respuesta. Verifica certificados y configuración)"
                    elif 'concatenate' in str(e).lower() or 'str' in str(e).lower():
                        error_msg += " (Error de tipo al procesar respuesta de AFIP. Esto puede indicar un problema con el formato de respuesta)"
                    return False, {}, error_msg
                
                # Preparar datos de la factura
                fecha_servicio = datetime.now()
                fecha_vencimiento = fecha_servicio + timedelta(days=10)  # Por defecto 10 días
                
                # IMPORTANTE: Los precios de los productos ya tienen IVA incluido (21%)
                # El descuento/recargo se aplica sobre el TOTAL CON IVA, no sobre el subtotal sin IVA
                # El total de la venta ya tiene IVA incluido y descuentos/recargos aplicados
                total_con_iva = venta.total
                
                # Calcular subtotal sin IVA: total_con_iva / 1.21
                # IMPORTANTE: Redondear a 2 decimales porque AFIP solo acepta 2 decimales
                subtotal = (total_con_iva / Decimal('1.21')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                # Calcular IVA: total_con_iva - subtotal
                # IMPORTANTE: Redondear a 2 decimales porque AFIP solo acepta 2 decimales
                impuesto_iva = (total_con_iva - subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                total = total_con_iva  # El total ya es correcto (incluye IVA y descuentos/recargos aplicados)
                
                logger.info(f"Cálculos de IVA (redondeados a 2 decimales): Subtotal={subtotal}, IVA={impuesto_iva}, Total={total}")
                
                # Mapear condición de IVA a código AFIP
                # Códigos AFIP: 1=RI, 4=EX, 5=CF, 6=MT, 0=NR
                condicion_iva = cliente_data.get('cliente_condicion_iva', 'CF')
                condicion_iva_codigo_map = {
                    'RI': 1,  # Responsable Inscripto
                    'EX': 4,  # Exento
                    'CF': 5,  # Consumidor Final
                    'MT': 6,  # Monotributo
                    'NR': 0,  # No Responsable
                }
                condicion_iva_codigo = condicion_iva_codigo_map.get(condicion_iva, 5)  # Por defecto CF
                
                logger.info(f"Condición IVA del cliente: {condicion_iva} (código AFIP: {condicion_iva_codigo})")
                
                # Crear comprobante
                # NOTA: En pyafipws WSFEv1, para facturas simples no se requieren items detallados
                # Los totales son suficientes para AFIP. Si se necesitan items detallados,
                # se pueden agregar usando el método correcto después de investigar la API.
                logger.info(f"Creando factura con {venta.detalles.count()} items (detalles almacenados localmente)")
                
                # Crear comprobante
                # El parámetro correcto para condición de IVA del receptor es 'condicion_iva_receptor_id'
                # NOTA: Para concepto=1 (Productos), NO se deben enviar fecha_serv_desde, fecha_serv_hasta ni fecha_venc_pago
                # Estas fechas solo se usan para concepto=2 (Servicios) o concepto=3 (Productos y Servicios)
                concepto = 1  # Productos
                logger.info(f"Creando factura con {venta.detalles.count()} items (detalles almacenados localmente)")
                logger.info(f"Condición IVA del receptor: {condicion_iva} (código AFIP: {condicion_iva_codigo})")
                
                # IMPORTANTE: Redondear todos los valores a 2 decimales porque AFIP solo acepta 2 decimales
                # Los valores ya están redondeados en subtotal e impuesto_iva, pero aseguramos que total también lo esté
                imp_total_redondeado = float(total.quantize(Decimal('0.01')))
                imp_neto_redondeado = float(subtotal.quantize(Decimal('0.01')))
                imp_iva_redondeado = float(impuesto_iva.quantize(Decimal('0.01')))
                
                logger.info(f"Valores redondeados a 2 decimales para AFIP: imp_total={imp_total_redondeado}, imp_neto={imp_neto_redondeado}, imp_iva={imp_iva_redondeado}")
                
                # Preparar parámetros base de la factura
                factura_params = {
                    'concepto': concepto,
                    'tipo_doc': cliente_data.get('tipo_documento', '99'),  # 99 = Sin identificar
                    'nro_doc': cliente_data.get('cuit', '').replace('-', '') or '0',
                    'tipo_cbte': tipo_comprobante,
                    'punto_vta': punto_venta,
                    'cbt_desde': nuevo_numero,
                    'cbt_hasta': nuevo_numero,
                    'imp_total': imp_total_redondeado,
                    'imp_tot_conc': 0.0,
                    'imp_neto': imp_neto_redondeado,
                    'imp_iva': imp_iva_redondeado,
                    'imp_trib': 0.0,
                    'imp_op_ex': 0.0,
                    'fecha_cbte': fecha_servicio.strftime('%Y%m%d'),
                    'moneda_id': 'PES',
                    'moneda_ctz': 1.0,
                    'condicion_iva_receptor_id': condicion_iva_codigo,  # Condición frente al IVA del receptor (OBLIGATORIO)
                }
                
                # Solo agregar fechas de servicio y vencimiento si concepto es 2 o 3
                # Para concepto=1 (Productos), AFIP rechaza estas fechas
                if concepto in [2, 3]:
                    factura_params['fecha_venc_pago'] = fecha_vencimiento.strftime('%Y%m%d')
                    factura_params['fecha_serv_desde'] = fecha_servicio.strftime('%Y%m%d')
                    factura_params['fecha_serv_hasta'] = fecha_servicio.strftime('%Y%m%d')
                    logger.info(f"Concepto {concepto}: Agregando fechas de servicio y vencimiento")
                else:
                    logger.info(f"Concepto {concepto}: NO se agregan fechas de servicio ni vencimiento (solo para concepto 2 o 3)")
                
                # Crear la factura
                wsfev1.CrearFactura(**factura_params)
                
                # Si hay importe neto mayor a 0, agregar el array de IVA (OBLIGATORIO)
                if float(subtotal) > 0 and float(impuesto_iva) > 0:
                    # Los valores ya están redondeados, pero aseguramos el redondeo para el log
                    subtotal_redondeado_log = subtotal.quantize(Decimal('0.01'))
                    iva_redondeado_log = impuesto_iva.quantize(Decimal('0.01'))
                    logger.info(f"Agregando información de IVA (ImpNeto: {subtotal_redondeado_log}, ImpIVA: {iva_redondeado_log})")
                    
                    # Obtener tipos de IVA válidos desde AFIP para usar el código correcto
                    try:
                        tipos_iva = wsfev1.ParamGetTiposIva()
                        logger.debug(f"Tipos de IVA disponibles: {tipos_iva}")
                        logger.debug(f"Tipo de datos: {type(tipos_iva)}")
                        
                        # Buscar el código para IVA 21% (generalmente es 5 o similar)
                        # Los tipos de IVA pueden venir como lista de tuplas o como diccionario
                        iva_id = 5  # Por defecto 21% (código más común en Argentina)
                        
                        if tipos_iva:
                            # Manejar diferentes formatos de respuesta
                            if isinstance(tipos_iva, dict):
                                # Si viene como diccionario {id: descripcion}
                                for tipo_id, tipo_desc in tipos_iva.items():
                                    if '21' in str(tipo_desc) or '21%' in str(tipo_desc):
                                        iva_id = tipo_id
                                        logger.info(f"✅ Código de IVA 21% encontrado: {iva_id} ({tipo_desc})")
                                        break
                            elif isinstance(tipos_iva, (list, tuple)):
                                # Si viene como lista/tupla de tuplas [(id, descripcion), ...]
                                for item in tipos_iva:
                                    # Manejar si es tupla de 2 elementos o lista
                                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                                        tipo_id, tipo_desc = item[0], item[1]
                                        if '21' in str(tipo_desc) or '21%' in str(tipo_desc):
                                            iva_id = tipo_id
                                            logger.info(f"✅ Código de IVA 21% encontrado: {iva_id} ({tipo_desc})")
                                            break
                                    # Si es solo el ID (número)
                                    elif isinstance(item, (int, str)) and str(item) == '5':
                                        iva_id = int(item)
                                        logger.info(f"✅ Código de IVA encontrado: {iva_id}")
                                        break
                            
                            # Si no se encontró específicamente el 21%, buscar el código 5 (común para 21%)
                            if iva_id == 5:
                                logger.info(f"✅ Usando código de IVA 5 (21% - estándar en Argentina)")
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudieron obtener tipos de IVA desde AFIP: {e}. Usando código por defecto 5 (21%)")
                        iva_id = 5  # Código por defecto para IVA 21%
                    
                    # Agregar IVA usando los parámetros correctos: iva_id, base_imp, importe
                    # IMPORTANTE: Redondear a 2 decimales porque AFIP solo acepta 2 decimales
                    base_imp_redondeada = float(subtotal.quantize(Decimal('0.01')))
                    importe_iva_redondeado = float(impuesto_iva.quantize(Decimal('0.01')))
                    
                    wsfev1.AgregarIva(
                        iva_id=iva_id,  # Código de alícuota de IVA (5 = 21%)
                        base_imp=base_imp_redondeada,  # Base imponible (redondeada a 2 decimales)
                        importe=importe_iva_redondeado  # Monto del IVA (redondeado a 2 decimales)
                    )
                    logger.info(f"✅ Información de IVA agregada correctamente (código: {iva_id})")
                
                # Autorizar comprobante
                logger.info(f"⚠️ Solicitando autorización CAE...")
                try:
                    wsfev1.CAESolicitar()
                except Exception as e:
                    error_msg = f"Error al solicitar CAE: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    if 'junk after document element' in str(e).lower():
                        error_msg += " (Problema al parsear XML de respuesta. Esto puede indicar certificados inválidos o formato incorrecto)"
                    if hasattr(wsfev1, 'Excepcion') and wsfev1.Excepcion:
                        error_msg += f" | Excepción AFIP: {wsfev1.Excepcion}"
                    if hasattr(wsfev1, 'Errores') and wsfev1.Errores:
                        error_msg += f" | Errores: {wsfev1.Errores}"
                    return False, {}, error_msg
                
                logger.info(f"Resultado de autorización: {wsfev1.Resultado}")
                
                if wsfev1.Resultado == 'A':  # Autorizado
                    # Obtener CAE y fecha de vencimiento
                    cae = str(wsfev1.CAE)
                    fecha_venc_cae = datetime.strptime(wsfev1.Vencimiento, '%Y%m%d').date()
                    
                    # Convertir tipo_comprobante (int) a letra para guardar en la base de datos
                    tipo_comprobante_letra = 'B'  # Por defecto
                    if tipo_comprobante == 1:
                        tipo_comprobante_letra = 'A'  # Factura A
                    elif tipo_comprobante == 6:
                        tipo_comprobante_letra = 'B'  # Factura B
                    elif tipo_comprobante == 11:
                        tipo_comprobante_letra = 'C'  # Factura C
                    
                    datos_factura = {
                        'tipo_comprobante': tipo_comprobante_letra,  # Tipo de comprobante (A, B, o C)
                        'numero_comprobante': nuevo_numero,
                        'punto_venta': punto_venta,
                        'cae': cae,
                        'fecha_vencimiento_cae': fecha_venc_cae,
                        'numero_comprobante_afip': wsfev1.CbteNro,
                        'subtotal': subtotal,
                        'impuesto_iva': impuesto_iva,
                        'total': total,
                        'respuesta_bruta': json.dumps({
                            'resultado': wsfev1.Resultado,
                            'cae': cae,
                            'observaciones': wsfev1.Obs or [],
                        }),
                    }
                    
                    return True, datos_factura, None
                else:
                    # Obtener mensaje de error más detallado
                    error_details = []
                    if hasattr(wsfev1, 'Obs') and wsfev1.Obs:
                        error_details.append(f"Observaciones: {wsfev1.Obs}")
                    if hasattr(wsfev1, 'Excepcion') and wsfev1.Excepcion:
                        error_details.append(f"Excepción: {wsfev1.Excepcion}")
                    if hasattr(wsfev1, 'Errores') and wsfev1.Errores:
                        error_details.append(f"Errores: {wsfev1.Errores}")
                    
                    error_msg = f"AFIP rechazó la factura"
                    if error_details:
                        error_msg += f": {' | '.join(str(d) for d in error_details)}"
                    
                    # Mensajes de ayuda para errores comunes
                    excepcion_str = str(wsfev1.Excepcion or '')
                    if 'cms.cert.untrusted' in excepcion_str:
                        error_msg += " (Solución: Usa certificados válidos de homologación de AFIP para modo testing)"
                    elif 'cms.sign.invalid' in excepcion_str:
                        error_msg += " (Solución: Verifica que el certificado y la clave privada coincidan y sean válidos)"
                    elif 'coe.notAuthorized' in excepcion_str or 'notAuthorized' in excepcion_str:
                        error_msg += " (Solución: El CUIT o punto de venta no está habilitado en AFIP. Verifica en AFIP que el servicio de facturación electrónica esté activado para este CUIT y punto de venta)"
                    
                    logger.error(f"Error al emitir factura AFIP: {error_msg}")
                    return False, {}, error_msg
                    
            finally:
                # Limpiar archivos temporales
                try:
                    os.unlink(cert_path)
                    os.unlink(key_path)
                except:
                    pass
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error al emitir factura AFIP: {error_msg}", exc_info=True)
            
            # Mensajes de ayuda específicos para errores comunes
            if 'junk after document element' in error_msg.lower():
                error_msg += " | Problema al parsear XML. Posibles causas: certificados inválidos, formato incorrecto, o respuesta malformada del servidor AFIP"
            elif 'cms.cert.untrusted' in error_msg:
                error_msg += " | SOLUCIÓN: Los certificados no son válidos para homologación. Debes obtener certificados de homologación desde https://www.afip.gob.ar/fe/. Los certificados de producción NO funcionan en modo testing."
            elif 'cms.sign.invalid' in error_msg:
                error_msg += " | SOLUCIÓN: El certificado y la clave privada no coinciden. Asegúrate de usar el certificado (.crt) y la clave privada (.key) que pertenecen al mismo par generado en AFIP."
            elif 'coe.notAuthorized' in error_msg or 'notAuthorized' in error_msg:
                error_msg += " | SOLUCIÓN: El CUIT o punto de venta no está habilitado en AFIP. Ve a https://www.afip.gob.ar/fe/ y verifica que el servicio esté ACTIVO."
            
            return False, {}, f"Error al emitir factura: {error_msg}"
    
    def _emitir_arca(self, venta, cliente_data: Dict) -> Tuple[bool, Dict, Optional[str]]:
        """Emitir factura a través de ARCA"""
        if not REQUESTS_AVAILABLE:
            return False, {}, "requests no está instalado. Instala con: pip install requests"
        
        try:
            if not self.tienda.api_key_arca:
                return False, {}, "API Key de ARCA no configurada"
            
            if not self.tienda.url_arca:
                return False, {}, "URL de ARCA no configurada"
            
            # Preparar datos para ARCA
            tipo_comprobante = self._determinar_tipo_comprobante(cliente_data)
            
            # Calcular IVA
            iva_porcentaje = Decimal('21.00')
            subtotal = venta.total
            impuesto_iva = subtotal * (iva_porcentaje / 100)
            total = subtotal + impuesto_iva
            
            # Preparar items
            items = []
            for detalle in venta.detalles.all():
                if not detalle.anulado_individualmente:
                    items.append({
                        'codigo': detalle.producto.codigo_barras if detalle.producto and detalle.producto.codigo_barras else '',
                        'descripcion': detalle.producto.nombre if detalle.producto else 'Producto',
                        'cantidad': float(detalle.cantidad),
                        'precio_unitario': float(detalle.precio_unitario),
                        'subtotal': float(detalle.subtotal),
                    })
            
            # Datos para enviar a ARCA
            payload = {
                'cuit': self.tienda.cuit.replace('-', ''),
                'punto_venta': self.tienda.punto_venta,
                'tipo_comprobante': tipo_comprobante,
                'cliente': {
                    'nombre': cliente_data.get('nombre', 'Consumidor Final'),
                    'cuit': cliente_data.get('cuit', '').replace('-', '') if cliente_data.get('cuit') else None,
                    'domicilio': cliente_data.get('domicilio', ''),
                    'tipo_documento': cliente_data.get('tipo_documento', '99'),
                },
                'items': items,
                'subtotal': float(subtotal),
                'iva': float(impuesto_iva),
                'total': float(total),
            }
            
            # Enviar petición a ARCA
            headers = {
                'Authorization': f'Bearer {self.tienda.api_key_arca}',
                'Content-Type': 'application/json',
            }
            
            response = requests.post(
                self.tienda.url_arca,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Convertir tipo_comprobante (int) a letra para guardar en la base de datos
                tipo_comprobante_letra = 'B'  # Por defecto
                if tipo_comprobante == 1:
                    tipo_comprobante_letra = 'A'  # Factura A
                elif tipo_comprobante == 6:
                    tipo_comprobante_letra = 'B'  # Factura B
                elif tipo_comprobante == 11:
                    tipo_comprobante_letra = 'C'  # Factura C
                
                datos_factura = {
                    'numero_comprobante': data.get('numero_comprobante'),
                    'punto_venta': self.tienda.punto_venta,
                    'tipo_comprobante': tipo_comprobante_letra,  # Tipo de comprobante (A, B, o C)
                    'cae': data.get('cae'),
                    'fecha_vencimiento_cae': datetime.fromisoformat(data.get('fecha_vencimiento_cae')).date() if data.get('fecha_vencimiento_cae') else None,
                    'numero_comprobante_afip': data.get('numero_comprobante_afip'),
                    'subtotal': subtotal,
                    'impuesto_iva': impuesto_iva,
                    'total': total,
                    'respuesta_bruta': json.dumps(data),
                }
                
                return True, datos_factura, None
            else:
                error_msg = f"ARCA rechazó la factura: {response.text}"
                return False, {}, error_msg
                
        except Exception as e:
            logger.error(f"Error al emitir factura ARCA: {str(e)}", exc_info=True)
            return False, {}, f"Error al emitir factura: {str(e)}"
    
    def _determinar_tipo_comprobante(self, cliente_data: Dict) -> int:
        """
        Determina el tipo de comprobante según la condición IVA del cliente y del emisor.
        AFIP: 1=Factura A, 6=Factura B, 11=Factura C
        
        Reglas:
        - Factura A: Solo si el EMISOR es Responsable Inscripto Y el cliente es Responsable Inscripto
        - Factura C: Cuando el cliente es Exento (EX)
        - Factura B: En todos los demás casos (CF, MT, NR, o cuando el emisor no puede emitir A)
        """
        condicion_iva_cliente = cliente_data.get('cliente_condicion_iva', 'CF')
        
        # Obtener condición IVA del emisor (tienda)
        # Por defecto, si no está configurado, asumimos Monotributista (más común)
        condicion_iva_emisor = getattr(self.tienda, 'condicion_iva_emisor', 'MT') or 'MT'
        
        logger.info(f"Condición IVA - Emisor: {condicion_iva_emisor}, Cliente: {condicion_iva_cliente}")
        
        # Factura C: Cliente Exento (cualquier emisor puede emitir Factura C)
        if condicion_iva_cliente == 'EX':
            logger.info("Determinado: Factura C (Cliente Exento)")
            return 11  # Factura C
        
        # Factura A: Solo si el EMISOR es Responsable Inscripto Y el cliente es Responsable Inscripto
        if condicion_iva_emisor == 'RI' and condicion_iva_cliente == 'RI':
            logger.info("Determinado: Factura A (Emisor RI y Cliente RI)")
            return 1  # Factura A
        
        # Factura B: Todos los demás casos
        # - Emisor no es RI (no puede emitir A)
        # - Cliente no es RI
        # - Cliente es CF, MT, NR
        logger.info("Determinado: Factura B (caso por defecto)")
        return 6  # Factura B
    
    def obtener_proximo_numero(self) -> Optional[int]:
        """Obtiene el próximo número de comprobante disponible"""
        if self.sistema == 'AFIP':
            return self._obtener_proximo_numero_afip()
        elif self.sistema == 'ARCA':
            return self._obtener_proximo_numero_arca()
        return None
    
    def _obtener_proximo_numero_afip(self) -> Optional[int]:
        """Obtiene el próximo número de comprobante de AFIP"""
        # Similar a _emitir_afip pero solo consulta
        # Implementación simplificada - en producción requeriría autenticación completa
        try:
            from inventario.models import Factura
            ultima_factura = Factura.objects.filter(
                tienda=self.tienda,
                punto_venta=self.tienda.punto_venta
            ).order_by('-numero_comprobante').first()
            
            if ultima_factura and ultima_factura.numero_comprobante:
                return ultima_factura.numero_comprobante + 1
            return 1
        except:
            return None
    
    def _obtener_proximo_numero_arca(self) -> Optional[int]:
        """Obtiene el próximo número de comprobante de ARCA"""
        # Similar a _obtener_proximo_numero_afip
        try:
            from inventario.models import Factura
            ultima_factura = Factura.objects.filter(
                tienda=self.tienda,
                punto_venta=self.tienda.punto_venta
            ).order_by('-numero_comprobante').first()
            
            if ultima_factura and ultima_factura.numero_comprobante:
                return ultima_factura.numero_comprobante + 1
            return 1
        except:
            return None

