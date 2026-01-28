#!/bin/bash

# Script para verificar que el webhook está accesible y funcionando

echo "🔍 Verificando Webhook de Mercado Libre"
echo "========================================"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Solicitar URL del webhook
if [ -z "$1" ]; then
    echo -e "${YELLOW}Ingresa la URL completa del webhook:${NC}"
    echo "Ejemplo: https://abc123.ngrok.io/api/tiendas/31551735-b173-4831-9c4a-3b8d5196dbd5/mercadolibre/webhook/"
    read -p "URL: " WEBHOOK_URL
else
    WEBHOOK_URL="$1"
fi

echo ""
echo -e "${BLUE}URL a verificar: ${WEBHOOK_URL}${NC}"
echo ""

# Verificar que la URL sea HTTPS
if [[ ! "$WEBHOOK_URL" =~ ^https:// ]]; then
    echo -e "${RED}❌ ERROR: La URL debe ser HTTPS${NC}"
    echo "   Mercado Libre requiere HTTPS para los webhooks"
    exit 1
fi

# Probar GET (validación de Mercado Libre)
echo -e "${YELLOW}1. Probando GET (validación de Mercado Libre)...${NC}"
GET_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${WEBHOOK_URL}")
GET_HTTP_CODE=$(echo "$GET_RESPONSE" | tail -n1)
GET_BODY=$(echo "$GET_RESPONSE" | sed '$d')

if [ "$GET_HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ GET respondió correctamente (HTTP 200)${NC}"
    echo "   Respuesta:"
    echo "$GET_BODY" | python3 -m json.tool 2>/dev/null || echo "   $GET_BODY"
else
    echo -e "${RED}❌ GET falló (HTTP ${GET_HTTP_CODE})${NC}"
    echo "   Respuesta:"
    echo "$GET_BODY"
    echo ""
    echo "   Posibles causas:"
    echo "   - El servidor no está corriendo"
    echo "   - La URL es incorrecta"
    echo "   - El endpoint requiere autenticación"
fi

echo ""

# Probar POST (notificación real)
echo -e "${YELLOW}2. Probando POST (notificación de prueba)...${NC}"
POST_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "/orders/123456789",
    "topic": "orders"
  }')
POST_HTTP_CODE=$(echo "$POST_RESPONSE" | tail -n1)
POST_BODY=$(echo "$POST_RESPONSE" | sed '$d')

if [ "$POST_HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ POST respondió correctamente (HTTP 200)${NC}"
    echo "   Respuesta:"
    echo "$POST_BODY" | python3 -m json.tool 2>/dev/null || echo "   $POST_BODY"
else
    echo -e "${RED}❌ POST falló (HTTP ${POST_HTTP_CODE})${NC}"
    echo "   Respuesta:"
    echo "$POST_BODY"
fi

echo ""
echo "========================================"
echo ""

# Resumen
if [ "$GET_HTTP_CODE" = "200" ] && [ "$POST_HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Webhook configurado correctamente${NC}"
    echo ""
    echo "Próximos pasos:"
    echo "1. Copia esta URL y úsala en Mercado Libre Developers"
    echo "2. Mercado Libre validará el webhook automáticamente"
    echo "3. Cuando haya una venta, recibirás notificaciones en este endpoint"
else
    echo -e "${RED}❌ El webhook tiene problemas${NC}"
    echo ""
    echo "Verifica:"
    echo "1. Que el servidor Django esté corriendo"
    echo "2. Que ngrok esté activo (si usas ngrok)"
    echo "3. Que la URL sea exactamente correcta"
    echo "4. Revisa los logs del servidor Django"
fi

echo ""
