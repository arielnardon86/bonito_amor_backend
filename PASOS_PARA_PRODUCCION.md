# 🚀 Pasos Rápidos para Llevar a Producción

## ✅ Estado Actual

- ✅ Todas las migraciones están creadas (0010 incluye todo)
- ✅ Dependencias actualizadas en `requirements.txt`
- ✅ Código completo y probado en staging

## 📝 Pasos para Desplegar

### 1. Verificar Estado Local

```bash
cd /Users/arinardon/Proyectos/Bonito_Amor/backend
./scripts/verificar_pre_deploy.sh
```

Este script verificará:
- Dependencias en requirements.txt
- Migraciones existentes
- Archivos nuevos
- Estado de Git

### 2. Hacer Commit y Push a Git

```bash
# Desde la raíz del proyecto
cd /Users/arinardon/Proyectos/Bonito_Amor

# Ver qué archivos se van a subir
git status

# Agregar todos los cambios
git add .

# Commit con mensaje descriptivo
git commit -m "feat: Sistema completo de facturación electrónica AFIP/ARCA

- Integración con AFIP y ARCA para facturación electrónica
- Emisión automática de Facturas A, B y C según condición IVA
- Generación de PDFs de facturas
- Configuración por tienda de certificados y credenciales
- Endpoints API para facturación e impresión
- Componentes React para facturación e impresión
- Documentación completa del sistema"

# Subir a repositorio
git push origin main
# O la rama que uses: git push origin tu-rama
```

### 3. En el Servidor de Producción

```bash
# 1. Hacer backup de la base de datos (IMPORTANTE)
# Ejemplo con PostgreSQL:
pg_dump -h localhost -U usuario -d nombre_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Hacer pull de los cambios
cd /ruta/a/tu/proyecto
git pull origin main

# 3. Activar entorno virtual
source venv/bin/activate

# 4. Instalar nuevas dependencias
pip install -r requirements.txt

# 5. Aplicar migraciones
DJANGO_ENVIRONMENT=production python manage.py migrate inventario

# 6. Verificar que las migraciones se aplicaron
DJANGO_ENVIRONMENT=production python manage.py showmigrations inventario
# Todas deben mostrar [X]

# 7. Recolectar archivos estáticos (si aplica)
DJANGO_ENVIRONMENT=production python manage.py collectstatic --noinput

# 8. Reiniciar el servidor
# Depende de tu configuración:
# - systemd: sudo systemctl restart gunicorn
# - supervisor: sudo supervisorctl restart tu_app
# - Heroku: git push heroku main (aplica migraciones automáticamente)
```

### 4. Verificar en Producción

1. **Verificar logs:**
   ```bash
   tail -f /ruta/a/logs/django.log
   ```

2. **Probar la aplicación:**
   - Acceder al frontend
   - Verificar que el punto de venta funcione
   - Probar emitir una factura (con certificados de producción)

3. **Verificar base de datos:**
   ```sql
   -- Verificar que la tabla existe
   SELECT * FROM inventario_factura LIMIT 1;
   
   -- Verificar campos en tienda
   SELECT nombre, tipo_facturacion, cuit, punto_venta FROM inventario_tienda;
   ```

## ⚠️ IMPORTANTE: Certificados AFIP en Producción

**ANTES de usar en producción:**

1. **Obtener certificados de PRODUCCIÓN** (no de testing):
   - Ve a https://www.afip.gob.ar/fe/
   - Genera certificados de PRODUCCIÓN
   - Conviértelos a base64 usando:
     ```bash
     python manage.py convertir_certificados_afip certificado_prod.crt clave_prod.key
     ```

2. **Configurar en Django Admin:**
   - Ve a la tienda en Django Admin
   - Pega los certificados de producción (base64)
   - **Desmarca** "Modo test AFIP" (debe estar desmarcado)
   - Guarda

3. **Verificar en AFIP:**
   - El CUIT debe estar habilitado para facturación electrónica
   - El punto de venta debe estar activo
   - Todo debe estar en modo PRODUCCIÓN

## 📋 Checklist Final

- [ ] Backup de base de datos realizado
- [ ] Cambios commiteados y pusheados a Git
- [ ] Migraciones aplicadas en producción
- [ ] Dependencias instaladas
- [ ] Servidor reiniciado
- [ ] Certificados de producción configurados
- [ ] Modo test desactivado en producción
- [ ] Prueba de facturación exitosa

## 🆘 Si Algo Sale Mal

1. **Revertir migraciones:**
   ```bash
   DJANGO_ENVIRONMENT=production python manage.py migrate inventario 0009
   ```

2. **Restaurar backup:**
   ```bash
   psql -h localhost -U usuario -d nombre_db < backup_archivo.sql
   ```

3. **Revertir código:**
   ```bash
   git revert HEAD
   git push origin main
   ```

## 📚 Documentación Adicional

- `DEPLOY_PRODUCCION.md` - Guía detallada completa
- `CONFIGURAR_FACTURACION.md` - Cómo configurar AFIP/ARCA
- `FACTURACION_ELECTRONICA.md` - Documentación técnica



