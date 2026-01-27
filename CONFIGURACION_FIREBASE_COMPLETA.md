# ✅ Configuración de Firebase - COMPLETA

## 🎉 Estado: Listo para desplegar

Todas las keys de Firebase están configuradas. Solo falta agregar la variable de entorno en Render.

## ✅ Keys Configuradas

### Frontend
- ✅ **VAPID Key:** Configurada en `frontend/src/firebase.js`
- ✅ **Firebase Config:** Completamente configurada

### Backend
- ✅ **Server Key:** Obtenida (`697ddca3b1428809d31f4bbbdaa898f7ae11fdf7`)
- ⚠️ **PENDIENTE:** Agregar como variable de entorno en Render

## 🔧 Último Paso: Agregar Server Key en Render

### Pasos:

1. **Ve a Render Dashboard:**
   - https://dashboard.render.com/
   - Inicia sesión

2. **Selecciona tu servicio backend:**
   - Busca el servicio de "bonito-amor-backend" o similar

3. **Ve a Environment:**
   - En el menú lateral, haz clic en **"Environment"**

4. **Agrega la variable:**
   - Haz clic en **"Add Environment Variable"**
   - **Key:** `FIREBASE_SERVER_KEY`
   - **Value:** `697ddca3b1428809d31f4bbbdaa898f7ae11fdf7`
   - Haz clic en **"Save Changes"**

5. **Render reiniciará automáticamente:**
   - El servicio se reiniciará con la nueva variable
   - Espera a que termine el despliegue

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
