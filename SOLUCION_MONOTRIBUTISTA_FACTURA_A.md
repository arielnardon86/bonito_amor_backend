# 🔧 Solución: Error para Monotributistas al Emitir Factura

## ❌ Problema

Error al emitir factura en producción:
```
AFIP rechazó la factura: Errores: 
['10000: NO AUTORIZADO A EMITIR COMPROBANTES - LA CUIT INFORMADA NO CORRESPONDE A UN RESPONSABLE INSCRIPTO EN EL IMPUESTO IVA.']
```

## 🔍 Causa

**Monotributistas NO pueden emitir Factura A** (solo Responsables Inscriptos pueden hacerlo).

El código anterior determinaba el tipo de factura solo basándose en la condición IVA del **cliente**, pero no consideraba la condición IVA del **emisor** (tienda).

### Reglas de AFIP:

1. **Factura A**: Solo puede ser emitida por Responsables Inscriptos (RI) y solo para clientes Responsables Inscriptos
2. **Factura B**: Puede ser emitida por cualquier condición IVA, para Consumidores Finales, Monotributistas, No Responsables
3. **Factura C**: Puede ser emitida por cualquier condición IVA, solo para clientes Exentos

### Problema en Testing vs Producción:

- En **testing/homologación**, AFIP es más permisivo y puede aceptar Factura A incluso para Monotributistas
- En **producción**, AFIP rechaza estrictamente las Facturas A emitidas por no Responsables Inscriptos

## ✅ Solución Implementada

Se ha agregado un nuevo campo `condicion_iva_emisor` al modelo `Tienda` para almacenar la condición IVA del emisor (tienda).

### Cambios Realizados:

1. **Nuevo campo en modelo Tienda**: `condicion_iva_emisor`
   - Valores posibles: RI, MT, CF, EX, NR
   - Valor por defecto: MT (Monotributista)
   - Help text: "Importante: Solo Responsables Inscriptos pueden emitir Factura A"

2. **Lógica actualizada en `_determinar_tipo_comprobante`**:
   - Ahora verifica **TANTO** la condición IVA del cliente **COMO** la del emisor
   - Solo emite Factura A si el emisor es RI **Y** el cliente es RI
   - Si el emisor es Monotributista, siempre emite Factura B (o C si el cliente es Exento)

3. **Actualizado Django Admin**:
   - El campo `condicion_iva_emisor` aparece en el fieldset "Configuración Fiscal"

## 🚀 Pasos para Aplicar la Solución

### 1. Crear y Aplicar la Migración

**En staging/local:**
```bash
cd backend
source venv/bin/activate
DJANGO_ENVIRONMENT=staging python manage.py migrate inventario 0012
```

**En producción (Render Shell):**
```bash
cd /opt/render/project/src/backend
python manage.py migrate inventario 0012
```

### 2. Configurar la Condición IVA del Emisor

1. **Ingresa al Django Admin**: https://tu-dominio.com/admin/
2. **Ve a**: Inventario > Tiendas
3. **Selecciona tu tienda**
4. **En la sección "Configuración Fiscal"**, configura:
   - **Condición IVA Emisor**: Selecciona "Monotributista" (MT)
5. **Guarda los cambios**

### 3. Verificar la Configuración

Después de configurar:
- ✅ El sistema **NO intentará** emitir Factura A para clientes Responsables Inscriptos
- ✅ Siempre emitirá **Factura B** (a menos que el cliente sea Exento, en cuyo caso emitirá Factura C)
- ✅ AFIP **aceptará** las facturas porque son del tipo correcto para Monotributistas

## 📋 Comportamiento Esperado

### Para Monotributistas (Emisor):

| Condición IVA Cliente | Tipo de Factura Emitida |
|----------------------|------------------------|
| Responsable Inscripto (RI) | **Factura B** (no A, porque el emisor no puede emitir A) |
| Monotributista (MT) | **Factura B** |
| Consumidor Final (CF) | **Factura B** |
| Exento (EX) | **Factura C** |
| No Responsable (NR) | **Factura B** |

### Para Responsables Inscriptos (Emisor):

| Condición IVA Cliente | Tipo de Factura Emitida |
|----------------------|------------------------|
| Responsable Inscripto (RI) | **Factura A** |
| Monotributista (MT) | **Factura B** |
| Consumidor Final (CF) | **Factura B** |
| Exento (EX) | **Factura C** |
| No Responsable (NR) | **Factura B** |

## ⚠️ Importante

- **Si eres Monotributista**: Configura `condicion_iva_emisor = 'MT'` y **NO** intentarás emitir Factura A
- **Si eres Responsable Inscripto**: Configura `condicion_iva_emisor = 'RI'` y podrás emitir Factura A para clientes RI
- **El valor por defecto es MT** porque es la condición más común para pequeñas empresas

## 🔄 Archivos Modificados

- `backend/inventario/models.py` - Agregado campo `condicion_iva_emisor`
- `backend/inventario/services/facturacion_service.py` - Actualizada lógica de `_determinar_tipo_comprobante`
- `backend/inventario/admin.py` - Agregado campo al admin
- `backend/inventario/migrations/0012_tienda_condicion_iva_emisor.py` - Nueva migración

## ✅ Verificación

Después de aplicar la migración y configurar el campo:

1. **Verifica en Django Admin** que el campo esté configurado correctamente
2. **Intenta emitir una factura** para un cliente Responsable Inscripto
3. **Debería emitir Factura B** (no A) si eres Monotributista
4. **AFIP debería aceptar** la factura sin errores

