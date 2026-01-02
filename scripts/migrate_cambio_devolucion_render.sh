#!/bin/bash
# Script para aplicar la migración de CambioDevolucion en Render
# Ejecutar en el Shell de Render del servicio backend

echo "🚀 Iniciando migración de CambioDevolucion y DetalleCambioDevolucion..."

# Aplicar la migración
python manage.py migrate inventario 0013_cambiodevolucion_detallecambiodevolucion

# Verificar que la migración se aplicó correctamente
if [ $? -eq 0 ]; then
    echo "✅ Migración aplicada exitosamente"
    python manage.py showmigrations inventario | grep 0013
else
    echo "❌ Error al aplicar la migración"
    exit 1
fi

echo "✅ Proceso completado"

