"""
Extracción por IA de las líneas de productos de una factura/proforma de compra
(foto o PDF), para la funcionalidad de "Importación IA" del listado de productos.
"""
import logging

from django.conf import settings

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

logger = logging.getLogger(__name__)

MODELO = 'claude-sonnet-5'

MIME_TYPES_SOPORTADOS = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/webp',
}

_TOOL_NAME = 'registrar_lineas_factura'

_TOOL_SCHEMA = {
    'name': _TOOL_NAME,
    'description': (
        'Registra los datos extraídos de una factura o proforma de compra a un '
        'proveedor: sus datos generales y la lista de productos comprados.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'proveedor': {
                'type': ['string', 'null'],
                'description': 'Nombre del proveedor/emisor de la factura, si figura.',
            },
            'numero_documento': {
                'type': ['string', 'null'],
                'description': 'Número de factura/proforma/remito, si figura.',
            },
            'fecha': {
                'type': ['string', 'null'],
                'description': "Fecha del documento tal como figura impresa (texto libre).",
            },
            'lineas': {
                'type': 'array',
                'description': 'Una entrada por cada producto/ítem comprado.',
                'items': {
                    'type': 'object',
                    'properties': {
                        'nombre': {
                            'type': 'string',
                            'description': 'Nombre o descripción del producto tal como figura en la factura.',
                        },
                        'cantidad': {
                            'type': 'integer',
                            'description': 'Cantidad comprada de este ítem.',
                        },
                        'costo_unitario': {
                            'type': 'number',
                            'description': 'Precio unitario de costo (sin el símbolo de moneda).',
                        },
                        'codigo_barras': {
                            'type': ['string', 'null'],
                            'description': 'Código de barras/EAN del producto, solo si figura explícitamente.',
                        },
                        'talle': {
                            'type': ['string', 'null'],
                            'description': 'Talle/tamaño del producto, si se distingue del nombre.',
                        },
                    },
                    'required': ['nombre', 'cantidad', 'costo_unitario'],
                },
            },
        },
        'required': ['lineas'],
    },
}

_PROMPT = (
    "Esta imagen o PDF es una factura o proforma de compra que un comercio le hace "
    "a un proveedor de mercadería. Extraé cada línea de producto comprado (nombre, "
    "cantidad y costo unitario) y los datos generales del documento, usando la "
    "herramienta registrar_lineas_factura. Si un dato no está impreso o no se "
    "entiende con claridad, dejalo en null antes que inventarlo. No incluyas líneas "
    "de totales, subtotales, IVA, flete o descuentos como si fueran productos."
)


class ExtraccionFacturaError(Exception):
    """Error al extraer o interpretar la factura/proforma con IA."""


def extraer_lineas_factura(contenido_bytes: bytes, mime_type: str) -> dict:
    """
    Envía la foto/PDF de una factura de compra a Claude y devuelve un dict:
    {proveedor, numero_documento, fecha, lineas: [{nombre, cantidad,
    costo_unitario, codigo_barras, talle}, ...]}.

    Levanta ExtraccionFacturaError con un mensaje apto para mostrar al usuario
    si falla la llamada, el archivo no es soportado, o el modelo no devuelve
    ninguna línea.
    """
    if not ANTHROPIC_AVAILABLE:
        raise ExtraccionFacturaError(
            "La importación por IA no está disponible en el servidor (falta la librería 'anthropic')."
        )
    if not settings.ANTHROPIC_API_KEY:
        raise ExtraccionFacturaError(
            "La importación por IA no está configurada (falta ANTHROPIC_API_KEY en el servidor)."
        )
    if mime_type not in MIME_TYPES_SOPORTADOS:
        raise ExtraccionFacturaError(
            "Formato de archivo no soportado. Subí una foto (JPG/PNG/WEBP) o un PDF."
        )

    import base64
    contenido_b64 = base64.b64encode(contenido_bytes).decode('ascii')

    if mime_type == 'application/pdf':
        content_block = {
            'type': 'document',
            'source': {'type': 'base64', 'media_type': mime_type, 'data': contenido_b64},
        }
    else:
        content_block = {
            'type': 'image',
            'source': {'type': 'base64', 'media_type': mime_type, 'data': contenido_b64},
        }

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        respuesta = client.messages.create(
            model=MODELO,
            max_tokens=4096,
            tools=[_TOOL_SCHEMA],
            tool_choice={'type': 'tool', 'name': _TOOL_NAME},
            messages=[{
                'role': 'user',
                'content': [content_block, {'type': 'text', 'text': _PROMPT}],
            }],
        )
    except Exception as e:
        logger.error("Importación IA: falló la llamada a Claude: %s", e)
        raise ExtraccionFacturaError(
            "No se pudo procesar el archivo con el servicio de IA. Probá de nuevo en unos minutos."
        )

    resultado = None
    for bloque in respuesta.content:
        if getattr(bloque, 'type', None) == 'tool_use' and bloque.name == _TOOL_NAME:
            resultado = bloque.input
            break

    if resultado is None:
        logger.error("Importación IA: la respuesta de Claude no incluyó la tool esperada: %s", respuesta.content)
        raise ExtraccionFacturaError(
            "No se pudieron leer productos del archivo. Probá con una foto más clara o el PDF original."
        )

    lineas = resultado.get('lineas') or []
    if not lineas:
        raise ExtraccionFacturaError(
            "No se detectaron productos en el archivo. Probá con una foto más clara o el PDF original."
        )

    return {
        'proveedor': resultado.get('proveedor'),
        'numero_documento': resultado.get('numero_documento'),
        'fecha': resultado.get('fecha'),
        'lineas': lineas,
    }
