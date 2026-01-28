#!/bin/bash

# Script para probar operaciones con Mercado Libre después de autenticación
# Uso: ./scripts/test_ml_api.sh [usuario] [password] [tienda_id]

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BASE_URL="http://localhost:8000"
TIENDA_ID="${3:-31551735-b173-4831-9c4a-3b8d5196dbd5}"

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Uso: $0 [usuario] [password] [tienda_id]"
    exit 1
fi

USERNAME="$1"
PASSWORD="$2"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Prueba de Operaciones Mercado Libre${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Obtener token
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/token/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access":"[^"]*' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}❌ Error al obtener token${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Token obtenido${NC}"
echo ""

# 1. Verificar estado
echo -e "${BLUE}Paso 1: Verificando estado de la integración...${NC}"
STATUS_RESPONSE=$(curl -s "$BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/status/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

AUTHENTICATED=$(echo "$STATUS_RESPONSE" | grep -o '"authenticated":[^,}]*' | cut -d':' -f2)
USER_ID=$(echo "$STATUS_RESPONSE" | grep -o '"user_id":"[^"]*' | cut -d'"' -f4)

if [ "$AUTHENTICATED" == "true" ]; then
    echo -e "${GREEN}✅ Autenticado correctamente${NC}"
    echo "   User ID: $USER_ID"
else
    echo -e "${YELLOW}⚠️  No está autenticado. Debes completar el flujo OAuth primero.${NC}"
    exit 1
fi
echo ""

# Mostrar próximos pasos
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ INTEGRACIÓN EXITOSA${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "La integración con Mercado Libre está funcionando correctamente."
echo ""
echo "📋 Próximos pasos:"
echo ""
echo "1. ${YELLOW}Sincronizar productos:${NC}"
echo "   - Implementar mapeo de categorías entre Total Stock y Mercado Libre"
echo "   - Crear lógica para publicar productos desde Total Stock a ML"
echo "   - Sincronizar cambios de stock automáticamente"
echo ""
echo "2. ${YELLOW}Recibir órdenes de Mercado Libre:${NC}"
echo "   - Implementar webhooks para recibir notificaciones de ML"
echo "   - Crear ventas automáticamente cuando se venda en ML"
echo "   - Actualizar stock cuando se complete una venta en ML"
echo ""
echo "3. ${YELLOW}Interfaz Frontend:${NC}"
echo "   - Crear componente React para gestionar la integración"
echo "   - Mostrar estado de sincronización"
echo "   - Permitir sincronización manual de productos"
echo ""
echo "4. ${YELLOW}Funcionalidades avanzadas:${NC}"
echo "   - Sincronización bidireccional completa"
echo "   - Gestión de atributos específicos de ML (variaciones, imágenes, etc.)"
echo "   - Reportes de ventas desde Mercado Libre"
echo ""
echo "Para probar operaciones específicas, puedes usar:"
echo "  - POST /api/tiendas/$TIENDA_ID/mercadolibre/sync-products/"
echo ""
echo "O consultar la documentación en:"
echo "  backend/INTEGRACION_MERCADO_LIBRE.md"
echo ""
