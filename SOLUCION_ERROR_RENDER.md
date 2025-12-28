# 🔧 Solución al Error de Deployment en Render

## ❌ Error Encontrado

```
ERROR: Cannot find command 'git' - do you have 'git' installed and in your PATH?
```

## ✅ Solución Aplicada

Se agregó `git` a las dependencias del sistema en el `Dockerfile`. El archivo ya está actualizado.

## 📝 Cambio Realizado

En `backend/Dockerfile`, se agregó `git` a la instalación de paquetes:

```dockerfile
RUN apt-get update && apt-get install -y \
    dos2unix \
    postgresql-client \
    build-essential \
    libjpeg-dev zlib1g-dev \
    git \                    # ← AGREGADO
    && rm -rf /var/lib/apt/lists/*
```

## 🚀 Próximos Pasos

1. **Commit y push del cambio:**
   ```bash
   git add backend/Dockerfile
   git commit -m "fix: Agregar git al Dockerfile para instalar pyafipws desde GitHub"
   git push origin main
   ```

2. **Render detectará el cambio automáticamente** y volverá a hacer el build.

3. **Verifica que el build funcione** en el Dashboard de Render.

## ✅ Verificación

Después del nuevo deployment, verifica que:
- El build se complete sin errores
- El servicio se inicie correctamente
- Las migraciones se apliquen automáticamente (están en `start.sh`)

## 📚 Archivos Modificados

- `backend/Dockerfile` - Agregado `git` a las dependencias

