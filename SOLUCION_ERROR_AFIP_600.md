# Solución al Error AFIP 600: "No apareció CUIT en lista de relaciones"

## Error
```
AFIP rechazó la factura: Errores: ['600: ValidacionDeToken: No aparecio CUIT en lista de relaciones: 20312213473']
```

## Causa
Este error indica que el CUIT especificado (20312213473) no está autorizado o relacionado con el certificado digital que se está utilizando para autenticarse con AFIP.

## Posibles Causas

1. **El CUIT configurado en la tienda no coincide con el CUIT del certificado**
   - El certificado digital contiene un CUIT específico (el que fue usado para generar el certificado)
   - El CUIT configurado en la base de datos (`tienda.cuit`) debe coincidir exactamente con el CUIT del certificado

2. **El servicio web no está autorizado para ese CUIT**
   - El CUIT debe tener el servicio de Facturación Electrónica autorizado en AFIP
   - En producción, el servicio debe estar habilitado y autorizado

3. **Delegación no aceptada**
   - Si estás operando en nombre de otra empresa, la delegación debe ser aceptada en AFIP
   - Esto es común cuando un contador o sistema externo opera en nombre de una empresa

4. **Certificado incorrecto**
   - Se está usando un certificado de una cuenta personal en lugar del certificado de la empresa
   - El certificado debe ser generado desde la cuenta correcta de AFIP

## Solución Paso a Paso

### 1. Verificar el CUIT del Certificado

El CUIT está embebido en el certificado digital. Para verificarlo:

**Opción A: Usando OpenSSL (en tu computadora local)**
```bash
# Guardar el certificado en un archivo (decodificar desde base64 si es necesario)
# Si tienes el certificado en base64 en la base de datos, primero decodifícalo:

python3 -c "
import base64
import sys

# Pegar aquí el certificado base64 (sin BEGIN/END headers)
cert_b64 = 'TU_CERTIFICADO_BASE64_AQUI'

# Decodificar
cert_data = base64.b64decode(cert_b64)

# Guardar en archivo
with open('certificado.crt', 'wb') as f:
    f.write(cert_data)

print('Certificado guardado en certificado.crt')
"

# Luego usar OpenSSL para ver el CUIT
openssl x509 -in certificado.crt -noout -subject -nameopt sep_multiline
```

**Opción B: Verificar desde AFIP**
1. Ingresar a https://www.afip.gob.ar con tu Clave Fiscal
2. Ir a "Sistemas" → "Clave Fiscal" → "Certificados Digitales"
3. Verificar qué certificado estás usando y su CUIT asociado

### 2. Verificar el CUIT Configurado en la Base de Datos

Asegúrate de que el CUIT configurado en la tienda coincida exactamente con el CUIT del certificado:

```python
# Desde Django shell o desde el admin
from inventario.models import Tienda

tienda = Tienda.objects.get(id=TU_TIENDA_ID)  # Reemplazar con el ID de tu tienda
print(f"CUIT configurado: {tienda.cuit}")
print(f"CUIT sin guiones: {tienda.cuit.replace('-', '')}")
```

**IMPORTANTE:** El CUIT debe coincidir exactamente. Si el certificado tiene CUIT `20312213473`, entonces en la base de datos debe estar configurado como:
- `20-31221347-3` (con guiones), o
- `20312213473` (sin guiones)

El código automáticamente quita los guiones cuando se usa, así que ambos formatos funcionan.

### 3. Verificar Autorización del Servicio Web en AFIP

1. Ingresar a https://www.afip.gob.ar con tu Clave Fiscal
2. Ir a "Sistemas" → "Facturación Electrónica" (o "Regímenes de Facturación y Registración")
3. Verificar que el servicio esté **ACTIVO** y **AUTORIZADO**
4. Verificar que el punto de venta esté correctamente configurado

### 4. Aceptar Delegación (si aplica)

Si estás operando en nombre de otra empresa (delegación):

1. Ingresar a AFIP con tu Clave Fiscal
2. Ir a "Sistemas" → "Facturación Electrónica"
3. Verificar si hay delegaciones pendientes
4. Aceptar la delegación si existe
5. Asegurarte de autorizar el servicio web seleccionando el CUIT correcto como "Representado"

### 5. Verificar que el Certificado y Clave Privada Coincidan

El certificado y la clave privada deben ser un par válido. Para verificar:

```bash
# Verificar que el certificado y la clave privada coincidan
openssl x509 -noout -modulus -in certificado.crt | openssl md5
openssl rsa -noout -modulus -in clave_privada.key | openssl md5
```

Ambos comandos deben devolver el mismo hash MD5. Si no coinciden, el certificado y la clave privada no son un par válido.

### 6. Regenerar el Certificado (si es necesario)

Si el certificado es incorrecto o está asociado al CUIT incorrecto:

1. Ingresar a https://www.afip.gob.ar con tu Clave Fiscal
2. Ir a "Sistemas" → "Clave Fiscal" → "Certificados Digitales"
3. Revocar el certificado actual si es necesario
4. Generar un nuevo certificado desde la cuenta correcta (empresa, no personal)
5. Descargar el nuevo certificado (.crt) y clave privada (.key)
6. Convertir a base64 y actualizar en la base de datos:

```bash
python manage.py convertir_certificados_afip nuevo_certificado.crt nueva_clave.key
```

Esto te dará los valores en base64 que debes copiar a la base de datos.

### 7. Limpiar el Cache de Tokens

A veces el cache puede tener tokens antiguos. Para limpiarlo en producción (Render):

```bash
# Conectarse al shell de Render y ejecutar:
rm -rf /tmp/pyafipws_cache_shared_*
```

O desde Django:

```python
import os
import tempfile
import hashlib
from inventario.models import Tienda

tienda = Tienda.objects.get(id=TU_TIENDA_ID)
cuit_hash = hashlib.md5(tienda.cuit.encode()).hexdigest()[:8]
cache_dir = os.path.join(tempfile.gettempdir(), f"pyafipws_cache_shared_{cuit_hash}")

if os.path.exists(cache_dir):
    import shutil
    shutil.rmtree(cache_dir)
    print(f"Cache limpiado: {cache_dir}")
else:
    print("No existe cache para limpiar")
```

## Verificación Final

Después de corregir el problema, verifica que todo esté correcto:

1. **CUIT del certificado** = **CUIT en la base de datos**
2. **Servicio web autorizado** en AFIP para ese CUIT
3. **Punto de venta habilitado** y del tipo correcto (RECE para web service)
4. **Certificado y clave privada** son un par válido
5. **Cache limpiado** (si se cambió el certificado)

## Contacto

Si después de seguir todos estos pasos el problema persiste, contacta al soporte de AFIP o consulta con un especialista en facturación electrónica.

## Referencias

- [AFIP - Facturación Electrónica](https://www.afip.gob.ar/fe/)
- [AFIP - Certificados Digitales](https://www.afip.gob.ar/claveFiscal/)
- [Documentación pyafipws](https://github.com/reingart/pyafipws)


