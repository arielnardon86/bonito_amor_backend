#!/bin/bash

# Script para probar el webhook de Mercado Libre
# Uso: ./probar_webhook_ml.sh [ORDER_ID]

TIENDA_ID="e265d339-39ec-4ec5-a73c-d5a31904d29a"
BASE_URL="https://bonito-amor-backend.onrender.com"
WEBHOOK_URL="${BASE_URL}/api/tiendas/${TIENDA_ID}/mercadolibre/webhook/"

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "============================================================"
echo "  🧪 Prueba de Webhook de Mercado Libre"
echo "============================================================"
echo ""
echo "URL: ${WEBHOOK_URL}"
echo "Fecha: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Obtener ORDER_ID de argumentos si se proporciona
ORDER_ID="${1:-123456789}"

if [ "$ORDER_ID" != "123456789" ]; then
    echo -e "${BLUE}📦 ID de orden proporcionado: ${ORDER_ID}${NC}"
else
    echo -e "${YELLOW}⚠️  Usando ID de orden de ejemplo: ${ORDER_ID}${NC}"
    echo "   Para probar con una orden real, proporciona el ID como argumento:"
    echo "   ./probar_webhook_ml.sh <ORDER_ID>"
fi

echo ""
echo "============================================================"
echo "  1. Probando GET (Validación de Mercado Libre)"
echo "============================================================"
echo ""

GET_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X GET "${WEBHOOK_URL}" 2>&1)
GET_HTTP_CODE=$(echo "$GET_RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
GET_BODY=$(echo "$GET_RESPONSE" | sed 's/HTTP_CODE:[0-9]*$//')

echo "Status Code: ${GET_HTTP_CODE}"
echo ""
echo "Respuesta:"
echo "$GET_BODY" | python3 -m json.tool 2>/dev/null || echo "$GET_BODY"

if [ "$GET_HTTP_CODE" = "200" ]; then
    echo ""
    echo -e "${GREEN}✅ GET exitoso - El endpoint está configurado correctamente${NC}"
    GET_SUCCESS=true
else
    echo ""
    echo -e "${RED}⚠️  GET devolvió código ${GET_HTTP_CODE}${NC}"
    GET_SUCCESS=false
fi

echo ""
echo "============================================================"
echo "  2. Probando POST (Notificación de Mercado Libre)"
echo "============================================================"
echo ""

# Payload JSON
PAYLOAD=$(cat <<EOF
{
  "resource": "/orders/${ORDER_ID}",
  "topic": "orders"
}
EOF
)

echo "Payload enviado:"
echo "$PAYLOAD" | python3 -m json.tool 2>/dev/null || echo "$PAYLOAD"
echo ""

POST_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "${WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --max-time 30 2>&1)

POST_HTTP_CODE=$(echo "$POST_RESPONSE" | grep -o "HTTP_CODE:[0-9]*" | cut -d: -f2)
POST_BODY=$(echo "$POST_RESPONSE" | sed 's/HTTP_CODE:[0-9]*$//')

echo "Status Code: ${POST_HTTP_CODE}"
echo ""
echo "Respuesta:"
echo "$POST_BODY" | python3 -m json.tool 2>/dev/null || echo "$POST_BODY"

if [ "$POST_HTTP_CODE" = "200" ]; then
    echo ""
    echo -e "${GREEN}✅ POST exitoso - La notificación fue procesada${NC}"
    
    # Verificar el status en la respuesta
    if echo "$POST_BODY" | grep -q '"status":"success"'; then
        echo -e "${GREEN}✅ La orden fue procesada correctamente${NC}"
    elif echo "$POST_BODY" | grep -q '"status":"error"'; then
        echo -e "${YELLOW}⚠️  Hubo un error al procesar la orden${NC}"
    elif echo "$POST_BODY" | grep -q '"status":"skipped"'; then
        echo -e "${BLUE}ℹ️  La orden fue omitida (puede ser que no esté en estado válido)${NC}"
    fi
    POST_SUCCESS=true
else
    echo ""
    echo -e "${RED}⚠️  POST devolvió código ${POST_HTTP_CODE}${NC}"
    POST_SUCCESS=false
fi

echo ""
echo "============================================================"
echo "  📊 Resumen"
echo "============================================================"
echo ""

if [ "$GET_SUCCESS" = true ]; then
    echo -e "GET (Validación):  ${GREEN}✅ Exitoso${NC}"
else
    echo -e "GET (Validación):  ${RED}❌ Falló${NC}"
fi

if [ "$POST_SUCCESS" = true ]; then
    echo -e "POST (Notificación): ${GREEN}✅ Exitoso${NC}"
else
    echo -e "POST (Notificación): ${RED}❌ Falló${NC}"
fi

echo ""
if [ "$GET_SUCCESS" = true ] && [ "$POST_SUCCESS" = true ]; then
    echo -e "${GREEN}✅ Todas las pruebas pasaron correctamente${NC}"
elif [ "$GET_SUCCESS" = true ]; then
    echo -e "${YELLOW}⚠️  GET funciona, pero POST puede tener problemas${NC}"
    echo "   Revisa los logs del servidor para más detalles"
else
    echo -e "${RED}❌ El endpoint no está respondiendo correctamente${NC}"
    echo "   Verifica que:"
    echo "   1. El servidor esté corriendo"
    echo "   2. La URL sea correcta"
    echo "   3. El ID de tienda sea válido"
fi

echo ""
echo "============================================================"
echo "  💡 Información Adicional"
echo "============================================================"
echo ""
echo "Para ver los logs del servidor en Render:"
echo "  1. Ve a tu dashboard de Render"
echo "  2. Selecciona tu servicio"
echo "  3. Ve a la pestaña 'Logs'"
echo ""
echo "Para probar con una orden real de Mercado Libre:"
echo "  1. Obtén el ID de una orden real desde tu cuenta de ML"
echo "  2. Ejecuta: ./probar_webhook_ml.sh <ORDER_ID_REAL>"
echo ""
echo "Comandos curl manuales:"
echo ""
echo "GET:"
echo "  curl -X GET \"${WEBHOOK_URL}\""
echo ""
echo "POST:"
echo "  curl -X POST \"${WEBHOOK_URL}\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"resource\": \"/orders/${ORDER_ID}\", \"topic\": \"orders\"}'"
echo ""
