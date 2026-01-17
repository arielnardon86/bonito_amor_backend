# Guía: Cómo Configurar Facturación en el Admin de Django

## Paso 1: Acceder al Admin de Django

1. Ve a `http://localhost:8000/admin/`
2. Inicia sesión con tu usuario superusuario
3. Ve a **Tiendas** → Selecciona la tienda que quieres configurar

## Paso 2: Completar los Campos Fiscales

### Campos Básicos (Obligatorios)

1. **CUIT**: Formato `XX-XXXXXXXX-X` (ejemplo: `20-12345678-9`)
2. **Punto de Venta**: Número del punto de venta (generalmente `1`)
3. **Tipo de Facturación**: Selecciona:
   - `AFIP` - Para usar facturación de AFIP
   - `ARCA` - Para usar facturación de ARCA
   - `NINGUNA` - Si no quieres facturación electrónica

---

## Si eliges AFIP:

### Opción A: Usar el Script (Recomendado)

1. Tienes tus archivos `.crt` y `.key` de AFIP
2. Ejecuta en la terminal:
```bash
cd backend
source venv/bin/activate
DJANGO_ENVIRONMENT=staging python manage.py convertir_certificados_afip ruta/al/certificado.crt ruta/a/la/clave.key
```

3. El script te dará dos bloques de texto en base64
4. Copia cada uno y pégalo en el admin:
   - **Certificado AFIP**: pega el primer bloque
   - **Clave Privada AFIP**: pega el segundo bloque

### Opción B: Convertir Manualmente

Si prefieres hacerlo manualmente:

1. Abre el archivo `.crt` en un editor de texto
2. Copia TODO el contenido (incluyendo las líneas `-----BEGIN CERTIFICATE-----` y `-----END CERTIFICATE-----`)
3. Convierte a base64:
```bash
# En macOS/Linux
base64 -i certificado.crt

# O en Python
python3 -c "import base64; print(base64.b64encode(open('certificado.crt', 'rb').read()).decode('utf-8'))"
```
4. Repite lo mismo para el archivo `.key`

### Campos para AFIP:

- **Certificado AFIP**: El contenido COMPLETO del archivo `.crt` codificado en base64 (NO solo el nombre del archivo)
- **Clave Privada AFIP**: El contenido COMPLETO del archivo `.key` codificado en base64 (NO solo el nombre del archivo)
- **Modo Test AFIP**: 
  - ✅ Marca esta casilla si estás probando (homologación)
  - ❌ Desmarca cuando vayas a producción

### ⚠️ IMPORTANTE: Certificados para Modo Testing

**Para modo testing/homologación, necesitas certificados válidos de AFIP:**

1. **Obtener certificados de homologación:**
   - **Paso 1**: Ve al sitio web de AFIP para facturación electrónica: https://www.afip.gob.ar/fe/
   - **Paso 2**: Inicia sesión con tu CUIT
   - **Paso 3**: Ve a la sección de **"Certificados Digitales"** o **"Homologación"**
   - **Paso 4**: Solicita/genera certificados de **HOMOLOGACIÓN** (ambiente de prueba)
   - **Paso 5**: Descarga el certificado (.crt) y la clave privada (.key)
   
   ⚠️ **Los certificados de producción NO funcionan en modo testing/homologación**
   ⚠️ **Debes usar SOLO certificados específicos de homologación**

2. **Errores comunes y soluciones:**
   
   **❌ Error: "Certificado no emitido por AC de confianza"**
   - **Causa**: Los certificados no son de homologación válidos o fueron emitidos por una AC no reconocida por AFIP
   - **Solución**: 
     1. Ve a https://www.afip.gob.ar/fe/ y solicita certificados de homologación nuevos
     2. Asegúrate de descargarlos del ambiente de homologación (no producción)
     3. Regenera los certificados si es necesario
   
   **❌ Error: "Firma inválida"**
   - **Causa**: El certificado y la clave privada no coinciden
   - **Solución**: Asegúrate de usar el certificado y la clave privada que pertenecen al mismo par generado
   
   **❌ Error: "Certificado expirado"**
   - **Causa**: El certificado está vencido
   - **Solución**: Solicita nuevos certificados de homologación en AFIP

3. **Verificar certificados:**
   - Asegúrate de que el CUIT configurado coincida con el certificado
   - En modo test, usa SOLO certificados de homologación
   - Los certificados de producción NO funcionan en modo test
   - Verifica que los certificados no estén expirados

4. **Habilitar servicio en AFIP:**
   - El CUIT debe estar habilitado para Facturación Electrónica en AFIP
   - El punto de venta debe estar activo y habilitado
   - Para verificar/habilitar: https://www.afip.gob.ar/fe/
   - En modo testing, asegúrate de usar un CUIT de prueba válido

5. **URLs del ambiente de homologación (Testing):**
   - WSAA (Autenticación): `https://wsaahomo.afip.gov.ar/ws/services/LoginCms` (pyafipws agrega `?wsdl` automáticamente)
   - WSFEv1 (Facturación): `https://wswhomo.afip.gov.ar/wsfev1/service.asmx` (pyafipws agrega `?wsdl` automáticamente)
   
   **URLs del ambiente de producción:**
   - WSAA (Autenticación): `https://wsaa.afip.gov.ar/ws/services/LoginCms` (pyafipws agrega `?wsdl` automáticamente)
   - WSFEv1 (Facturación): `https://servicios1.afip.gov.ar/wsfev1/service.asmx` (pyafipws agrega `?wsdl` automáticamente)
   
   ⚠️ **IMPORTANTE**: pyafipws agrega automáticamente el parámetro `?wsdl` a las URLs, por lo que NO debemos incluirlo en la configuración. Si incluimos `?WSDL` manualmente, pyafipws agregará otro `?wsdl`, resultando en `?WSDL?wsdl` que causa errores.
   ⚠️ **El sistema usa automáticamente estas URLs según el valor de "Modo Test AFIP" en la configuración de la tienda.**

### ⚠️ Error: "Computador no autorizado a acceder al servicio"

Este error significa que:
- ❌ El CUIT no está habilitado para facturación electrónica en AFIP
- ❌ El punto de venta no está activo
- ❌ El servicio no está activado para ese CUIT

**Solución:**
1. Ve a https://www.afip.gob.ar/fe/
2. Inicia sesión con tu CUIT
3. Verifica que el servicio de Facturación Electrónica esté **ACTIVO**
4. Verifica que el punto de venta esté **HABILITADO**
5. En modo testing, usa CUITs de prueba válidos proporcionados por AFIP

---

### ⚠️ Error: "junk after document element: line 2, column 0"

Este error indica un problema al parsear XML, generalmente causado por:

1. **Certificados inválidos o mal formateados:**
   - Los certificados no son válidos para el ambiente (testing vs producción)
   - Los certificados están corruptos o mal codificados en base64
   - El certificado y la clave privada no coinciden

2. **Respuesta malformada del servidor AFIP:**
   - Problemas temporales de conectividad
   - Respuesta con múltiples documentos XML

3. **Formato incorrecto de los certificados:**
   - Los certificados no están en formato PEM válido
   - Hay contenido extra antes o después del certificado

**Solución:**
1. **Verifica los certificados:**
   ```bash
   # Usa el comando de Django para convertir certificados
   cd backend
   ./scripts/run_staging.sh convertir_certificados_afip tu_certificado.crt tu_clave.key
   ```

2. **Verifica que los certificados sean del ambiente correcto:**
   - En modo testing, usa SOLO certificados de homologación
   - En modo producción, usa certificados de producción
   - No mezcles certificados de diferentes ambientes

3. **Verifica el formato base64:**
   - Los certificados deben estar codificados en base64 SIN encabezados/footers
   - No deben tener saltos de línea o espacios extra

4. **Intenta regenerar los certificados:**
   - Descarga nuevos certificados desde AFIP
   - Conviértelos nuevamente usando el comando de conversión

5. **Revisa los logs del servidor Django:**
   - Busca mensajes que indiquen problemas con el ticket de acceso
   - Verifica que la autenticación se complete correctamente antes del error

---

## Si eliges ARCA:

### Campos para ARCA:

1. **API Key ARCA**: 
   - Es la clave API que te proporciona tu proveedor de servicios ARCA
   - Ejemplo: `abc123xyz789def456ghi012jkl345mno678pqr901`
   - **¿Dónde obtenerla?**: Contacta a tu proveedor de servicios ARCA o revisa tu cuenta en su plataforma

2. **URL ARCA**: 
   - Es la URL del endpoint del servicio de facturación
   - Ejemplo: `https://api.arca.com/v1/facturacion`
   - **¿Dónde obtenerla?**: Debe estar en la documentación de tu proveedor ARCA

### Nota sobre ARCA:

ARCA puede ser:
- Un servicio gubernamental específico
- Un proveedor tercerizado de facturación electrónica
- Consulta con tu contador o proveedor de servicios fiscales para obtener estas credenciales

---

## Ejemplo Visual

### En el Admin de Django verás:

```
┌─────────────────────────────────────────┐
│ Configuración Fiscal                    │
├─────────────────────────────────────────┤
│ Tipo de Facturación: [AFIP ▼]          │
│ CUIT: [20-12345678-9]                   │
│ Punto de Venta: [1]                     │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Configuración AFIP                      │
├─────────────────────────────────────────┤
│ Certificado AFIP:                       │
│ [Pega aquí el contenido base64...]     │
│                                         │
│ Clave Privada AFIP:                     │
│ [Pega aquí el contenido base64...]     │
│                                         │
│ ☑ Modo Test AFIP                        │
└─────────────────────────────────────────┘
```

---

## Resumen Importante

### ❌ NO hagas esto:
- NO pongas solo el nombre del archivo (ej: `certificado.crt`)
- NO pongas la ruta del archivo (ej: `/ruta/certificado.crt`)
- NO dejes espacios innecesarios en los textos base64

### ✅ SÍ haz esto:
- SÍ pega el contenido COMPLETO codificado en base64
- SÍ usa el script `convertir_certificados_afip` para facilitar el proceso
- SÍ guarda una copia segura de tus certificados originales

---

## Verificar que Funciona

Después de guardar la configuración:

1. Crea una venta de prueba
2. Intenta emitir una factura usando el endpoint:
   ```
   POST /api/ventas/{venta_id}/emitir_factura/
   ```
3. Si hay errores, revisa el campo `error_mensaje` en la factura creada

---

## Soporte

Si tienes problemas:
1. Verifica que los certificados sean válidos
2. En modo test, asegúrate de usar datos de prueba de AFIP
3. Para ARCA, verifica que la API Key y URL sean correctas con tu proveedor

