# Guía para Desplegar Cambios de Facturación a Producción

Esta guía te ayudará a desplegar todos los cambios relacionados con la facturación electrónica a producción.

## 📋 Checklist Pre-Deployment

### 1. Verificar Cambios en el Código

Los siguientes archivos han sido modificados/creados:

**Backend:**
- `inventario/models.py` - Modelo `Factura` y campos de facturación en `Tienda`
- `inventario/serializers.py` - `FacturaSerializer`, `EmitirFacturaSerializer`, campo `tiene_factura` en `VentaSerializer`
- `inventario/views.py` - `FacturaViewSet`, endpoint `emitir_factura`, endpoint `generar_pdf`
- `inventario/services/facturacion_service.py` - Servicio completo de facturación AFIP/ARCA
- `inventario/services/__init__.py` - Archivo para hacer `services` un paquete
- `inventario/management/commands/convertir_certificados_afip.py` - Comando para convertir certificados
- `inventario/admin.py` - Configuración de admin para `Factura` y campos fiscales
- `mi_tienda_backend/urls.py` - Rutas para facturas
- `requirements.txt` - Nuevas dependencias: `pyafipws`, `reportlab`, `setuptools`

**Frontend:**
- `src/components/PuntoVenta.js` - Integración de facturación en el flujo de ventas
- `src/components/FacturaImpresion.js` - Componente para mostrar/imprimir facturas
- `src/components/VentasPage.jsx` - Botón "Factura" para reimprimir facturas
- `src/App.js` - Ruta `/factura`

**Documentación:**
- `FACTURACION_ELECTRONICA.md` - Documentación del sistema
- `CONFIGURAR_FACTURACION.md` - Guía de configuración
- `DEPLOY_PRODUCCION.md` - Este archivo

### 2. Verificar Migraciones

Las migraciones ya están creadas:
- `0010_tienda_api_key_arca_tienda_certificado_afip_and_more.py` - Incluye todos los campos de facturación

**IMPORTANTE:** Verifica que esta migración esté aplicada en staging antes de producción.

### 3. Dependencias Nuevas

Asegúrate de que estas dependencias estén en `requirements.txt`:
```
pyafipws @ git+https://github.com/reingart/pyafipws.git
reportlab==4.0.9
setuptools
requests==2.31.0
cryptography==41.0.7
```

## 🚀 Pasos para Desplegar a Producción

### Paso 1: Preparar el Entorno Local

```bash
# 1. Asegúrate de estar en la rama correcta
git status
git branch

# 2. Verifica que todos los cambios estén commiteados
git status

# 3. Si hay cambios sin commitear, haz commit
git add .
git commit -m "feat: Integración completa de facturación electrónica AFIP/ARCA"
```

### Paso 2: Verificar Migraciones en Staging

```bash
cd backend

# Verificar estado de migraciones
DJANGO_ENVIRONMENT=staging python3 manage.py showmigrations inventario

# Si hay migraciones pendientes, aplicarlas primero en staging
DJANGO_ENVIRONMENT=staging python3 manage.py migrate inventario
```

### Paso 3: Crear Migraciones (si es necesario)

```bash
# Solo si hay cambios en modelos que no estén en migraciones
DJANGO_ENVIRONMENT=staging python3 manage.py makemigrations

# Revisar las migraciones creadas
ls -la inventario/migrations/
```

### Paso 4: Subir Cambios a Git

```bash
# Desde la raíz del proyecto
cd /Users/arinardon/Proyectos/Bonito_Amor

# Verificar qué archivos se van a subir
git status

# Agregar todos los archivos nuevos/modificados
git add .

# Hacer commit con mensaje descriptivo
git commit -m "feat: Sistema completo de facturación electrónica

- Integración con AFIP y ARCA
- Emisión automática de Facturas A, B y C según condición IVA
- Generación de PDFs de facturas
- Configuración por tienda de certificados AFIP/ARCA
- Endpoints API para facturación
- Componentes React para facturación e impresión
- Documentación completa del sistema"

# Subir a repositorio remoto
git push origin main
# O si usas otra rama:
# git push origin tu-rama
```

### Paso 5: Desplegar en Producción

**IMPORTANTE:** Asegúrate de tener un backup de la base de datos antes de continuar.

```bash
# 1. Conectarte al servidor de producción
# (ajusta según tu método de deployment)

# 2. Hacer pull de los cambios
cd /ruta/a/tu/proyecto
git pull origin main

# 3. Activar entorno virtual (si aplica)
source venv/bin/activate

# 4. Instalar nuevas dependencias
pip install -r requirements.txt

# 5. Aplicar migraciones
DJANGO_ENVIRONMENT=production python manage.py migrate inventario

# 6. Recolectar archivos estáticos (si aplica)
DJANGO_ENVIRONMENT=production python manage.py collectstatic --noinput

# 7. Reiniciar el servidor
# Depende de tu configuración:
# - Si usas systemd: sudo systemctl restart gunicorn
# - Si usas supervisor: sudo supervisorctl restart bonito_amor
# - Si usas Heroku: git push heroku main (ya aplica migraciones automáticamente)
```

### Paso 6: Verificar en Producción

1. **Verificar que el servidor esté corriendo:**
   ```bash
   # Verificar logs
   tail -f /ruta/a/logs/django.log
   ```

2. **Verificar que las migraciones se aplicaron:**
   ```bash
   DJANGO_ENVIRONMENT=production python manage.py showmigrations inventario
   ```
   Todas las migraciones deben mostrar `[X]` (aplicadas).

3. **Verificar que las tablas existen:**
   ```bash
   # Conectarse a la base de datos y verificar
   # Debe existir la tabla inventario_factura
   ```

4. **Probar en el frontend:**
   - Acceder a la aplicación
   - Verificar que el punto de venta funcione
   - Probar emitir una factura de prueba (en modo testing de AFIP)

## ⚠️ Consideraciones Importantes

### Certificados AFIP

**EN PRODUCCIÓN DEBES:**
1. Cambiar los certificados de testing por certificados de producción
2. Actualizar la URL de AFIP en el código (si no está configurada automáticamente)
3. Verificar que el CUIT y punto de venta estén habilitados en AFIP para producción

### Variables de Entorno

Asegúrate de que en producción tengas configuradas:
- `DJANGO_ENVIRONMENT=production`
- `DJANGO_SECRET_KEY` (único para producción)
- Variables de base de datos de producción
- Cualquier otra variable específica de producción

### Base de Datos

**ANTES DE APLICAR MIGRACIONES:**
- ✅ Hacer backup completo de la base de datos
- ✅ Probar las migraciones en staging primero
- ✅ Verificar que no haya conflictos

### Frontend

Si usas un build separado:
```bash
cd frontend
npm run build
# Subir los archivos de build/ al servidor
```

## 🔍 Troubleshooting

### Error: "No such table: inventario_factura"
**Solución:** Las migraciones no se aplicaron. Ejecuta:
```bash
DJANGO_ENVIRONMENT=production python manage.py migrate inventario
```

### Error: "ModuleNotFoundError: No module named 'pyafipws'"
**Solución:** Las dependencias no se instalaron. Ejecuta:
```bash
pip install -r requirements.txt
```

### Error: "ModuleNotFoundError: No module named 'reportlab'"
**Solución:** Instala reportlab:
```bash
pip install reportlab==4.0.9
```

### Error al emitir factura: "Certificado no válido"
**Solución:** Verifica que los certificados en producción sean de producción, no de testing.

## 📝 Notas Finales

- Las facturas antiguas pueden tener `tipo_comprobante` como número (1, 6, 11). El código maneja ambos formatos.
- El sistema determina automáticamente el tipo de factura según la condición IVA del cliente.
- Los PDFs se generan dinámicamente, no se almacenan en el servidor (a menos que configures `pdf_factura` en el modelo).

## ✅ Checklist Post-Deployment

- [ ] Migraciones aplicadas correctamente
- [ ] Servidor Django funcionando
- [ ] Frontend accesible
- [ ] Certificados AFIP de producción configurados
- [ ] Probar emisión de factura de prueba
- [ ] Verificar que los PDFs se generen correctamente
- [ ] Verificar logs sin errores críticos



