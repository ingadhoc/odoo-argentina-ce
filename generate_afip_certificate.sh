#!/bin/bash
##############################################################################
# Script para generar certificado AFIP desde cero
# Uso: ./generate_afip_certificate.sh <CUIT> <ambiente>
#
# Ejemplos:
#   ./generate_afip_certificate.sh 20362952832 homologacion
#   ./generate_afip_certificate.sh 20362952832 produccion
##############################################################################

set -e  # Salir si hay error

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

# Función para imprimir con color
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Verificar argumentos
if [ $# -ne 2 ]; then
    print_error "Uso: $0 <CUIT> <ambiente>"
    echo ""
    echo "Ejemplos:"
    echo "  $0 20362952832 homologacion"
    echo "  $0 20362952832 produccion"
    exit 1
fi

CUIT=$1
AMBIENTE=$2

# Validar ambiente
if [ "$AMBIENTE" != "homologacion" ] && [ "$AMBIENTE" != "produccion" ]; then
    print_error "El ambiente debe ser 'homologacion' o 'produccion'"
    exit 1
fi

# Verificar que existe openssl
if ! command -v openssl &> /dev/null; then
    print_error "openssl no está instalado"
    echo "En macOS: brew install openssl"
    echo "En Ubuntu/Debian: sudo apt-get install openssl"
    exit 1
fi

echo ""
echo "=========================================="
echo " GENERACIÓN DE CERTIFICADO AFIP"
echo "=========================================="
echo "CUIT: $CUIT"
echo "Ambiente: $AMBIENTE"
echo "=========================================="
echo ""

# Crear directorio de salida
OUTPUT_DIR="afip_cert_${CUIT}_${AMBIENTE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

print_info "Archivos se guardarán en: $(pwd)"
echo ""

# 1. Generar clave privada
print_info "Paso 1/3: Generando clave privada RSA 2048 bits..."
openssl genrsa -out clave_privada.key 2048 2>/dev/null
if [ $? -eq 0 ]; then
    print_success "Clave privada generada: clave_privada.key"
    # Mostrar primeras líneas
    echo ""
    head -n 3 clave_privada.key
    echo "..."
else
    print_error "Error al generar clave privada"
    exit 1
fi

# 2. Generar CSR
print_info ""
print_info "Paso 2/3: Generando Certificate Signing Request (CSR)..."
echo ""

# Datos del certificado
PAIS="AR"
PROVINCIA="Buenos Aires"
CIUDAD="CABA"
ORGANIZACION="MI EMPRESA"
UNIDAD="IT"
CN="AFIP WS ${AMBIENTE}"

print_info "Datos del certificado:"
echo "  País: $PAIS"
echo "  Provincia: $PROVINCIA"
echo "  Ciudad: $CIUDAD"
echo "  Organización: $ORGANIZACION"
echo "  Unidad Organizativa: $UNIDAD"
echo "  Common Name: $CN"
echo "  Serial Number (CUIT): $CUIT"
echo ""

# Generar CSR
openssl req -new -key clave_privada.key -out solicitud.csr \
    -subj "/C=${PAIS}/ST=${PROVINCIA}/L=${CIUDAD}/O=${ORGANIZACION}/OU=${UNIDAD}/CN=${CN}/serialNumber=CUIT ${CUIT}" 2>/dev/null

if [ $? -eq 0 ]; then
    print_success "CSR generado: solicitud.csr"
    echo ""
    head -n 3 solicitud.csr
    echo "..."
else
    print_error "Error al generar CSR"
    exit 1
fi

# 3. Instrucciones para AFIP
echo ""
print_info "Paso 3/3: Instrucciones para obtener el certificado en AFIP"
echo ""
echo "=========================================="
echo " PRÓXIMOS PASOS EN AFIP"
echo "=========================================="
echo ""
echo "1️⃣  Ingrese al sitio de AFIP:"
if [ "$AMBIENTE" = "homologacion" ]; then
    echo "   🔗 https://www.afip.gob.ar/ws/WSAA/wsaa_asociar_certificado.asp"
    echo ""
    echo "2️⃣  Seleccione: 'Homologación'"
else
    echo "   🔗 https://www.afip.gob.ar/ws/WSAA/wsaa_asociar_certificado.asp"
    echo ""
    echo "2️⃣  Seleccione: 'Producción'"
fi
echo ""
echo "3️⃣  Haga clic en 'Generar Solicitud de Certificado'"
echo ""
echo "4️⃣  Suba el archivo CSR:"
echo "   📄 $(pwd)/solicitud.csr"
echo ""
echo "5️⃣  Seleccione los servicios que necesita:"
echo "   ☑️  wsfe (Factura Electrónica)"
echo "   ☑️  wsfex (Factura de Exportación)"
echo "   ☑️  wsbfe (Bono Fiscal Electrónico)"
echo "   ☑️  wsmtxca (Remitos Electrónicos)"
echo ""
echo "6️⃣  Descargue el certificado que AFIP le genera"
echo "   Guárdelo como: $(pwd)/certificado.crt"
echo ""
echo "=========================================="
echo ""

# Crear archivo de instrucciones
cat > INSTRUCCIONES.txt << EOF
CERTIFICADO AFIP - CUIT $CUIT ($AMBIENTE)
Generado: $(date)

ARCHIVOS GENERADOS:
===================
✓ clave_privada.key - Clave privada RSA (NUNCA compartir)
✓ solicitud.csr - Certificate Signing Request para AFIP

PRÓXIMOS PASOS:
===============
1. Ir a AFIP: https://www.afip.gob.ar/ws/WSAA/wsaa_asociar_certificado.asp
2. Seleccionar ambiente: $AMBIENTE
3. Subir el archivo: solicitud.csr
4. Seleccionar servicios: wsfe, wsfex, wsbfe, wsmtxca
5. Descargar el certificado y guardarlo como: certificado.crt
6. En Odoo, subir AMBOS archivos:
   - clave_privada.key (la que está aquí)
   - certificado.crt (la que descargó de AFIP)

IMPORTANTE:
===========
⚠️  La clave_privada.key es la que DEBE usar con el certificado de AFIP
⚠️  NO genere una nueva clave, use ESTA misma
⚠️  NO pierda este archivo, guárdelo en lugar seguro

VERIFICAR PAR:
==============
Una vez tenga el certificado de AFIP, verifique que corresponda:

  python3 ../verify_certificate_pair.py certificado.crt clave_privada.key

Si dice "PAR VÁLIDO", puede subir los archivos a Odoo.

DIRECTORIO: $(pwd)
EOF

print_success "Instrucciones guardadas en: INSTRUCCIONES.txt"
echo ""

# Resumen
echo "=========================================="
echo " RESUMEN"
echo "=========================================="
echo ""
print_success "Archivos generados en:"
echo "  📁 $(pwd)"
echo ""
ls -lh clave_privada.key solicitud.csr INSTRUCCIONES.txt
echo ""
print_warning "IMPORTANTE: Guarde la clave_privada.key en lugar seguro"
print_warning "Esta es la ÚNICA clave que funcionará con el certificado de AFIP"
echo ""
print_info "Abra INSTRUCCIONES.txt para continuar"
echo ""

# Abrir instrucciones automáticamente en macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    print_info "Abriendo instrucciones..."
    open INSTRUCCIONES.txt 2>/dev/null || cat INSTRUCCIONES.txt
fi

echo "=========================================="
