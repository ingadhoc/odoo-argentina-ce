##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/lib/iva_simple.py (LGPL-3).
"""Specs y mappings de los CSV del régimen IVA Simple AFIP/ARCA.

Lib pura — no importa ``odoo``.

4 archivos según tipo de comprobante / movimiento:

================== ========================== ==================
Archivo            Origen (move_type)         File prefix
================== ========================== ==================
``DEBITO``         out_invoice + out_receipt  Ventas (FA-A/B/C/E + ND)
``REST_DEBITO``    out_refund                 Ventas NC
``CREDITO``        in_invoice + in_receipt    Compras (FA-A/B/C + ND)
``REST_CREDITO``   in_refund                  Compras NC
================== ========================== ==================

Encoding: latin-1, separador ``;``, decimales ``,``.

Mappings AFIP (de la spec / `l10n_ar_reports_simple` enterprise):

* **Codigo de Alicuota** = ``account.tax.group.l10n_ar_vat_afip_code``:
    ``'3'`` → 0%, ``'4'`` → 10.5%, ``'5'`` → 21%, ``'6'`` → 27%,
    ``'8'`` → 5%, ``'9'`` → 2.5%. Códigos ``'0','1','2'`` (no gravado /
    exento) se mapean a tipo de operación = "Exenta" (3) en VENTAS, y
    no se reportan por alícuota sino con el monto exento separado.

* **Tipo de Operacion (Ventas)**:
    ``1`` = Gravada (default cuando hay alícuota IVA > 0)
    ``2`` = Bienes de Uso (account tagged con tag_fixed_asset_account)
    ``3`` = Exenta / No gravada (vat_code IN '0','1','2')

* **Tipo de sujeto comprador (Ventas)** — mapea desde
  ``partner.l10n_ar_afip_responsibility_type_id.code``:
    ``'1'``                     → ``'1'`` (Responsable Inscripto)
    ``'6'`` o ``'13'``          → ``'2'`` (Monotributo / MT social)
    resto (CF/Exento/Exterior)  → ``'3'``

* **Concepto (Compras)**:
    ``1`` = Productos (default)
    ``2`` = Locaciones (account tagged tag_leases_rentals_account)
    ``3`` = Servicios (product.type='service')
    ``4`` = Bienes de Uso (account tagged tag_fixed_asset_account)
"""

# ---------- Headers de cada archivo (orden fijo) ----------
HEADERS_DEBITO = [
    "Actividad",
    "Tipo de Operacion",
    "Tipo de sujeto comprador",
    "Codigo de Alicuota",
    "Monto Neto Gravado",
    "Debito Fiscal Facturado",
    "Debito Fiscal O.D.P.",
    "Monto Neto Exento o No Gravado",
]
HEADERS_REST_DEBITO = [
    "Actividad",
    "Tipo de Operacion",
    "Codigo de Alicuota",
    "Monto Neto Gravado",
    "Debito Fiscal a Restituir",
    "Monto Neto Exento o No Gravado",
]
HEADERS_CREDITO = [
    "Concepto",
    "Codigo de Alicuota",
    "Monto Neto Gravado",
    "Credito Fiscal Facturado",
    "Credito Fiscal Computable",
]
HEADERS_REST_CREDITO = [
    "Concepto",
    "Codigo de Alicuota",
    "Monto Neto Gravado",
    "Credito Fiscal Facturado",
]

# ---------- Mapeos puros ----------

# vat_code → alícuota IVA (%) usado para calcular debito/credito fiscal.
VAT_CODE_TO_PERCENT = {
    "3": 0.0,
    "4": 10.5,
    "5": 21.0,
    "6": 27.0,
    "8": 5.0,
    "9": 2.5,
}

# vat_codes considerados "exentos / no gravados" para Ventas.
EXEMPT_VAT_CODES = {"0", "1", "2"}

# Operation type Ventas.
OP_TYPE_GRAVADA = 1
OP_TYPE_BIENES_DE_USO = 2
OP_TYPE_EXENTA = 3

# Operation type compras (Concepto).
CONCEPT_PRODUCTOS = 1
CONCEPT_LOCACIONES = 2
CONCEPT_SERVICIOS = 3
CONCEPT_BIENES_DE_USO = 4


def map_responsibility_to_buyer_type(resp_code):
    """Mapea ``partner.l10n_ar_afip_responsibility_type_id.code`` → string para CSV.

    Devuelve ``''`` si el código no está mapeado (CSV lo deja vacío).
    """
    if not resp_code:
        return ""
    if resp_code == "1":
        return "1"
    if resp_code in ("6", "13"):
        return "2"
    if resp_code in ("4", "5", "7", "8", "9", "10", "16"):
        return "3"
    return ""


def map_sale_operation_type(vat_code, is_fixed_asset):
    """Decide tipo de operación de Venta para una línea.

    * Si vat_code en exentos/no gravados → 3 (Exenta).
    * Si la cuenta está tagged como Bien de Uso → 2.
    * Default → 1 (Gravada).
    """
    if vat_code in EXEMPT_VAT_CODES:
        return OP_TYPE_EXENTA
    if is_fixed_asset:
        return OP_TYPE_BIENES_DE_USO
    return OP_TYPE_GRAVADA


def map_purchase_concept(product_type, is_fixed_asset, is_leases):
    """Decide Concepto de Compra para una línea.

    Prioridad: leases > fixed_asset > product.type='service' > productos.
    (Esto matchea el comportamiento de enterprise).
    """
    if is_leases:
        return CONCEPT_LOCACIONES
    if is_fixed_asset:
        return CONCEPT_BIENES_DE_USO
    if product_type == "service":
        return CONCEPT_SERVICIOS
    return CONCEPT_PRODUCTOS


def vat_amount(net_amount, vat_code):
    """Calcula débito/crédito fiscal aplicando la alícuota al neto agregado.

    **Método: cálculo teórico** (alícuota × neto agrupado).

    AFIP IVA Simple acepta este enfoque. La precisión por línea (sumar
    `tax_line_id` reales via `compute_all`) se reserva para el **Libro
    IVA Digital**, que sí lo exige y consume otra fuente
    (`account.ar.vat.line`).

    Diferencia típica entre teórico y real: < $0.05 por agrupación, por
    redondeo por línea. ARCA acepta ambos.
    """
    pct = VAT_CODE_TO_PERCENT.get(vat_code, 0.0)
    return round(net_amount * pct / 100.0, 2)
