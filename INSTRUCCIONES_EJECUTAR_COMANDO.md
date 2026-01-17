# 📋 Instrucciones para Ejecutar el Comando de Categorías

## 🎯 Opción 1: Shell de Render (Recomendado)

### Paso 1: Acceder al Dashboard
1. Ve a **https://dashboard.render.com**
2. Inicia sesión con tu cuenta

### Paso 2: Abrir tu Servicio
1. En la lista de servicios, busca **"bonito-amor-backend"** (o el nombre de tu servicio)
2. Haz clic en él

### Paso 3: Abrir el Shell
1. En la barra lateral izquierda, busca la opción **"Shell"**
2. O en la parte superior, haz clic en la pestaña **"Shell"**
3. Se abrirá una terminal en el navegador

### Paso 4: Ejecutar el Comando
En la terminal que se abrió, escribe exactamente esto:

```bash
python manage.py actualizar_categorias_ml --site_id MLA
```

Presiona **Enter** y espera.

### Paso 5: Ver el Progreso
Verás mensajes como:
```
🔄 Descargando categorías de Mercado Libre para MLA...
📥 Descargando desde: https://api.mercadolibre.com/sites/MLA/categories/all
✅ Respuesta recibida como JSON directo
📋 Estructura detectada: lista con XXXX categorías
💾 Guardando categorías en la base de datos...
```

### Paso 6: Ver el Resumen Final
Al terminar, verás algo como:
```
✅ Actualización completada
   📊 Total de categorías: 5000+
   ➕ Nuevas categorías: 5000+
   🔄 Categorías actualizadas: 0
   🍃 Categorías hoja: 2000+
```

---

## 🖥️ Opción 2: SSH (Si está habilitado)

Si Render te permite conectarte por SSH:

```bash
# Conectarte al servidor
ssh <usuario>@<servidor-render>

# Navegar al directorio
cd /app

# Ejecutar el comando
python manage.py actualizar_categorias_ml --site_id MLA
```

---

## ⚠️ Solución de Problemas

### No veo la opción "Shell" en Render

**Solución**: 
- Asegúrate de estar en la página del servicio (no en el dashboard general)
- Busca en la barra lateral izquierda o en las pestañas superiores
- Si no aparece, Render puede requerir que el servicio esté activo

### El comando no se ejecuta o da error

**Verifica**:
1. Que estás en el directorio correcto (`/app` generalmente)
2. Que Python está disponible: `python --version`
3. Que Django está instalado: `python manage.py --help`

### Error: "No module named 'inventario'"

**Solución**: Asegúrate de estar en el directorio del proyecto:
```bash
cd /app
python manage.py actualizar_categorias_ml --site_id MLA
```

### El comando se cuelga o tarda mucho

**Es normal**: El comando descarga y procesa miles de categorías. Puede tardar 5-10 minutos o más.

---

## ✅ Verificar que Funcionó

Después de ejecutar el comando:

1. **En el frontend**: Recarga la página donde seleccionas productos para sincronizar
2. **Deberías ver**: Todas las categorías disponibles en el dropdown
3. **Puedes buscar**: Escribe en el campo de búsqueda para filtrar categorías

---

## 🔄 Re-ejecutar el Comando

Si necesitas actualizar las categorías (por ejemplo, si Mercado Libre agregó nuevas):

```bash
python manage.py actualizar_categorias_ml --site_id MLA --force
```

El flag `--force` actualizará todas las categorías existentes.

---

## 📝 Notas Importantes

- ⏱️ **Tiempo**: El comando puede tardar varios minutos (hay miles de categorías)
- 🌐 **Internet**: Necesita conexión a internet para descargar desde la API de Mercado Libre
- 💾 **Base de datos**: Asegúrate de que la migración esté aplicada (debería estarlo en producción)
- 🔒 **Sin autenticación**: No necesitas tokens de Mercado Libre, usa el endpoint público
