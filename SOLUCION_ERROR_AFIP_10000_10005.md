# 🔧 Solución: Error AFIP 10000 y 10005

## ❌ Error

```
AFIP rechazó la factura: Errores: 
['10000: NO AUTORIZADO A EMITIR COMPROBANTES - LA CUIT INFORMADA NO CORRESPONDE A UN RESPONSABLE INSCRIPTO EN EL IMPUESTO IVA.', 
'10005: NO AUTORIZADO A EMITIR COMPROBANTES - EL PUNTO DE VENTA INFORMADO DEBE ESTAR DADO DE ALTA Y SER DEL TIPO RECE']
```

## 🔍 Significado de los Errores

### Error 10000
- **Problema**: La CUIT informada no está registrada como Responsable Inscripto en IVA
- **Causas posibles**:
  1. La CUIT no está correctamente registrada en AFIP
  2. La CUIT no corresponde a un Responsable Inscripto
  3. Estás usando certificados de testing pero el CUIT no está habilitado para homologación
  4. El CUIT ingresado tiene un formato incorrecto o tiene espacios/guiones mal ubicados

### Error 10005
- **Problema**: El punto de venta no está dado de alta o no es del tipo RECE
- **RECE**: Registro de Emisión de Comprobantes Electrónicos
- **Causas posibles**:
  1. El punto de venta no está habilitado en AFIP
  2. El punto de venta no está habilitado para facturación electrónica
  3. El punto de venta no corresponde al CUIT informado
  4. Estás usando el ambiente incorrecto (homologación vs producción)

## ✅ Soluciones Paso a Paso

### Paso 1: Verificar que estás en el Ambiente Correcto

**Para Testing/Homologación:**
1. Verifica que `modo_test_afip = True` en el Django Admin para tu tienda
2. Debes usar certificados de **homologación/testing**
3. La CUIT debe estar habilitada para el ambiente de **homologación**

**Para Producción:**
1. Verifica que `modo_test_afip = False` en el Django Admin
2. Debes usar certificados de **producción**
3. La CUIT y punto de venta deben estar habilitados para **producción**

### Paso 2: Verificar la CUIT en el Portal de AFIP

1. **Ingresa al Portal de AFIP**: https://www.afip.gob.ar/autonomos/
2. **Usa tu CUIT y clave fiscal** para ingresar
3. **Verifica tu condición frente al IVA**:
   - Ve a "Mi AFIP" > "Mi cuenta"
   - O "Constancia de Inscripción"
   - Debes estar como **Responsable Inscripto (RI)**

### Paso 3: Habilitar el Punto de Venta en AFIP

1. **Ingresa al Portal de AFIP**
2. **Navega a**: Facturación Electrónica > Puntos de Venta
3. **Verifica que tu punto de venta esté**:
   - ✅ Dado de alta
   - ✅ Habilitado para facturación electrónica
   - ✅ Del tipo **RECE** (Registro de Emisión de Comprobantes Electrónicos)

4. **Si NO está habilitado**:
   - Solicita el alta del punto de venta
   - Puede requerir documentación adicional
   - El trámite puede tardar algunos días

### Paso 4: Verificar Configuración en Django Admin

1. **Ingresa al Django Admin**: https://tu-dominio.com/admin/
2. **Ve a**: Inventario > Tiendas
3. **Selecciona tu tienda** y verifica:

   **Campos obligatorios:**
   - ✅ **CUIT**: Debe ser el CUIT completo (con guiones: XX-XXXXXXXX-X)
   - ✅ **Punto de venta**: Debe coincidir exactamente con el habilitado en AFIP
   - ✅ **Tipo de facturación**: Debe ser "AFIP"
   - ✅ **Modo test AFIP**: 
     - `True` para homologación/testing
     - `False` para producción
   - ✅ **Certificado AFIP**: Debe ser el certificado correcto para el ambiente
   - ✅ **Clave privada AFIP**: Debe ser la clave correspondiente al certificado

### Paso 5: Obtener Certificados Correctos

**Para Homologación/Testing:**
1. **Descarga certificados de testing** desde:
   - https://www.afip.gob.ar/fe/documentos/manual_desarrollador_COMPG_v2_10.pdf
   - O desde el Portal de AFIP > Facturación Electrónica > Certificados de Homologación

2. **Usa los certificados de homologación** que proporciona AFIP

**Para Producción:**
1. **Obtén certificados de producción** desde el Portal de AFIP
2. **Configúralos en Django Admin** usando el comando:
   ```bash
   python manage.py convertir_certificados_afip certificado.crt clave.key
   ```
3. **Pega los valores base64** en los campos correspondientes

### Paso 6: Verificar Formato de CUIT

El CUIT debe tener exactamente este formato:
- ✅ **Correcto**: `20-12345678-9` (11 dígitos con guiones)
- ❌ **Incorrecto**: `20123456789` (sin guiones)
- ❌ **Incorrecto**: `20 12345678 9` (con espacios)
- ❌ **Incorrecto**: `20-12345678` (faltan dígitos)

### Paso 7: Verificar Punto de Venta

1. **El punto de venta debe ser un número** (ej: `1`, `2`, `0001`)
2. **Debe coincidir exactamente** con el registrado en AFIP
3. **Verifica en AFIP** que ese punto de venta esté habilitado para RECE

## 🔄 Checklist de Verificación

Antes de volver a intentar emitir una factura, verifica:

- [ ] Estoy usando el ambiente correcto (homologación/producción)
- [ ] El CUIT está en formato correcto (XX-XXXXXXXX-X)
- [ ] El CUIT corresponde a un Responsable Inscripto en IVA
- [ ] El punto de venta está habilitado en AFIP
- [ ] El punto de venta es del tipo RECE
- [ ] Los certificados corresponden al ambiente correcto
- [ ] `modo_test_afip` está configurado correctamente
- [ ] Los certificados están correctamente codificados en base64

## 📝 Códigos de Error AFIP Comunes

| Código | Descripción | Solución |
|--------|-------------|----------|
| 10000 | CUIT no corresponde a Responsable Inscripto | Verificar condición IVA en AFIP |
| 10005 | Punto de venta no habilitado o no es RECE | Habilitar punto de venta en AFIP |
| 10019 | Campo Id en AlicIVA es obligatorio | Error del código (ya solucionado) |
| 10049 | FchServDesde debe informarse solo si Concepto es 2 o 3 | Error del código (ya solucionado) |

## 🆘 Si el Problema Persiste

1. **Verifica los logs de Django** para ver más detalles del error
2. **Revisa la respuesta completa de AFIP** en el campo `respuesta_bruta` de la factura en Django Admin
3. **Contacta a AFIP** si:
   - El punto de venta no aparece en el listado
   - No puedes habilitarlo desde el portal
   - Tienes dudas sobre tu condición frente al IVA

## 📚 Recursos de AFIP

- **Portal AFIP**: https://www.afip.gob.ar/
- **Facturación Electrónica**: https://www.afip.gob.ar/fe/
- **Manual del Desarrollador**: https://www.afip.gob.ar/fe/documentos/
- **Puntos de Venta**: Portal AFIP > Facturación Electrónica > Puntos de Venta

## ⚠️ Importante

- **Los certificados de homologación** solo funcionan con CUITs habilitados para testing
- **Los certificados de producción** solo funcionan con CUITs reales y puntos de venta habilitados
- **El trámite de habilitación** de puntos de venta puede tardar varios días hábiles
- **No mezcles** certificados de homologación con producción o viceversa



