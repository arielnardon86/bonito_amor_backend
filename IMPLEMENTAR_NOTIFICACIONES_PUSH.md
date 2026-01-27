# 📱 Implementación de Notificaciones Push para Ventas

## 🎯 Objetivo
Recibir notificaciones en el celular cuando se realiza una venta en la tienda a la que estás logueado.

## ✅ Solución: Firebase Cloud Messaging (FCM) - PWA (Progressive Web App)

**Ventajas:**
- ✅ Gratis hasta 1 millón de notificaciones/mes
- ✅ Funciona en web y móvil (PWA) - NO necesitas app nativa
- ✅ Funciona incluso con la app cerrada
- ✅ Fácil de integrar
- ✅ No requiere publicar en App Store/Play Store

## 📋 Pasos de Implementación

### Paso 1: Configurar Firebase

1. Ve a https://console.firebase.google.com/
2. Crea un nuevo proyecto o usa uno existente
3. Habilita Cloud Messaging:
   - Ve a "Build" → "Cloud Messaging"
   - Habilita "Cloud Messaging API (Legacy)"
4. Agrega una app web:
   - Haz clic en el ícono `</>` (Add app)
   - Registra la app con un nombre
   - Copia la configuración de Firebase (firebaseConfig)
5. Obtén la VAPID Key:
   - Ve a "Configuración del proyecto" → "Cloud Messaging"
   - En "Web Push certificates", genera un nuevo par de claves
   - Copia la "Clave pública" (VAPID Key)
6. Obtén el Server Key:
   - En la misma página, copia la "Clave del servidor" (Server Key)

### Paso 2: Configurar Variables de Entorno

#### Backend (Render):
⚠️ **IMPORTANTE:** Agrega esta variable de entorno en Render (dashboard → Environment):
```
FIREBASE_SERVER_KEY=697ddca3b1428809d31f4bbbdaa898f7ae11fdf7
```

**Pasos:**
1. Ve a tu dashboard de Render
2. Selecciona el servicio del backend
3. Ve a **Environment** (Variables de entorno)
4. Agrega nueva variable: `FIREBASE_SERVER_KEY` = `697ddca3b1428809d31f4bbbdaa898f7ae11fdf7`
5. Guarda y Render reiniciará automáticamente

#### Frontend (Variables de entorno o .env):
```env
REACT_APP_FIREBASE_API_KEY=tu-api-key
REACT_APP_FIREBASE_AUTH_DOMAIN=tu-auth-domain
REACT_APP_FIREBASE_PROJECT_ID=tu-project-id
REACT_APP_FIREBASE_STORAGE_BUCKET=tu-storage-bucket
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=tu-sender-id
REACT_APP_FIREBASE_APP_ID=tu-app-id
REACT_APP_FIREBASE_VAPID_KEY=tu-vapid-key
```

### Paso 3: Instalar Dependencias

```bash
cd frontend
npm install firebase
```

### Paso 4: Configurar Archivos

1. **Actualizar `src/firebase.js`**: Reemplaza los valores con tu configuración de Firebase
2. **Actualizar `public/firebase-messaging-sw.js`**: Reemplaza los valores con tu configuración
3. **Aplicar migración en backend**:
   ```bash
   cd backend
   python manage.py makemigrations inventario
   python manage.py migrate inventario
   ```

### Paso 5: Desplegar

1. Desplegar backend con la variable `FIREBASE_SERVER_KEY`
2. Desplegar frontend con las variables de entorno de Firebase
3. ¡Listo!

## 📱 Uso

1. El usuario abre la app en el celular (navegador)
2. La app solicitará permiso para notificaciones (solo la primera vez)
3. El usuario acepta las notificaciones
4. Recibirá notificaciones automáticamente cuando se haga una venta en su tienda
5. Las notificaciones funcionan incluso con la app cerrada (en segundo plano)

## 🔧 Instalación en el Celular (PWA)

### Android (Chrome):
1. Abre la app en Chrome
2. Menú (3 puntos) → "Agregar a pantalla de inicio"
3. La app se instalará como PWA
4. Abre la app desde el ícono en la pantalla de inicio

### iOS (Safari):
1. Abre la app en Safari
2. Compartir → "Agregar a pantalla de inicio"
3. La app se instalará como PWA
4. Abre la app desde el ícono en la pantalla de inicio

## ⚙️ Cómo Funciona

1. **Registro de Token**: Cuando el usuario inicia sesión, se solicita permiso y se registra su token FCM
2. **Creación de Venta**: Cuando se crea una venta, el backend busca todos los tokens de usuarios de esa tienda
3. **Envío de Notificación**: Se envía una notificación push a través de Firebase
4. **Recepción**: El usuario recibe la notificación en su celular, incluso si la app está cerrada

## 🎨 Personalización

Puedes personalizar:
- Título de la notificación
- Mensaje
- Icono
- Sonido
- Acciones (botones en la notificación)

## 📊 Monitoreo

Firebase Console te permite ver:
- Notificaciones enviadas
- Notificaciones entregadas
- Errores

## 🔒 Seguridad

- Los tokens FCM están asociados a usuarios autenticados
- Solo se envían notificaciones a usuarios de la misma tienda
- Los tokens se eliminan automáticamente al cerrar sesión
