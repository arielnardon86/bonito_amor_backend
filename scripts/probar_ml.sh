#!/bin/bash

# Script para probar la integración con Mercado Libre
# Uso: 
#   ./scripts/probar_ml.sh [usuario] [password] [tienda_id]
#   ./scripts/probar_ml.sh exchange [usuario] [password] [tienda_id] [codigo]

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:8000"
REDIRECT_URI="https://totalstock.onrender.com/api/tiendas/mercadolibre/callback/"

# Si el primer argumento es "exchange", intercambiar código
if [ "$1" == "exchange" ]; then
    if [ -z "$5" ]; then
        echo -e "${RED}❌ Error: Falta el código de autorización${NC}"
        echo ""
        echo "Uso para intercambiar código:"
        echo "  $0 exchange [usuario] [password] [tienda_id] [codigo]"
        echo ""
        echo "Ejemplo:"
        echo "  $0 exchange admin mi_password 31551735-b173-4831-9c4a-3b8d5196dbd5 TG-XXXXX"
        exit 1
    fi
    
    USERNAME="$2"
    PASSWORD="$3"
    TIENDA_ID="$4"
    CODE="$5"
    
    # Obtener token
    TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/token/" \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")
    
    ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access":"[^"]*' | cut -d'"' -f4)
    
    if [ -z "$ACCESS_TOKEN" ]; then
        echo -e "${RED}❌ Error al obtener token${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}🔄 Intercambiando código por tokens...${NC}"
    echo ""
    
    EXCHANGE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/callback/" \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"code\":\"$CODE\",\"redirect_uri\":\"$REDIRECT_URI\"}")
    
    # Verificar si fue exitoso
    if echo "$EXCHANGE_RESPONSE" | grep -q "message"; then
        echo -e "${GREEN}✅ Autenticación exitosa!${NC}"
        echo ""
        echo "$EXCHANGE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$EXCHANGE_RESPONSE"
        echo ""
        echo -e "${BLUE}Verifica el estado con:${NC}"
        echo "  curl $BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/status/ -H \"Authorization: Bearer $ACCESS_TOKEN\""
    else
        echo -e "${RED}❌ Error al intercambiar código${NC}"
        echo "$EXCHANGE_RESPONSE"
    fi
    
    exit 0
fi

# Modo normal: obtener URL de autorización
TIENDA_ID="${3:-31551735-b173-4831-9c4a-3b8d5196dbd5}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Prueba de Integración Mercado Libre${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Paso 1: Obtener token
if [ -z "$1" ] || [ -z "$2" ]; then
    echo -e "${YELLOW}⚠️  Usuario o contraseña no proporcionados${NC}"
    echo ""
    echo "Uso para obtener URL de autorización:"
    echo "  $0 [usuario] [password] [tienda_id]"
    echo ""
    echo "Uso para intercambiar código (después de autorizar):"
    echo "  $0 exchange [usuario] [password] [tienda_id] [codigo]"
    echo ""
    echo "Ejemplo:"
    echo "  $0 admin mi_password"
    echo "  $0 exchange admin mi_password 31551735-b173-4831-9c4a-3b8d5196dbd5 TG-XXXXX"
    echo ""
    exit 1
fi

USERNAME="$1"
PASSWORD="$2"

echo -e "${BLUE}Paso 1: Obteniendo token de autenticación...${NC}"
echo ""

TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/token/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access":"[^"]*' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}❌ Error al obtener token${NC}"
    echo "Respuesta: $TOKEN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Token obtenido exitosamente${NC}"
echo ""

# Paso 2: Verificar estado
echo -e "${BLUE}Paso 2: Verificando estado de la integración...${NC}"
echo ""

STATUS_RESPONSE=$(curl -s "$BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/status/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
echo ""

# Paso 3: Obtener URL de autorización
echo -e "${BLUE}Paso 3: Obteniendo URL de autorización OAuth...${NC}"
echo ""

AUTH_URL_RESPONSE=$(curl -s "$BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/auth-url/?redirect_uri=$REDIRECT_URI" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

AUTH_URL=$(echo "$AUTH_URL_RESPONSE" | grep -o '"auth_url":"[^"]*' | cut -d'"' -f4)

if [ -z "$AUTH_URL" ]; then
    echo -e "${RED}❌ Error al obtener URL de autorización${NC}"
    echo "Respuesta: $AUTH_URL_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ URL de autorización generada${NC}"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 PASOS SIGUIENTES:${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}1. Abre esta URL en tu navegador:${NC}"
echo ""
echo -e "${YELLOW}$AUTH_URL${NC}"
echo ""
echo -e "${BLUE}2. Autoriza la aplicación con tu cuenta de Mercado Libre${NC}"
echo ""
echo -e "${BLUE}3. Después de autorizar, serás redirigido a:${NC}"
echo -e "${YELLOW}$REDIRECT_URI?code=TG-XXXXX${NC}"
echo ""
echo -e "${BLUE}4. Copia el código (TG-XXXXX) de la URL${NC}"
echo ""
echo -e "${BLUE}5. Ejecuta este comando para intercambiar el código por tokens:${NC}"
echo ""
echo -e "${CYAN}Opción A: Usando el script (más fácil):${NC}"
echo -e "${GREEN}  ./scripts/probar_ml.sh exchange $USERNAME $PASSWORD $TIENDA_ID TG-XXXXX${NC}"
echo ""
echo -e "${CYAN}Opción B: Usando curl directamente:${NC}"
echo -e "${GREEN}curl -X POST \"$BASE_URL/api/tiendas/$TIENDA_ID/mercadolibre/callback/\" \\\\${NC}"
echo -e "${GREEN}  -H \"Authorization: Bearer $ACCESS_TOKEN\" \\\\${NC}"
echo -e "${GREEN}  -H \"Content-Type: application/json\" \\\\${NC}"
echo -e "${GREEN}  -d '{\"code\":\"TG-XXXXX\",\"redirect_uri\":\"$REDIRECT_URI\"}'${NC}"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
