# Cómo Ver los Logs de Django

## 📋 Ver Logs en Tiempo Real

### Opción 1: Terminal donde está corriendo el servidor

Si iniciaste el servidor con:
```bash
cd backend
./scripts/run_staging.sh runserver
```

**Los logs aparecen directamente en esa terminal** en tiempo real.

---

### Opción 2: Si el servidor está corriendo en background

1. **Encuentra el proceso:**
   ```bash
   ps aux | grep "manage.py runserver"
   ```

2. **Mata el proceso y reinícialo en foreground:**
   ```bash
   # Matar proceso (reemplaza PID con el número del proceso)
   kill PID
   
   # Reiniciar en foreground para ver logs
   cd backend
   ./scripts/run_staging.sh runserver
   ```

---

## 🔍 Qué Buscar en los Logs

Cuando intentas facturar, deberías ver mensajes como:

```
=== Iniciando emisión de factura ===
Venta ID: ...
Tienda: ...
Tipo facturación: AFIP
Datos del cliente: ...
⚠️ Llamando a facturacion_service.emitir_factura...
=== Iniciando autenticación AFIP ===
Modo: testing
CUIT: ...
...
```

### Si hay un error, verás:

```
❌ Error al validar serializer: ...
❌ Error al autenticar con AFIP: ...
❌ Error al establecer ticket de acceso: ...
❌ Error al solicitar CAE: ...
```

---

## 📊 Niveles de Logging

Los logs incluyen diferentes niveles:

- `INFO`: Información general del flujo
- `WARNING`: Advertencias (no críticas)
- `ERROR`: Errores que impiden el funcionamiento
- `DEBUG`: Información detallada para debugging

---

## 🛠️ Activar Logging Detallado (Opcional)

Si necesitas más detalles, puedes modificar `settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',  # Cambiar a DEBUG para más detalles
    },
    'loggers': {
        'inventario': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
```

---

## 💡 Tip

**Para ver solo los errores relevantes**, busca líneas que contengan:
- `❌` (símbolo de error que agregamos)
- `ERROR`
- `Exception`
- `Traceback`

Ejemplo:
```bash
# Si guardas los logs en un archivo
./scripts/run_staging.sh runserver 2>&1 | tee django.log

# Luego buscar errores
grep -i "error\|❌\|exception" django.log
```

