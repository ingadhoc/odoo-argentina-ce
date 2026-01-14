#!/bin/bash
##############################################################################
# Script de verificación de la migración zeep
# Valida que los cambios implementados sean correctos
##############################################################################

set -e  # Exit on error

echo "🔍 Verificando migración zeep..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# 1. Verificar sintaxis Python
echo "1️⃣  Verificando sintaxis Python..."
if python3 -m py_compile l10n_ar_afipws/models/afipws_connection.py 2>/dev/null; then
    echo -e "${GREEN}✅ l10n_ar_afipws/models/afipws_connection.py - Sintaxis OK${NC}"
else
    echo -e "${RED}❌ l10n_ar_afipws/models/afipws_connection.py - Error de sintaxis${NC}"
    ((ERRORS++))
fi

if python3 -m py_compile l10n_ar_afipws_fe/models/afipws_connection.py 2>/dev/null; then
    echo -e "${GREEN}✅ l10n_ar_afipws_fe/models/afipws_connection.py - Sintaxis OK${NC}"
else
    echo -e "${RED}❌ l10n_ar_afipws_fe/models/afipws_connection.py - Error de sintaxis${NC}"
    ((ERRORS++))
fi

if python3 -m py_compile l10n_ar_afipws_fe/tests/test_connection_zeep.py 2>/dev/null; then
    echo -e "${GREEN}✅ l10n_ar_afipws_fe/tests/test_connection_zeep.py - Sintaxis OK${NC}"
else
    echo -e "${RED}❌ l10n_ar_afipws_fe/tests/test_connection_zeep.py - Error de sintaxis${NC}"
    ((ERRORS++))
fi

echo ""

# 2. Verificar imports de zeep
echo "2️⃣  Verificando imports de zeep..."
if python3 -c "from zeep import Client; from zeep.transports import Transport; from requests import Session" 2>/dev/null; then
    echo -e "${GREEN}✅ Dependencias zeep disponibles${NC}"
else
    echo -e "${YELLOW}⚠️  Dependencias zeep no instaladas${NC}"
    echo "   Ejecuta: pip install -r requirements.txt"
    ((WARNINGS++))
fi

echo ""

# 3. Verificar que se agregaron los métodos helper
echo "3️⃣  Verificando métodos helper en módulo base..."

if grep -q "_get_zeep_client" l10n_ar_afipws/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Método _get_zeep_client() encontrado${NC}"
else
    echo -e "${RED}❌ Método _get_zeep_client() NO encontrado${NC}"
    ((ERRORS++))
fi

if grep -q "_get_wsdl_url" l10n_ar_afipws/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Método _get_wsdl_url() encontrado${NC}"
else
    echo -e "${RED}❌ Método _get_wsdl_url() NO encontrado${NC}"
    ((ERRORS++))
fi

echo ""

# 4. Verificar uso correcto de self.type (NO self.env_type)
echo "4️⃣  Verificando uso correcto de self.type..."

if grep -q "self\.env_type" l10n_ar_afipws_fe/models/afipws_connection.py; then
    echo -e "${RED}❌ ¡CRÍTICO! Se encontró uso de self.env_type (campo inexistente)${NC}"
    echo "   Debe usar self.type"
    ((ERRORS++))
else
    echo -e "${GREEN}✅ NO se encontró uso incorrecto de self.env_type${NC}"
fi

if grep -q "self\.type ==" l10n_ar_afipws_fe/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Se usa self.type correctamente${NC}"
else
    echo -e "${YELLOW}⚠️  No se encontró uso de self.type en extensión FE${NC}"
    ((WARNINGS++))
fi

echo ""

# 5. Verificar imports en archivos modificados
echo "5️⃣  Verificando imports agregados..."

if grep -q "from zeep import Client" l10n_ar_afipws/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Import 'Client' de zeep agregado${NC}"
else
    echo -e "${RED}❌ Falta import 'Client' de zeep${NC}"
    ((ERRORS++))
fi

if grep -q "from zeep.transports import Transport" l10n_ar_afipws/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Import 'Transport' de zeep agregado${NC}"
else
    echo -e "${RED}❌ Falta import 'Transport' de zeep${NC}"
    ((ERRORS++))
fi

if grep -q "from requests import Session" l10n_ar_afipws/models/afipws_connection.py; then
    echo -e "${GREEN}✅ Import 'Session' de requests agregado${NC}"
else
    echo -e "${RED}❌ Falta import 'Session' de requests${NC}"
    ((ERRORS++))
fi

echo ""

# 6. Verificar requirements.txt
echo "6️⃣  Verificando requirements.txt..."

if grep -q "zeep" requirements.txt; then
    echo -e "${GREEN}✅ zeep agregado a requirements.txt${NC}"
else
    echo -e "${RED}❌ zeep NO está en requirements.txt${NC}"
    ((ERRORS++))
fi

if grep -q "requests" requirements.txt; then
    echo -e "${GREEN}✅ requests agregado a requirements.txt${NC}"
else
    echo -e "${RED}❌ requests NO está en requirements.txt${NC}"
    ((ERRORS++))
fi

if grep -q "lxml" requirements.txt; then
    echo -e "${GREEN}✅ lxml agregado a requirements.txt${NC}"
else
    echo -e "${RED}❌ lxml NO está en requirements.txt${NC}"
    ((ERRORS++))
fi

echo ""

# 7. Verificar bump de versión
echo "7️⃣  Verificando bump de versión..."

FE_VERSION=$(grep '"version"' l10n_ar_afipws_fe/__manifest__.py | head -1 | cut -d'"' -f4)
if [[ "$FE_VERSION" == "19.0.1.1.0" ]]; then
    echo -e "${GREEN}✅ Versión actualizada en l10n_ar_afipws_fe: $FE_VERSION${NC}"
else
    echo -e "${YELLOW}⚠️  Versión en l10n_ar_afipws_fe: $FE_VERSION (esperada: 19.0.1.1.0)${NC}"
    ((WARNINGS++))
fi

echo ""

# 8. Verificar logging
echo "8️⃣  Verificando mejoras en logging..."

LOGGING_COUNT=$(grep -c "_logger\." l10n_ar_afipws_fe/models/afipws_connection.py || echo 0)
if [ "$LOGGING_COUNT" -ge 3 ]; then
    echo -e "${GREEN}✅ Logging mejorado (${LOGGING_COUNT} llamadas encontradas)${NC}"
else
    echo -e "${YELLOW}⚠️  Logging podría mejorarse (solo ${LOGGING_COUNT} llamadas)${NC}"
    ((WARNINGS++))
fi

echo ""

# 9. Verificar tests creados
echo "9️⃣  Verificando tests..."

if [ -f "l10n_ar_afipws_fe/tests/test_connection_zeep.py" ]; then
    echo -e "${GREEN}✅ Test test_connection_zeep.py creado${NC}"

    TEST_COUNT=$(grep -c "def test_" l10n_ar_afipws_fe/tests/test_connection_zeep.py || echo 0)
    echo -e "   Métodos de test encontrados: $TEST_COUNT"
else
    echo -e "${YELLOW}⚠️  Test test_connection_zeep.py no encontrado${NC}"
    ((WARNINGS++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Resumen
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ ¡Verificación completada exitosamente!${NC}"
    echo ""
    echo "Todos los cambios están correctos. Puedes proceder a:"
    echo "  1. Commit de los cambios"
    echo "  2. Ejecutar tests: odoo-bin --test-enable -i l10n_ar_afipws_fe"
    echo "  3. Validar en ambiente de homologación AFIP"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Verificación completada con advertencias${NC}"
    echo ""
    echo "Errores: $ERRORS"
    echo "Advertencias: $WARNINGS"
    echo ""
    echo "Los cambios son funcionales pero hay advertencias menores."
    exit 0
else
    echo -e "${RED}❌ Verificación falló${NC}"
    echo ""
    echo "Errores: $ERRORS"
    echo "Advertencias: $WARNINGS"
    echo ""
    echo "Por favor corrige los errores antes de continuar."
    exit 1
fi
