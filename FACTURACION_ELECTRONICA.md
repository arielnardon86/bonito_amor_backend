# Integración de Facturación Electrónica (AFIP/ARCA)

Este documento explica cómo configurar y usar la integración de facturación electrónica con AFIP y ARCA para cada tienda.

## Características Implementadas

✅ Soporte para AFIP (Administración Federal de Ingresos Públicos)  
✅ Soporte para ARCA (Administración de Recursos de la Administración Nacional)  
✅ Configuración por tienda  
✅ Emisión de facturas A, B y C  
✅ Almacenamiento de CAE y datos de facturación  
✅ API REST para emitir y consultar facturas  

## Instalación

### 1. Instalar dependencias

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

Las nuevas dependencias incluyen:
- `pyafipws==0.7.35` - Biblioteca para integración con AFIP
- `requests==2.31.0` - Para comunicación HTTP con ARCA
- `cryptography==41.0.7` - Para manejo de certificados

### 2. Crear y aplicar migraciones

```bash
DJANGO_ENVIRONMENT=staging python manage.py makemigrations
DJANGO_ENVIRONMENT=staging python manage.py migrate
```

## Configuración por Tienda

### Configurar una tienda para facturación AFIP

1. **Obtener certificados AFIP:**
   - Debes tener el certificado digital (.crt) y la clave privada (.key) de AFIP
   - Estos archivos se obtienen del sitio de AFIP

2. **Configurar la tienda en el admin o mediante API:**

```python
# Ejemplo de configuración
tienda = Tienda.objects.get(nombre="Mi Tienda")
tienda.cuit = "20-12345678-9"
tienda.punto_venta = 1
tienda.tipo_facturacion = "AFIP"
tienda.modo_test_afip = True  # True para testing, False para producción

# Convertir certificados a base64
import base64
with open('certificado.crt', 'rb') as f:
    tienda.certificado_afip = base64.b64encode(f.read()).decode('utf-8')

with open('clave.key', 'rb') as f:
    tienda.clave_privada_afip = base64.b64encode(f.read()).decode('utf-8')

tienda.save()
```

### Configurar una tienda para facturación ARCA

```python
tienda = Tienda.objects.get(nombre="Mi Tienda")
tienda.cuit = "20-12345678-9"
tienda.punto_venta = 1
tienda.tipo_facturacion = "ARCA"
tienda.api_key_arca = "tu-api-key-de-arca"
tienda.url_arca = "https://api.arca.com/facturacion"  # URL del servicio ARCA
tienda.save()
```

## Uso de la API

### Emitir una factura desde una venta

**Endpoint:** `POST /api/ventas/{venta_id}/emitir_factura/`

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Body:**
```json
{
  "cliente_nombre": "Juan Pérez",
  "cliente_cuit": "20-12345678-9",
  "cliente_domicilio": "Av. Corrientes 1234, CABA",
  "cliente_tipo_documento": "80",
  "cliente_condicion_iva": "RI"
}
```

**Respuesta exitosa:**
```json
{
  "message": "Factura emitida exitosamente",
  "factura": {
    "id": "uuid-de-factura",
    "numero_comprobante": 1,
    "punto_venta": 1,
    "tipo_comprobante": "B",
    "numero_factura_completo": "0001-00000001",
    "cae": "12345678901234",
    "fecha_vencimiento_cae": "2024-01-15",
    "subtotal": 1000.00,
    "impuesto_iva": 210.00,
    "total": 1210.00,
    "estado": "EMITIDA",
    "sistema_facturacion": "AFIP"
  }
}
```

### Consultar facturas

**Endpoint:** `GET /api/facturas/`

**Filtros disponibles:**
- `?tienda={tienda_id}` - Filtrar por tienda
- `?estado={PENDIENTE|EMITIDA|ANULADA|ERROR}` - Filtrar por estado
- `?tipo_comprobante={A|B|C}` - Filtrar por tipo
- `?search={texto}` - Buscar por número, cliente, CAE
- `?ordering={-fecha_emision,numero_comprobante,total}` - Ordenar

**Ejemplo:**
```bash
GET /api/facturas/?estado=EMITIDA&tienda={tienda_id}
```

### Ver detalle de una factura

**Endpoint:** `GET /api/facturas/{factura_id}/`

## Tipos de Comprobante

- **Factura A**: Para clientes Responsables Inscriptos
- **Factura B**: Para Consumidor Final
- **Factura C**: Para clientes Exentos

## Condiciones de IVA

- `RI`: Responsable Inscripto
- `CF`: Consumidor Final
- `EX`: Exento
- `MT`: Monotributo
- `NR`: No Responsable

## Campos agregados al modelo Venta

- `facturada`: Boolean que indica si la venta tiene factura
- `cliente_nombre`: Nombre del cliente
- `cliente_cuit`: CUIT del cliente
- `cliente_domicilio`: Domicilio del cliente
- `cliente_tipo_documento`: Tipo de documento

## Modelo Factura

El modelo `Factura` almacena toda la información de las facturas emitidas:
- Números de comprobante
- CAE (Código de Autorización Electrónica)
- Datos del cliente
- Totales (subtotal, IVA, total)
- Estado (PENDIENTE, EMITIDA, ANULADA, ERROR)
- Respuesta completa del servicio de facturación

## Notas Importantes

### AFIP Testing vs Producción

- **Modo Testing**: Usa `modo_test_afip=True` para pruebas en ambiente de homologación
- **Modo Producción**: Usa `modo_test_afip=False` para facturar en producción

### Certificados AFIP

Los certificados deben estar en formato PEM y codificados en base64 en la base de datos. Esto permite almacenarlos de forma segura.

### ARCA

ARCA requiere configuración de API Key y URL del servicio. Consulta la documentación de tu proveedor ARCA para obtener estos valores.

### Validaciones

- No se puede facturar una venta anulada
- No se puede facturar dos veces la misma venta
- Cada tienda debe tener su sistema de facturación configurado

## Próximos Pasos

1. **Generar PDFs de facturas**: Implementar generación de PDFs para las facturas emitidas
2. **Nota de crédito**: Agregar funcionalidad para emitir notas de crédito
3. **Anulación de facturas**: Implementar anulación de facturas emitidas
4. **Reportes**: Crear reportes de facturas por período

## Solución de Problemas

### Error: "Certificados AFIP no configurados"
- Verifica que los certificados estén correctamente codificados en base64
- Asegúrate de que los archivos sean válidos

### Error: "AFIP rechazó la factura"
- Revisa los logs en `error_mensaje` de la factura
- Verifica que el CUIT y punto de venta sean correctos
- En modo testing, asegúrate de usar datos de prueba válidos

### Error: "ARCA rechazó la factura"
- Verifica que la API Key sea correcta
- Confirma que la URL del servicio sea válida
- Revisa la respuesta del servicio en `respuesta_bruta`

## Seguridad

⚠️ **IMPORTANTE**: 
- Los certificados y claves privadas están almacenados en la base de datos
- Considera usar encriptación adicional para estos campos sensibles
- No compartas las credenciales de producción
- Usa HTTPS para todas las comunicaciones

## Referencias

- [Documentación AFIP](https://www.afip.gob.ar/fe/documentos/manual_desarrollador_COMPG_v2_10.pdf)
- [PyAFIPws](https://github.com/reingart/pyafipws)
- [ARCA - Documentación oficial](consultar con tu proveedor)





