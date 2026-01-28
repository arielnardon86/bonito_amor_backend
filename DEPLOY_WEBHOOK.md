# 🚀 Desplegar Webhook a Producción

El error 404 significa que los cambios del webhook **no están desplegados en producción**. Necesitas desplegar los cambios a Render.

## 📋 Pasos para Desplegar

### Paso 1: Verificar Cambios Locales

```bash
cd backend
git status
```

Deberías ver que `inventario/views.py` tiene cambios sin commitear.

### Paso 2: Hacer Commit de los Cambios

```bash
# Agregar los archivos modificados
git add inventario/views.py

# Hacer commit
git commit -m "feat: Agregar endpoint webhook para notificaciones de Mercado Libre

- Endpoint GET/POST para recibir notificaciones de ML
- Actualización automática de stock cuando hay ventas
- Soporte para validación de webhook (GET)
- Procesamiento de órdenes y actualización de stock"

# Subir a tu repositorio
git push origin main
# O la rama que uses: git push origin tu-rama
```

### Paso 3: Verificar Despliegue en Render

1. Ve a tu panel de Render
2. Selecciona tu servicio `bonito-amor-backend`
3. Ve a la sección "Events" o "Deploys"
4. Deberías ver un nuevo deploy iniciándose automáticamente
5. Espera a que termine (puede tardar 2-5 minutos)

### Paso 4: Verificar que Funciona

Una vez que el deploy termine, prueba la URL:

```
https://bonito-amor-backend.onrender.com/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/
```

Deberías ver:
```json
{
  "status": "ok",
  "message": "Webhook configurado correctamente",
  "tienda_id": "31551735-b173-4831-9c4a-3b8d5196dbd5"
}
```

## ⚠️ Si Render No Despliega Automáticamente

Si Render no detecta los cambios automáticamente:

1. Ve a tu servicio en Render
2. Haz clic en "Manual Deploy" → "Deploy latest commit"
3. Espera a que termine

## 🔍 Verificar que los Cambios Están Desplegados

### Opción 1: Verificar en los Logs

1. Ve a Render → Tu servicio → Logs
2. Busca mensajes de inicio del servidor
3. Verifica que no haya errores de importación

### Opción 2: Probar Otro Endpoint

Prueba un endpoint que ya exista para verificar que el servidor está funcionando:

```
https://bonito-amor-backend.onrender.com/api/tiendas/
```

Si este funciona pero el webhook no, significa que los cambios no están desplegados.

### Opción 3: Verificar Código en Producción

Si tienes acceso SSH a Render, puedes verificar:

```bash
# En el shell de Render
cd /opt/render/project/src/backend
grep -n "ml_webhook" inventario/views.py
```

Si no encuentra el método, los cambios no están desplegados.

## 📝 Checklist de Despliegue

- [ ] Cambios commiteados localmente
- [ ] Cambios pusheados al repositorio
- [ ] Render detectó los cambios (o deploy manual iniciado)
- [ ] Deploy completado sin errores
- [ ] Webhook responde correctamente (GET devuelve JSON)
- [ ] Configurado en Mercado Libre Developers

## 🐛 Troubleshooting

### Error: "No changes to commit"

**Solución**: Los cambios ya están commiteados. Solo necesitas hacer push:
```bash
git push origin main
```

### Error: "Permission denied" al hacer push

**Solución**: Verifica que tienes permisos en el repositorio o usa SSH en lugar de HTTPS.

### El deploy falla en Render

**Solución**: 
1. Revisa los logs del deploy en Render
2. Verifica que no haya errores de sintaxis
3. Asegúrate de que todas las dependencias estén en `requirements.txt`

### El webhook sigue dando 404 después del deploy

**Solución**:
1. Espera unos minutos (a veces tarda en propagarse)
2. Verifica que el deploy realmente terminó
3. Revisa los logs del servidor en Render
4. Prueba reiniciar el servicio manualmente en Render

## ✅ Una Vez Desplegado

Cuando el webhook funcione correctamente:

1. **Configura en Mercado Libre** con la URL de producción
2. **Haz una venta de prueba** para verificar que funciona
3. **Revisa los logs** para confirmar que recibiste la notificación
4. **Verifica el stock** para confirmar que se actualizó
