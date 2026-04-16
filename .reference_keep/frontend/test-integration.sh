#!/bin/bash
# Script de teste para integração com API
# Valida se frontend consegue se comunicar com backend

set -e

echo "================================================"
echo "🧪 AGUADA - Teste de Integração Frontend/Backend"
echo "================================================"
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configurações
BACKEND_URL="http://192.168.0.100:3000"
BACKEND_API="${BACKEND_URL}/api"

echo "📡 Testando conectividade com backend..."
echo "URL: ${BACKEND_URL}"
echo ""

# Teste 1: Health check
echo "1️⃣  Teste: GET /api/health"
if curl -s -f "${BACKEND_API}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend online${NC}"
    HEALTH_RESPONSE=$(curl -s "${BACKEND_API}/health")
    echo "   Response: ${HEALTH_RESPONSE}"
else
    echo -e "${RED}❌ Backend offline ou inacessível${NC}"
    echo ""
    echo "Verifique se o backend está rodando:"
    echo "  cd backend && npm start"
    exit 1
fi
echo ""

# Teste 2: Latest readings
echo "2️⃣  Teste: GET /api/readings/latest"
LATEST_RESPONSE=$(curl -s "${BACKEND_API}/readings/latest")
if echo "${LATEST_RESPONSE}" | grep -q "success"; then
    echo -e "${GREEN}✅ Endpoint de leituras funcionando${NC}"
    echo "   Sensores retornados: $(echo "${LATEST_RESPONSE}" | grep -o "sensor_id" | wc -l)"
else
    echo -e "${YELLOW}⚠️  Endpoint retornou resposta inesperada${NC}"
    echo "   Response: ${LATEST_RESPONSE}"
fi
echo ""

# Teste 3: Sensors status
echo "3️⃣  Teste: GET /api/sensors/status"
STATUS_RESPONSE=$(curl -s "${BACKEND_API}/sensors/status")
if echo "${STATUS_RESPONSE}" | grep -q "success"; then
    echo -e "${GREEN}✅ Endpoint de status funcionando${NC}"
else
    echo -e "${YELLOW}⚠️  Endpoint retornou resposta inesperada${NC}"
fi
echo ""

# Teste 4: System health
echo "4️⃣  Teste: GET /api/system/health"
SYSTEM_HEALTH=$(curl -s "${BACKEND_API}/system/health")
if echo "${SYSTEM_HEALTH}" | grep -q "status"; then
    echo -e "${GREEN}✅ System health funcionando${NC}"
    echo "   Response: ${SYSTEM_HEALTH}"
else
    echo -e "${YELLOW}⚠️  System health não disponível${NC}"
fi
echo ""

# Teste 5: WebSocket (apenas verificar porta)
echo "5️⃣  Teste: WebSocket (porta 3000)"
if nc -z 192.168.0.100 3000 2>/dev/null; then
    echo -e "${GREEN}✅ Porta WebSocket acessível${NC}"
else
    echo -e "${YELLOW}⚠️  Porta WebSocket não acessível (pode estar OK se backend não implementou)${NC}"
fi
echo ""

# Teste 6: Verificar CORS
echo "6️⃣  Teste: CORS Headers"
CORS_HEADERS=$(curl -s -I "${BACKEND_API}/health" | grep -i "access-control")
if [ -n "$CORS_HEADERS" ]; then
    echo -e "${GREEN}✅ CORS configurado${NC}"
    echo "${CORS_HEADERS}"
else
    echo -e "${YELLOW}⚠️  CORS headers não encontrados${NC}"
    echo "   Certifique-se de que backend permite origem do frontend"
fi
echo ""

# Teste 7: Verificar arquivos frontend
echo "7️⃣  Teste: Arquivos Frontend"
FILES=(
    "frontend/assets/api-service.js"
    "frontend/assets/ui-utils.js"
    "frontend/assets/loading-states.css"
    "frontend/index.html"
    "frontend/mapa.html"
    "frontend/painel.html"
)

ALL_FILES_OK=true
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅${NC} ${file}"
    else
        echo -e "${RED}❌${NC} ${file} (não encontrado)"
        ALL_FILES_OK=false
    fi
done
echo ""

# Teste 8: Validar JSON dos configs
echo "8️⃣  Teste: Arquivos de Configuração"
CONFIG_FILES=(
    "config/reservoirs.json"
    "config/sensors.json"
)

for file in "${CONFIG_FILES[@]}"; do
    if [ -f "$file" ]; then
        if python3 -m json.tool "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}✅${NC} ${file} (JSON válido)"
        else
            echo -e "${RED}❌${NC} ${file} (JSON inválido)"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  ${file} (não encontrado)"
    fi
done
echo ""

# Resumo
echo "================================================"
echo "📊 RESUMO DOS TESTES"
echo "================================================"

if [ "$ALL_FILES_OK" = true ]; then
    echo -e "${GREEN}✅ Todos os arquivos frontend presentes${NC}"
else
    echo -e "${RED}❌ Alguns arquivos frontend estão faltando${NC}"
fi

echo ""
echo "🚀 Próximos passos:"
echo "   1. Iniciar backend:  cd backend && npm start"
echo "   2. Iniciar frontend: cd frontend && python3 -m http.server 8080"
echo "   3. Acessar:          http://localhost:8080/index.html"
echo ""
echo "📝 Logs importantes:"
echo "   - Backend:  backend/logs/"
echo "   - Frontend: Console do navegador (F12)"
echo ""
echo "================================================"
