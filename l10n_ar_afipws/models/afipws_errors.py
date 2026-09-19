##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Catálogo de errores AFIP con hints (port trixocom lib/errors.py, adaptado).

Sin dependencias Odoo: strings planos. La capa de modelos agrega `_()`.
Criterio trixocom: `Events` se loguean, `Errors` abortan.
"""

# (código o fragmento, descripción, hint)
WSAA_HINTS = [
    (
        "coe.alreadyAuthenticated",
        "Ya existe un TA válido",
        "Hay un token vigente pedido desde otro worker/sistema. Esperar a que expire (reuso en DB, no pedir otro).",
    ),
    (
        "cms.sign.invalid",
        "Firma inválida o algoritmo no soportado",
        "El certificado parece expirado o la clave no corresponde. Renovar el certificado AFIP.",
    ),
    (
        "cms.cert.expired",
        "Certificado expirado",
        "Renovar el certificado AFIP y confirmar el nuevo.",
    ),
    (
        "Computador no autorizado a acceder al servicio",
        "Certificado no delegado",
        "El certificado no está delegado para este WS en el portal AFIP (Administración de Certificados).",
    ),
    (
        "El CEE ya posee un TA valido para el acceso al WSN solicitado",
        "TA vigente en otro lado",
        "Se pidió otro token teniendo uno vigente (AFIP lo rechaza). Esperar 12h o reutilizar el de DB.",
    ),
    (
        "No se puede decodificar el BASE64",
        "Certificado y clave no matchean",
        "La clave privada no corresponde al certificado cargado.",
    ),
    (
        "request.expired",
        "TRA expirado",
        "Los timestamps del TRA van en TZ Argentina (-03:00) con ventana corta; reintentar (ya se genera así).",
    ),
    (
        "XML contra SCHEMA",
        "TRA contra schema",
        "El uniqueId debe ser uint32 (epoch en segundos, sin ms). Ya se genera así.",
    ),
]

# Hints WSFE por código numérico (los más comunes; resto → mensaje AFIP crudo)
WSFE_HINTS = {
    10016: "Reproceso: el comprobante ya fue autorizado antes (recuperar CAE con FECompConsultar).",
    10024: "Cotización no válida: contrastar MonCotiz con FEParamGetCotizacion del día.",
    1018: "Punto de venta no autorizado o bloqueado: verificar con FEParamGetPtosVenta.",
    1016: "Tipo de comprobante no habilitado para el punto de venta.",
    1025: "CUIT del receptor inválido o tipo doc incoherente (A/M exigen DocTipo 80).",
    10078: "Condición IVA del receptor inválida: verificar FEParamGetCondicionIvaReceptor.",
    10079: "CanMisMonExt inválido: debe ser S o N (res.config AFIP WS).",
}


def get_wsaa_hint(error_name):
    """Devuelve (desc, hint) para un fault/string WSAA. Fallback (None, None)."""
    text = str(error_name or "")
    for code, desc, hint in WSAA_HINTS:
        if code in text:
            return desc, hint
    return None, None


def get_wsfe_hint(code):
    """Devuelve (desc, hint) para un código WSFE. Fallback (None, None)."""
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return None, None
    hint = WSFE_HINTS.get(code_int)
    if hint:
        return "Error AFIP %s" % code_int, hint
    return None, None
