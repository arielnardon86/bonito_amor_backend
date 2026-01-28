#!/bin/bash

# Script para iniciar ngrok y obtener la URL del webhook

echo "🚀 Iniciando ngrok para exponer el servidor Django"
echo "=================================================="
echo ""

# Verificar que ngrok esté instalado
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok no está instalado"
    echo ""
    echo "Instálalo con:"
    echo "  brew install ngrok"
    echo ""
    echo "O descárgalo desde: https://ngrok.com/download"
    exit 1
fi

# Verificar que el servidor Django esté corriendo
echo "🔍 Verificando que el servidor Django esté corriendo en localhost:8000..."
if curl -s http://localhost:8000/api/tiendas/ > /dev/null 2>&1; then
    echo "✅ Servidor Django está corriendo"
else
    echo "❌ Servidor Django no está corriendo"
    echo ""
    echo "Inicia el servidor en otra terminal con:"
    echo "  cd backend"
    echo "  python manage.py runserver"
    echo ""
    read -p "¿Quieres continuar de todas formas? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        exit 1
    fi
fi

echo ""
echo "🚀 Iniciando ngrok..."
echo ""
echo "⚠️  IMPORTANTE:"
echo "   1. Mantén esta terminal abierta mientras uses ngrok"
echo "   2. Copia la URL HTTPS que aparece (ej: https://abc123.ngrok.io)"
echo "   3. Úsala para configurar el webhook en Mercado Libre"
echo ""
echo "=================================================="
echo ""

# Iniciar ngrok
ngrok http 8000
