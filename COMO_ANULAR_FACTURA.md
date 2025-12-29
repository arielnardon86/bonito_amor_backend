# 📋 Cómo Anular una Factura Electrónica

## 📌 Descripción

Esta guía explica cómo anular una factura electrónica emitida a través del web service de AFIP.

## ⚠️ Importante

- Solo se pueden anular facturas con estado **EMITIDA**
- La anulación es **irreversible** una vez procesada en AFIP
- Solo usuarios autorizados pueden anular facturas (superusuarios o usuarios de la misma tienda)

## 🚀 Formas de Anular una Factura

### Opción 1: Desde el Backend API (Recomendado)

#### Endpoint:
```
POST /api/facturas/{factura_id}/anular/
```

#### Ejemplo con cURL:
```bash
curl -X POST \
  https://tu-dominio.com/api/facturas/{factura_id}/anular/ \
  -H "Authorization: Bearer {tu_token_jwt}" \
  -H "Content-Type: application/json"
```

#### Ejemplo con JavaScript/React:
```javascript
const anularFactura = async (facturaId) => {
  try {
    const response = await axios.post(
      `${BASE_API_ENDPOINT}/api/facturas/${facturaId}/anular/`,
      {},
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );
    
    if (response.status === 200) {
      console.log('Factura anulada exitosamente:', response.data);
      // { mensaje: "Factura anulada exitosamente", factura_id: "...", estado: "ANULADA" }
    }
  } catch (error) {
    console.error('Error al anular factura:', error.response?.data);
  }
};
```

### Opción 2: Desde Django Admin

1. **Ingresa al Django Admin**: https://tu-dominio.com/admin/
2. **Ve a**: Inventario > Facturas
3. **Selecciona la factura** que quieres anular
4. **Cambia el estado** de `EMITIDA` a `ANULADA`
5. **Guarda los cambios**

⚠️ **Nota**: Esta opción solo cambia el estado en la base de datos local. **NO anula la factura en AFIP**. Usa solo si la factura no se puede anular en AFIP (ej: ya venció el CAE).

### Opción 3: Desde el Shell de Django (Solo para desarrollo/testing)

```python
from inventario.models import Factura
from inventario.services.facturacion_service import FacturacionService

# Obtener la factura
factura = Factura.objects.get(id='uuid-de-la-factura')

# Inicializar servicio de facturación
service = FacturacionService(factura.tienda)

# Anular factura
exito, error = service.anular_factura(factura)

if exito:
    factura.estado = 'ANULADA'
    factura.save()
    print("✅ Factura anulada exitosamente")
else:
    print(f"❌ Error: {error}")
```

## 📋 Requisitos para Anular

La factura debe cumplir:

- ✅ Estado = `EMITIDA`
- ✅ Tener `numero_comprobante` asignado
- ✅ Tener `punto_venta` configurado
- ✅ Tener `cae` (Código de Autorización Electrónica)
- ✅ El CAE no debe haber vencido (aunque AFIP puede permitir anular facturas vencidas en algunos casos)

## 🔍 Verificar Estado de una Factura

### Desde la API:
```bash
GET /api/facturas/{factura_id}/
```

### Respuesta ejemplo:
```json
{
  "id": "uuid",
  "estado": "EMITIDA",
  "numero_comprobante": 123,
  "cae": "12345678901234",
  "fecha_vencimiento_cae": "2025-01-15",
  ...
}
```

## ❌ Errores Comunes

### Error: "La factura no puede ser anulada. Estado actual: ANULADA"
- **Causa**: La factura ya está anulada
- **Solución**: Verifica el estado de la factura antes de intentar anular

### Error: "La factura no tiene los datos necesarios para anular"
- **Causa**: Falta número de comprobante o CAE
- **Solución**: Solo se pueden anular facturas que fueron emitidas exitosamente

### Error: "AFIP rechazó la anulación: [...]"
- **Causa**: AFIP rechazó la solicitud de anulación
- **Soluciones posibles**:
  - Verifica que el CAE no haya vencido
  - Verifica que el punto de venta y número de comprobante sean correctos
  - Verifica que los certificados AFIP sean válidos
  - Contacta a AFIP si el error persiste

### Error: "No tienes permiso para anular facturas de esta tienda"
- **Causa**: El usuario no tiene permisos
- **Solución**: Solo superusuarios o usuarios de la misma tienda pueden anular

## 📝 Notas Importantes

1. **Tiempo límite**: En general, las facturas pueden anularse dentro de un plazo determinado después de su emisión. Consulta la documentación de AFIP para detalles específicos.

2. **Impacto en la venta**: Anular una factura **NO anula automáticamente la venta**. Si necesitas anular la venta también, debes hacerlo por separado.

3. **Registro**: La anulación queda registrada en AFIP y en tu base de datos. El estado de la factura cambiará a `ANULADA`.

4. **Generación de nueva factura**: Si anulas una factura por error, puedes emitir una nueva factura para la misma venta (siempre que la venta no esté anulada).

## 🔄 Flujo Completo de Anulación

1. **Verificar que la factura puede ser anulada**:
   ```bash
   GET /api/facturas/{factura_id}/
   ```
   Verifica que `estado == "EMITIDA"`

2. **Anular la factura**:
   ```bash
   POST /api/facturas/{factura_id}/anular/
   ```

3. **Verificar que se anuló correctamente**:
   ```bash
   GET /api/facturas/{factura_id}/
   ```
   Verifica que `estado == "ANULADA"`

## 📚 Referencias

- **Documentación AFIP**: https://www.afip.gob.ar/fe/documentos/
- **Manual del Desarrollador**: Consulta la sección sobre anulación de comprobantes

