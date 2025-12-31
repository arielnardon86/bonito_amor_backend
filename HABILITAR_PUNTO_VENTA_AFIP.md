# 🔧 Solución: Error 10005 - Punto de Venta No Habilitado

## ❌ Error

```
AFIP rechazó la factura: Errores: 
['10005: NO AUTORIZADO A EMITIR COMPROBANTES - EL PUNTO DE VENTA INFORMADO DEBE ESTAR DADO DE ALTA Y SER DEL TIPO RECE']
```

## 🔍 Significado

Este error significa que:
1. El punto de venta **NO está dado de alta** en AFIP, O
2. El punto de venta **NO está habilitado** para facturación electrónica, O
3. El punto de venta **NO es del tipo RECE** (Registro de Emisión de Comprobantes Electrónicos)

## ✅ Solución: Habilitar el Punto de Venta en AFIP

### Paso 1: Acceder al Portal de AFIP

1. **Ve al Portal de AFIP**: https://www.afip.gob.ar/
2. **Inicia sesión** con tu CUIT y clave fiscal

### Paso 2: Ir a Facturación Electrónica

1. **Busca la sección "Facturación Electrónica"** o "FE" en el menú principal
2. O ve directamente a: https://www.afip.gob.ar/fe/
3. **Selecciona**: "Puntos de Venta" o "Gestión de Puntos de Venta"

### Paso 3: Verificar/Alta del Punto de Venta

#### Si el Punto de Venta NO existe:

1. **Clic en "Alta de Punto de Venta"** o "Solicitar Punto de Venta"
2. **Completa el formulario**:
   - Número de punto de venta (generalmente empiezas con `1`)
   - Tipo de actividad
   - Descripción/Ubicación
3. **Solicita el alta** (puede requerir documentación adicional)
4. **Espera la aprobación** (puede tardar varios días hábiles)

#### Si el Punto de Venta existe pero NO está habilitado para RECE:

1. **Busca tu punto de venta** en la lista
2. **Verifica su estado**:
   - ✅ Debe estar "ACTIVO" o "HABILITADO"
   - ✅ Debe estar habilitado para "RECE" (Registro de Emisión de Comprobantes Electrónicos)
   - ✅ NO debe estar "SUSPENDIDO" o "BAJA"

3. **Si NO está habilitado para RECE**:
   - Busca la opción "Habilitar para RECE" o "Activar Facturación Electrónica"
   - Selecciona el tipo de comprobante (Factura A, B, C según corresponda)
   - Completa la solicitud
   - Espera la aprobación (puede tardar varios días)

### Paso 4: Verificar en Django Admin

Después de habilitar el punto de venta en AFIP:

1. **Ve a Django Admin**: https://tu-dominio.com/admin/
2. **Inventario > Tiendas > [Tu Tienda]**
3. **Verifica que**:
   - ✅ **Punto de venta**: Coincida EXACTAMENTE con el habilitado en AFIP
   - ✅ **CUIT**: Sea el correcto
   - ✅ **Tipo de facturación**: Sea "AFIP"
   - ✅ **Modo test AFIP**: Esté configurado correctamente (True para testing, False para producción)

## 🔄 Diferencias entre Testing y Producción

### Ambiente de Testing/Homologación:

- Puedes usar puntos de venta de prueba proporcionados por AFIP
- Los puntos de venta se habilitan más rápidamente
- Ve a la sección de "Homologación" o "Ambiente de Pruebas"

### Ambiente de Producción:

- Debes usar tus puntos de venta reales
- Requieren documentación y aprobación
- El trámite puede tardar varios días hábiles
- Debes completar todos los datos fiscales requeridos

## ⚠️ Importante

1. **El punto de venta debe estar habilitado para RECE**
   - RECE = Registro de Emisión de Comprobantes Electrónicos
   - NO solo "punto de venta", sino específicamente habilitado para facturación electrónica

2. **El número de punto de venta debe coincidir exactamente**
   - Si en AFIP tienes `1`, en Django Admin también debe ser `1`
   - Si en AFIP tienes `0001`, en Django Admin debe ser `1` (normalmente se guarda sin ceros)

3. **El trámite puede tardar**
   - Alta de punto de venta: 3-5 días hábiles
   - Habilitación para RECE: 3-5 días hábiles
   - Total: Puede tardar hasta 10 días hábiles

## 📋 Checklist

Antes de intentar emitir facturas nuevamente:

- [ ] El punto de venta está dado de alta en AFIP
- [ ] El punto de venta está ACTIVO/HABILITADO (no suspendido)
- [ ] El punto de venta está habilitado para RECE (Registro de Emisión de Comprobantes Electrónicos)
- [ ] El número de punto de venta en Django Admin coincide con el de AFIP
- [ ] El CUIT en Django Admin coincide con el de AFIP
- [ ] El ambiente (testing/producción) está configurado correctamente
- [ ] Los certificados corresponden al ambiente correcto

## 🆘 Si el Problema Persiste

1. **Verifica en el Portal de AFIP**:
   - Ve a "Puntos de Venta" > [Tu Punto de Venta]
   - Revisa el detalle completo
   - Verifica que aparezca "RECE" o "Facturación Electrónica" como habilitado

2. **Contacta a AFIP**:
   - Llama al 0800-999-2347
   - O envía un mensaje desde el Portal de AFIP
   - Explica que necesitas habilitar tu punto de venta para RECE

3. **Verifica los certificados**:
   - Asegúrate de usar certificados del ambiente correcto (testing vs producción)
   - Verifica que los certificados estén vigentes

## 📚 Recursos

- **Portal AFIP**: https://www.afip.gob.ar/
- **Facturación Electrónica**: https://www.afip.gob.ar/fe/
- **Ayuda Telefónica AFIP**: 0800-999-2347
- **Manual del Desarrollador**: https://www.afip.gob.ar/fe/documentos/

## ✅ Verificación Final

Después de habilitar el punto de venta:

1. Espera 24-48 horas para que el cambio se propague en los sistemas de AFIP
2. Verifica nuevamente en el Portal de AFIP que el punto de venta esté habilitado
3. Intenta emitir una factura desde tu aplicación
4. Si sigue fallando, verifica los logs de Django para más detalles del error



