# 🔧 Configurar ngrok para Webhooks

ngrok ahora requiere autenticación. Sigue estos pasos:

## 📋 Pasos para Configurar ngrok

### Paso 1: Crear cuenta en ngrok (si no tienes una)

1. Ve a https://dashboard.ngrok.com/signup
2. Crea una cuenta gratuita (solo necesitas email)
3. Verifica tu email

### Paso 2: Obtener tu Authtoken

1. Inicia sesión en https://dashboard.ngrok.com/
2. Ve a: https://dashboard.ngrok.com/get-started/your-authtoken
3. Copia tu authtoken (algo como: `2abc123def456ghi789jkl012mno345pqr678`)

### Paso 3: Configurar el Authtoken

Ejecuta este comando (reemplaza `TU_AUTHTOKEN` con el que copiaste):

```bash
ngrok config add-authtoken TU_AUTHTOKEN
```

Ejemplo:
```bash
ngrok config add-authtoken 2abc123def456ghi789jkl012mno345pqr678
```

### Paso 4: Verificar que Funciona

```bash
ngrok http 8000
```

Deberías ver algo como:
```
Session Status                online
Account                       Tu Nombre (Plan: Free)
Version                       3.x.x
Forwarding                    https://abc123def456.ngrok.io -> http://localhost:8000
```

## ✅ Una Vez Configurado

Una vez que ngrok esté funcionando:

1. **Copia la URL HTTPS** que te muestra (ej: `https://abc123def456.ngrok.io`)

2. **Construye tu URL del webhook:**
   ```
   https://abc123def456.ngrok.io/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
   ```

3. **Verifica que funciona:**
   ```bash
   cd backend
   ./scripts/verificar_webhook.sh https://TU-URL-NGROK/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
   ```

4. **Configura en Mercado Libre** con esa URL

## 🔄 Alternativas a ngrok

Si prefieres no usar ngrok, tienes estas opciones:

### Opción 1: Usar tu servidor de producción directamente

Si ya tienes tu servidor desplegado en Render, usa esa URL directamente:

```
https://totalstock.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

**Ventajas:**
- URL fija (no cambia)
- No necesitas mantener ngrok corriendo
- Funciona 24/7

**Desventajas:**
- Necesitas desplegar los cambios primero
- No puedes probar localmente

### Opción 2: Usar localtunnel (sin autenticación)

```bash
# Instalar
npm install -g localtunnel

# Exponer puerto 8000
lt --port 8000
```

Te dará una URL como: `https://abc123.loca.lt`

### Opción 3: Usar serveo.net (sin instalación)

```bash
ssh -R 80:localhost:8000 serveo.net
```

## 💡 Recomendación

Para desarrollo local: Usa ngrok (una vez configurado, es muy fácil)
Para producción: Usa la URL de tu servidor en Render directamente
