# 🔧 Configurar Variables de Entorno en Render para Producción

## ⚠️ PROBLEMA ACTUAL

El sistema está usando SQLite local en lugar de PostgreSQL en la nube porque falta la variable de entorno `DJANGO_ENVIRONMENT`.

**Síntoma:**
```
Using SQLite for development
Django's DATABASES['default'] configured as: django.db.backends.sqlite3
```

## ✅ SOLUCIÓN: Configurar Variables de Entorno en Render

### Paso 1: Ir a la Configuración de Variables de Entorno

1. Ve a tu servicio en Render: https://dashboard.render.com
2. Selecciona tu servicio `bonito-amor-backend`
3. En el menú lateral, haz clic en **"Environment"** o **"Environment Variables"**

### Paso 2: Agregar/Verificar Variables de Entorno

Debes tener las siguientes variables configuradas:

#### 🔴 OBLIGATORIAS:

1. **`DJANGO_ENVIRONMENT`**
   - **Valor:** `production`
   - **Descripción:** Define que el sistema está en producción
   - **⚠️ CRÍTICO:** Sin esta variable, el sistema usa SQLite local

2. **`DATABASE_URL`**
   - **Valor:** Tu URL de PostgreSQL (Render la genera automáticamente)
   - **Formato:** `postgresql://usuario:password@host:puerto/nombre_db?sslmode=require`
   - **⚠️ CRÍTICO:** Sin esta variable, el sistema no puede conectarse a PostgreSQL

#### 🟡 RECOMENDADAS:

3. **`DJANGO_SECRET_KEY`**
   - **Valor:** Una clave secreta segura (genera una nueva si no la tienes)
   - **Generar:** `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

4. **`DJANGO_DEBUG`**
   - **Valor:** `False` (para producción)
   - **Descripción:** Desactiva el modo debug en producción

### Paso 3: Verificar que DATABASE_URL está Configurada

Render normalmente configura `DATABASE_URL` automáticamente cuando:
- Tienes un servicio de PostgreSQL en Render
- El servicio de PostgreSQL está vinculado a tu Web Service

**Para verificar:**
1. Ve a tu servicio de PostgreSQL en Render
2. En la sección "Connections", verifica que tu Web Service esté conectado
3. Si no está conectado, haz clic en "Connect" y selecciona tu Web Service

### Paso 4: Agregar Variables Manualmente

Si necesitas agregar variables manualmente:

1. En la página de Environment Variables de tu servicio
2. Haz clic en **"Add Environment Variable"**
3. Agrega cada variable:
   - **Key:** `DJANGO_ENVIRONMENT`
   - **Value:** `production`
   - Haz clic en **"Save Changes"**

Repite para todas las variables necesarias.

### Paso 5: Reiniciar el Servicio

Después de agregar/modificar variables de entorno:

1. Ve a la página principal de tu servicio
2. Haz clic en **"Manual Deploy"** → **"Deploy latest commit"**
   - O simplemente espera a que Render detecte los cambios y reinicie automáticamente

### Paso 6: Verificar que Funciona

Después del reinicio, revisa los logs. Deberías ver:

```
--- PRODUCTION DATABASE CONFIG ---
✅ DATABASE_URL found in environment variables!
✅ Engine: django.db.backends.postgresql
✅ Database Name: [nombre de tu BD]
✅ Host: [host de tu BD en la nube]
✅ Using Cloud PostgreSQL Database
```

**Si ves esto, está funcionando correctamente.**

## 🔍 Verificar Variables Actuales

Puedes verificar qué variables están configuradas usando el endpoint de verificación:

```bash
curl https://bonito-amor-backend.onrender.com/api/verificar-database/
```

Este endpoint mostrará:
- Qué tipo de base de datos está usando
- Si está usando PostgreSQL (nube) o SQLite (local)
- Información de la conexión

## 📋 Checklist de Variables

Antes de desplegar, verifica que tengas:

- [ ] `DJANGO_ENVIRONMENT=production`
- [ ] `DATABASE_URL` (configurada automáticamente por Render si tienes PostgreSQL)
- [ ] `DJANGO_SECRET_KEY` (clave secreta segura)
- [ ] `DJANGO_DEBUG=False` (opcional pero recomendado)

## 🚨 Problemas Comunes

### Problema 1: "Using SQLite for development"
**Causa:** `DJANGO_ENVIRONMENT` no está configurada o no es `production`
**Solución:** Agregar `DJANGO_ENVIRONMENT=production`

### Problema 2: "DATABASE_URL NOT found"
**Causa:** No hay servicio de PostgreSQL vinculado o `DATABASE_URL` no está configurada
**Solución:** 
1. Crear un servicio de PostgreSQL en Render (si no existe)
2. Vincularlo a tu Web Service
3. Verificar que `DATABASE_URL` aparezca en las variables de entorno

### Problema 3: "Connection refused" o errores de conexión
**Causa:** PostgreSQL no está corriendo o la URL es incorrecta
**Solución:** Verificar que el servicio de PostgreSQL esté activo en Render

## 📞 Soporte

Si después de seguir estos pasos sigue usando SQLite, verifica:
1. Que las variables estén guardadas correctamente
2. Que el servicio se haya reiniciado después de agregar las variables
3. Los logs del servicio para ver qué está detectando
