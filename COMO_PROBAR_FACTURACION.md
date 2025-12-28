# Cómo Probar la Facturación Electrónica

## Paso 1: Configurar una Tienda para Facturación

### Opción A: Configurar para Testing (sin facturar realmente)

1. Ve al admin: `http://localhost:8000/admin/inventario/tienda/`
2. Edita una tienda existente o crea una nueva
3. En **Configuración Fiscal**:
   - **Tipo de Facturación**: Selecciona `AFIP` o `ARCA`
   - **CUIT**: Ingresa un CUIT de prueba (ej: `20-12345678-9`)
   - **Punto de Venta**: `1`
4. Si elegiste **AFIP**:
   - Marca **Modo Test AFIP** ✅ (importante para pruebas)
   - Deja los campos de certificados vacíos por ahora (o usa certificados de prueba de AFIP)
5. Si elegiste **ARCA**:
   - **API Key ARCA**: Usa una clave de prueba si tienes
   - **URL ARCA**: URL del servicio de pruebas
6. Guarda los cambios

## Paso 2: Crear una Venta

Puedes crear una venta desde:
- El admin de Django
- La API REST
- El frontend (si ya lo tienes conectado)

### Desde el Admin:
1. Ve a `http://localhost:8000/admin/inventario/venta/add/`
2. Completa los datos:
   - **Tienda**: Selecciona la tienda que configuraste
   - **Método de Pago**: Selecciona uno
   - Agrega detalles de venta (productos)
3. Guarda la venta

### Desde la API (con Postman o curl):

```bash
# 1. Obtener token JWT
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "tu-usuario",
    "password": "tu-contraseña"
  }'

# 2. Crear una venta
curl -X POST http://localhost:8000/api/ventas/ \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "tienda_slug": "nombre-de-tu-tienda",
    "detalles": [
      {
        "producto_id": "uuid-del-producto",
        "cantidad": 2,
        "precio_unitario": 100.00
      }
    ]
  }'
```

## Paso 3: Emitir una Factura

### Desde la API (Recomendado para pruebas):

```bash
# Reemplaza VENTA_ID con el ID de la venta que creaste
curl -X POST http://localhost:8000/api/ventas/VENTA_ID/emitir_factura/ \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_nombre": "Juan Pérez",
    "cliente_cuit": "20-12345678-9",
    "cliente_domicilio": "Av. Corrientes 1234, CABA",
    "cliente_tipo_documento": "80",
    "cliente_condicion_iva": "CF"
  }'
```

### Desde el Admin (si agregas la acción):

Por ahora, la emisión de factura solo está disponible por API. Puedes usar:
- Postman
- curl
- El frontend (cuando lo implementes)

## Paso 4: Verificar el Resultado

### Ver la factura creada:

```bash
# Listar todas las facturas
curl http://localhost:8000/api/facturas/ \
  -H "Authorization: Bearer TU_TOKEN_AQUI"

# Ver una factura específica
curl http://localhost:8000/api/facturas/FACTURA_ID/ \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

### En el Admin:

1. Ve a `http://localhost:8000/admin/inventario/factura/`
2. Verás todas las facturas emitidas
3. Revisa:
   - **Estado**: `EMITIDA`, `ERROR`, o `PENDIENTE`
   - **CAE**: Si está en `EMITIDA`, tendrá un CAE
   - **Error Mensaje**: Si hay error, verás el motivo

## Paso 5: Verificar en la Venta

1. Ve a la venta que facturaste
2. Verifica que el campo **Facturada** esté marcado como `True`
3. Verifica que los datos del cliente se hayan guardado

## Ejemplo Completo de Prueba

### 1. Verificar que el servidor esté corriendo:
```bash
cd backend
source venv/bin/activate
./scripts/run_staging.sh runserver
```

### 2. Obtener token:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"tu-usuario","password":"tu-contraseña"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access'])")
```

### 3. Listar tiendas disponibles:
```bash
curl http://localhost:8000/api/tiendas/ \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Crear una venta de prueba (ajusta los IDs):
```bash
curl -X POST http://localhost:8000/api/ventas/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tienda_slug": "nombre-de-tu-tienda",
    "detalles": [
      {
        "producto_id": "uuid-del-producto",
        "cantidad": 1,
        "precio_unitario": 1000.00
      }
    ]
  }'
```

### 5. Emitir factura (reemplaza VENTA_ID):
```bash
curl -X POST http://localhost:8000/api/ventas/VENTA_ID/emitir_factura/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_nombre": "Consumidor Final",
    "cliente_cuit": "",
    "cliente_domicilio": "",
    "cliente_tipo_documento": "99",
    "cliente_condicion_iva": "CF"
  }'
```

## Casos de Prueba

### Prueba 1: Factura B (Consumidor Final)
```json
{
  "cliente_nombre": "Consumidor Final",
  "cliente_cuit": "",
  "cliente_domicilio": "",
  "cliente_tipo_documento": "99",
  "cliente_condicion_iva": "CF"
}
```

### Prueba 2: Factura A (Responsable Inscripto)
```json
{
  "cliente_nombre": "Empresa SA",
  "cliente_cuit": "20-12345678-9",
  "cliente_domicilio": "Av. Corrientes 1234, CABA",
  "cliente_tipo_documento": "80",
  "cliente_condicion_iva": "RI"
}
```

## Verificación de Errores Comunes

### Error: "La tienda no tiene configurado un sistema de facturación"
- **Solución**: Ve al admin y configura `tipo_facturacion` en la tienda

### Error: "Certificados AFIP no configurados"
- **Solución**: Si usas AFIP, configura los certificados. En modo test puedes dejar vacío si no los tienes

### Error: "Esta venta ya tiene una factura emitida"
- **Solución**: Es correcto, una venta solo puede tener una factura. Crea una nueva venta

### Error: "No tienes permiso para emitir facturas de esta tienda"
- **Solución**: Asegúrate de estar autenticado con un usuario que tenga acceso a esa tienda

## Próximos Pasos

Una vez que todo funcione:
1. Configura los certificados reales de AFIP (si usas AFIP)
2. Obtén las credenciales reales de ARCA (si usas ARCA)
3. Desactiva el modo test cuando estés listo para producción
4. Implementa la generación de PDFs de facturas
5. Conecta el frontend para que los usuarios puedan facturar desde la UI


