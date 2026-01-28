# 🔧 Solución: Webhook con ngrok

El error que estás viendo (`The endpoint abc123.ngrok.io is offline`) significa que **ngrok no está corriendo** o estás usando una URL de ejemplo.

## 🚀 Pasos para Solucionarlo

### Paso 1: Iniciar ngrok

**Opción A: Usando el script (Recomendado)**

```bash
cd backend
./scripts/iniciar_ngrok.sh
```

**Opción B: Manualmente**

En una **nueva terminal** (deja el servidor Django corriendo en otra):

```bash
ngrok http 8000
```

### Paso 2: Obtener la URL Real de ngrok

Cuando inicies ngrok, verás algo como:

```
Session Status                online
Account                       Tu Cuenta (Plan: Free)
Version                       3.x.x
Region                        United States (us)
Latency                       -
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://abc123def456.ngrok.io -> http://localhost:8000
```

**Copia la URL HTTPS** (la que dice `Forwarding`):
```
https://abc123def456.ngrok.io
```

⚠️ **IMPORTANTE**: Esta URL es única y cambia cada vez que reinicias ngrok (a menos que tengas cuenta de pago con URL fija).

### Paso 3: Construir la URL del Webhook

Tu URL del webhook será:

```
https://abc123def456.ngrok.io/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

**Reemplaza:**
- `abc123def456.ngrok.io` → Tu URL real de ngrok
- `31551735-b173-4831-9c4a-3b8d5196dbd5` → Tu ID de tienda (ya lo tienes)

### Paso 4: Verificar que Funciona

**Opción A: Usando el script**

```bash
cd backend
./scripts/verificar_webhook.sh https://TU-URL-NGROK/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

**Opción B: Manualmente con curl**

```bash
# Probar GET (validación de Mercado Libre)
curl https://TU-URL-NGROK/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/

# Deberías ver:
# {"status":"ok","message":"Webhook configurado correctamente","tienda_id":"31551735-b173-4831-9c4a-3b8d5196dbd5"}
```

### Paso 5: Configurar en Mercado Libre

Una vez que el GET responda correctamente:

1. Ve a [Mercado Libre Developers](https://developers.mercadolibre.com.ar/)
2. Selecciona tu aplicación
3. Ve a "Webhooks" o "Notificaciones"
4. Ingresa la URL completa:
   ```
   https://TU-URL-NGROK/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
   ```
5. Selecciona el topic: `orders`
6. Guarda

## ⚠️ Consideraciones Importantes

### 1. ngrok debe estar corriendo siempre

- **Mientras desarrollas**: Mantén ngrok corriendo en una terminal
- **Si cierras ngrok**: La URL cambiará y tendrás que actualizar la configuración en Mercado Libre

### 2. URL de ngrok cambia

- **Cuenta gratuita**: La URL cambia cada vez que reinicias ngrok
- **Cuenta de pago**: Puedes tener una URL fija (útil para desarrollo)

### 3. Para producción

Cuando despliegues a producción, usa la URL de tu servidor real (no ngrok):
```
https://totalstock.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

## 🔍 Verificar que Todo Funciona

### Checklist:

- [ ] Servidor Django corriendo en `localhost:8000`
- [ ] ngrok corriendo y exponiendo el puerto 8000
- [ ] URL de ngrok obtenida (ej: `https://abc123def456.ngrok.io`)
- [ ] URL del webhook construida correctamente
- [ ] GET al webhook responde con `{"status":"ok"}`
- [ ] Configurado en Mercado Libre Developers

## 🐛 Troubleshooting

### Error: "ngrok: command not found"

**Solución**: Instala ngrok
```bash
brew install ngrok
```

### Error: "The endpoint is offline"

**Causas posibles:**
1. ngrok no está corriendo → Inicia ngrok
2. URL incorrecta → Usa la URL real que te da ngrok
3. Servidor Django no está corriendo → Inicia el servidor

### Error: "Connection refused"

**Solución**: Asegúrate de que el servidor Django esté corriendo en el puerto 8000

### La URL de ngrok cambió

**Solución**: 
1. Obtén la nueva URL de ngrok
2. Actualiza la configuración en Mercado Libre Developers

## 💡 Tip: Ver el tráfico en ngrok

Mientras ngrok está corriendo, puedes ver todas las peticiones en:
```
http://127.0.0.1:4040
```

Esto te permite:
- Ver todas las peticiones que llegan
- Inspeccionar headers y body
- Ver las respuestas del servidor

## 📝 Resumen Rápido

```bash
# Terminal 1: Servidor Django
cd backend
python manage.py runserver

# Terminal 2: ngrok
ngrok http 8000

# Terminal 3: Verificar webhook
cd backend
./scripts/verificar_webhook.sh https://TU-URL-NGROK/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```
