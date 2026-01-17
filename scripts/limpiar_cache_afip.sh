#!/bin/bash

# Script para limpiar el cache corrupto de pyafipws
# Esto soluciona el error "junk after document element" cuando pyafipws cachea HTML en lugar de XML

echo "=== Limpiando cache de pyafipws ==="

# Encontrar y eliminar archivos de cache
CACHE_DIR="$HOME/Proyectos/Bonito_Amor/backend/venv/lib/python3.13/site-packages/pyafipws/cache"

if [ -d "$CACHE_DIR" ]; then
    echo "Eliminando archivos de cache en: $CACHE_DIR"
    find "$CACHE_DIR" -name "*.xml" -type f -delete
    echo "✅ Cache limpiado"
else
    echo "⚠️ Directorio de cache no encontrado: $CACHE_DIR"
    echo "Buscando en otras ubicaciones..."
    
    # Intentar encontrar el cache en otras ubicaciones posibles
    PYAFIPWS_PATH=$(python3 -c "import pyafipws; import os; print(os.path.dirname(pyafipws.__file__))" 2>/dev/null)
    if [ -n "$PYAFIPWS_PATH" ]; then
        ALT_CACHE_DIR="$PYAFIPWS_PATH/cache"
        if [ -d "$ALT_CACHE_DIR" ]; then
            echo "Encontrado cache en: $ALT_CACHE_DIR"
            find "$ALT_CACHE_DIR" -name "*.xml" -type f -delete
            echo "✅ Cache limpiado"
        fi
    fi
fi

echo ""
echo "✅ Listo. Puedes intentar facturar nuevamente."



