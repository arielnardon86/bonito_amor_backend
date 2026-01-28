# ✅ Configuración de Firebase - COMPLETA

## 🎉 Estado: Listo para desplegar

Todas las keys de Firebase están configuradas. Solo falta agregar la variable de entorno en Render.

## ✅ Keys Configuradas

### Frontend
- ✅ **VAPID Key:** Configurada en `frontend/src/firebase.js`
- ✅ **Firebase Config:** Completamente configurada

### Backend
- **Opción recomendada (Safari PWA / Web):** Cuenta de servicio JSON → FCM HTTP v1
- **Opción legacy (solo Chrome/Android):** Server Key en `FIREBASE_SERVER_KEY`

## 🔧 Notificaciones en Safari PWA (y todos los navegadores)

Para que las notificaciones lleguen en **Safari (iOS/macOS)** y en todos los navegadores web, el backend debe usar **FCM HTTP v1** con una **cuenta de servicio** de Firebase (la Server Key legacy no es fiable para Safari/Web).

### 1. Obtener la cuenta de servicio (Firebase)

1. Ve a [Firebase Console](https://console.firebase.google.com/) → tu proyecto (ej. total-stock).
2. **Configuración del proyecto** (engranaje) → pestaña **Cuentas de servicio**.
3. En **Firebase Admin SDK**, clic en **Generar nueva clave privada** → Descargar el JSON.
4. Guarda el archivo en un lugar seguro (no lo subas a Git).

### 2. Configurar en el backend (Render u otro host)

**Opción A – Ruta al archivo (si el host tiene disco):**

- Sube el JSON a un path que el backend pueda leer y agrega la variable:
  - **Key:** `FIREBASE_SERVICE_ACCOUNT_PATH`
  - **Value:** ruta absoluta al JSON (ej. `/etc/secrets/firebase-service-account.json`)

**Opción B – Contenido en variable de entorno (recomendado en Render):**

1. Abre el JSON descargado y copia **todo** el contenido (un solo objeto JSON).
2. En Render → tu servicio backend → **Environment**.
3. Agrega una variable:
   - **Key:** `FIREBASE_SERVICE_ACCOUNT_JSON`
   - **Value:** pega el contenido completo del JSON (Render acepta valores multilínea).
4. Guarda. El backend usará FCM v1 y las notificaciones funcionarán también en Safari PWA.

Si **no** defines ninguna de las dos variables anteriores, el backend usará la API legacy con `FIREBASE_SERVER_KEY` (puede no llegar a Safari/Web).

## ✅ Verificación

Una vez agregada la variable en Render:

1. ✅ Backend configurado con Server Key
2. ✅ Frontend configurado con VAPID Key
3. ✅ Service Worker configurado
4. ✅ Código de notificaciones implementado

## 🚀 Próximos Pasos

1. **Aplicar migración en backend:**
   ```bash
   cd backend
   python manage.py migrate inventario
   ```

2. **Desplegar frontend:**
   - El frontend ya tiene todo configurado
   - Solo necesita desplegarse

3. **Probar notificaciones:**
   - Abre la app en el celular
   - Inicia sesión
   - Acepta el permiso de notificaciones
   - Haz una venta de prueba
   - Deberías recibir una notificación

## 📱 Instalación PWA en el Celular

### Android (Chrome):
1. Abre la app en Chrome
2. Menú (3 puntos) → "Agregar a pantalla de inicio"
3. La app se instalará como PWA

### iOS (Safari):
1. Abre la app en Safari
2. Compartir → "Agregar a pantalla de inicio"
3. La app se instalará como PWA

## 🔍 Troubleshooting

Si las notificaciones no funcionan:

1. **Verifica el Service Worker:**
   - DevTools → Application → Service Workers
   - Debe estar registrado y activo

2. **Verifica los logs del backend:**
   - Render → Logs
   - Busca errores relacionados con FCM

3. **Verifica que el usuario tenga tienda asignada:**
   - Solo usuarios con tienda asignada recibirán notificaciones

4. **Verifica permisos:**
   - El navegador debe tener permisos de notificaciones
   - Configuración del navegador → Notificaciones → Permitir

5. **Safari PWA:**
   - Configura **FIREBASE_SERVICE_ACCOUNT_JSON** (o **FIREBASE_SERVICE_ACCOUNT_PATH**) en el backend para usar FCM v1.
   - En iOS, las notificaciones web suelen funcionar mejor con la app añadida a la pantalla de inicio (PWA).
