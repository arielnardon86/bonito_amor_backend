# 🔑 Cómo Obtener las Keys de Firebase para Notificaciones Push

## ✅ Ya configurado
- ✅ Configuración de Firebase (apiKey, authDomain, projectId, etc.)
- ✅ Service Worker configurado
- ✅ Código de notificaciones implementado
- ✅ VAPID Key configurada en el frontend
- ✅ Server Key obtenida

## ⚠️ IMPORTANTE: Agregar Server Key en Render

### Server Key (para el backend)

**Ya tienes la clave:** `697ddca3b1428809d31f4bbbdaa898f7ae11fdf7`

**⚠️ ACCIÓN REQUERIDA: Agregar en Render (backend)**

1. Ve a tu dashboard de Render
2. Selecciona el servicio del backend
3. Ve a **Environment** (Variables de entorno)
4. Agrega una nueva variable:
   - **Key:** `FIREBASE_SERVER_KEY`
   - **Value:** `697ddca3b1428809d31f4bbbdaa898f7ae11fdf7`
5. Guarda los cambios
6. Render reiniciará automáticamente el servicio

**⚠️ IMPORTANTE:** Esta clave NO debe estar en el código, solo como variable de entorno en Render.

**Pasos:**
1. Ve a https://console.firebase.google.com/
2. Selecciona tu proyecto "total-stock"
3. Ve a **Configuración del proyecto** (ícono de engranaje) → **Cloud Messaging**
4. En la sección **"Web Push certificates"**, haz clic en **"Generar nuevo par de claves"**
5. Se generará una **"Clave pública"** - **COPIA ESTA CLAVE**
6. Esta clave es tu **VAPID Key**

**Dónde usarla:**
- Opción 1: Agregar como variable de entorno en Render (recomendado):
  ```
  REACT_APP_FIREBASE_VAPID_KEY=tu-vapid-key-aqui
  ```
- Opción 2: Editar directamente `frontend/src/firebase.js` y reemplazar:
  ```javascript
  const vapidKey = "tu-vapid-key-aqui";
  ```

**Pasos:**
1. Ve a Firebase Console → Tu proyecto "total-stock"
2. Ve a **Configuración del proyecto** (ícono de engranaje) → **Cloud Messaging**
3. Busca la sección **"Cloud Messaging API (Legacy)"**
4. Verás una **"Clave del servidor"** (Server Key) - **COPIA ESTA CLAVE**
5. Si no la ves, puede que necesites habilitar la API primero:
   - Ve a https://console.cloud.google.com/
   - Selecciona el proyecto "total-stock"
   - Ve a **APIs & Services** → **Library**
   - Busca "Firebase Cloud Messaging API"
   - Habilítala si no está habilitada
   - Luego vuelve a Firebase Console → Cloud Messaging

**Dónde usarla:**
- Agregar como variable de entorno en Render (backend):
  ```
  FIREBASE_SERVER_KEY=tu-server-key-aqui
  ```

## 📝 Resumen

1. ✅ **VAPID Key** → Ya configurada en `frontend/src/firebase.js`
2. ✅ **Server Key** → Obtenida, **debe agregarse en Render (backend)** como variable de entorno `FIREBASE_SERVER_KEY`

## ✅ Verificación

Una vez que agregues ambas keys:
1. Despliega el frontend y backend
2. Abre la app en el celular
3. Inicia sesión
4. Deberías ver una solicitud de permiso para notificaciones
5. Acepta el permiso
6. Haz una venta de prueba
7. Deberías recibir una notificación en el celular

## 🔍 Si no funciona

1. Verifica que ambas keys estén correctamente configuradas
2. Verifica que el Service Worker esté registrado (DevTools → Application → Service Workers)
3. Verifica los logs del backend para ver si hay errores al enviar notificaciones
4. Verifica que el usuario tenga una tienda asignada
