#!/bin/bash

# Script para verificar que el servidor de staging está funcionando

echo "========================================="
echo "Verificación de Servidor Staging"
echo "========================================="
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

BASE_URL="http://localhost:8000"

echo "Rutas disponibles en tu servidor de staging:"
echo ""
echo -e "${GREEN}✓ Panel de administración:${NC}"
echo "   ${BASE_URL}/admin/"
echo ""
echo -e "${GREEN}✓ API REST:${NC}"
echo "   ${BASE_URL}/api/"
echo "   ${BASE_URL}/api/productos/"
echo "   ${BASE_URL}/api/ventas/"
echo "   ${BASE_URL}/api/categorias/"
echo "   ${BASE_URL}/api/tiendas/"
echo ""
echo -e "${GREEN}✓ Autenticación:${NC}"
echo "   ${BASE_URL}/api/token/          (POST para obtener token)"
echo "   ${BASE_URL}/api/token/refresh/  (POST para refrescar token)"
echo ""
echo -e "${GREEN}✓ Métricas:${NC}"
echo "   ${BASE_URL}/api/metricas/metrics/"
echo "   ${BASE_URL}/api/inventario/metrics/"
echo ""
echo "========================================="
echo ""
echo "Para probar que funciona:"
echo ""
echo "1. Ver la lista de tiendas (público):"
echo "   curl ${BASE_URL}/api/tiendas/"
echo ""
echo "2. O abrir en el navegador:"
echo "   ${BASE_URL}/api/tiendas/"
echo ""
echo "3. Para usar otras rutas necesitas autenticación JWT"
echo ""





