#!/bin/bash

# Script para probar el webhook de Mercado Libre localmente

echo "🧪 Test de Webhook de Mercado Libre"
echo "===================================="
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Verificar si el servidor está corriendo
echo -e "${YELLOW}1. Verificando que el servidor Django esté corriendo...${NC}"
if curl -s http://localhost:8000/api/tiendas/ > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Servidor Django está corriendo${NC}"
else
    echo -e "${RED}❌ Servidor Django no está corriendo. Inicia con: python manage.py runserver${NC}"
    exit 1
fi

# Obtener ID de tienda
echo ""
echo -e "${YELLOW}2. Obteniendo ID de tienda...${NC}"
TIENDA_ID=$(curl -s http://localhost:8000/api/tiendas/ | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0]['id'] if data else '')" 2>/dev/null)

if [ -z "$TIENDA_ID" ]; then
    echo -e "${RED}❌ No se pudo obtener el ID de tienda${NC}"
    echo "   Intenta obtenerlo manualmente:"
    echo "   curl http://localhost:8000/api/tiendas/ | python3 -m json.tool"
    exit 1
fi

echo -e "${GREEN}✅ ID de tienda: ${TIENDA_ID}${NC}"

# URL del webhook
WEBHOOK_URL="http://localhost:8000/api/tiendas/${TIENDA_ID}/mercadolibre/webhook/"

echo ""
echo -e "${YELLOW}3. Probando webhook...${NC}"
echo "   URL: ${WEBHOOK_URL}"
echo ""

# Hacer petición de prueba
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }')

# Separar respuesta y código HTTP
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "Respuesta del servidor:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Webhook respondió correctamente (HTTP 200)${NC}"
    echo ""
    echo "📋 Próximos pasos:"
    echo "   1. Revisa los logs del servidor Django para ver más detalles"
    echo "   2. Si quieres probar desde internet, usa ngrok:"
    echo "      ngrok http 8000"
    echo "   3. Usa la URL de ngrok para configurar el webhook en Mercado Libre"
else
    echo -e "${RED}❌ Webhook respondió con código HTTP ${HTTP_CODE}${NC}"
    echo ""
    echo "Revisa:"
    echo "   - Que el servidor Django esté corriendo"
    echo "   - Que el ID de tienda sea correcto"
    echo "   - Los logs del servidor para ver el error"
fi

echo ""
echo "===================================="
