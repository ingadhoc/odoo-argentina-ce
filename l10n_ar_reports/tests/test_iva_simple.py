##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Tests IVA Simple — spec pura y formato CSV (sin tocar DB).

Ported (and adapted to 17.0 / AGPL-3) from
trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/tests/ (LGPL-3).
"""
from odoo.tests.common import TransactionCase

from ..report import iva_simple_spec as spec
from ..report import iva_simple_csv as fmt


class TestIvaSimpleSpec(TransactionCase):
    """Verifica los mappings y cálculos de la spec ARCA IVA Simple."""

    def test_vat_amount_21pct(self):
        self.assertEqual(spec.vat_amount(1000.0, "5"), 210.0)

    def test_vat_amount_10_5pct(self):
        self.assertEqual(spec.vat_amount(1000.0, "4"), 105.0)

    def test_vat_amount_27pct(self):
        self.assertEqual(spec.vat_amount(1000.0, "6"), 270.0)

    def test_vat_amount_5pct(self):
        self.assertEqual(spec.vat_amount(1000.0, "8"), 50.0)

    def test_vat_amount_0pct_exempt(self):
        for code in ("0", "1", "2", "3"):
            self.assertEqual(spec.vat_amount(1000.0, code), 0.0,
                             "vat_amount('%s') debería ser 0" % code)

    def test_vat_amount_rounding(self):
        self.assertEqual(spec.vat_amount(100.005, "5"), 21.00)
        self.assertEqual(spec.vat_amount(50.50, "5"), 10.61)

    def test_map_sale_operation_type_exenta(self):
        self.assertEqual(
            spec.map_sale_operation_type("0", False),
            spec.OP_TYPE_EXENTA,
        )

    def test_map_sale_operation_type_fixed_asset(self):
        op = spec.map_sale_operation_type("5", True)
        self.assertNotEqual(op, spec.OP_TYPE_EXENTA)

    def test_map_responsibility_to_buyer_type_known_codes(self):
        for resp_code in ("1", "4", "5", "6"):
            buyer = spec.map_responsibility_to_buyer_type(resp_code)
            self.assertIsNotNone(buyer,
                                 "responsability_code=%s debería mapear" % resp_code)

    def test_map_responsibility_to_buyer_type_unknown(self):
        spec.map_responsibility_to_buyer_type("999")
        spec.map_responsibility_to_buyer_type(None)
        spec.map_responsibility_to_buyer_type("")

    def test_map_purchase_concept_service(self):
        concept = spec.map_purchase_concept("service", False, False)
        self.assertIsNotNone(concept)

    def test_map_purchase_concept_fixed_asset(self):
        concept_with_fa = spec.map_purchase_concept("consu", True, False)
        concept_without_fa = spec.map_purchase_concept("consu", False, False)
        self.assertNotEqual(concept_with_fa, concept_without_fa,
                            "El tag fixed_asset debe cambiar el concepto")

    def test_map_purchase_concept_leases_priority(self):
        concept_leases = spec.map_purchase_concept("consu", True, True)
        concept_fa = spec.map_purchase_concept("consu", True, False)
        self.assertNotEqual(concept_leases, concept_fa,
                            "El tag leases debe priorizar sobre fixed_asset")


class TestIvaSimpleCsvFormat(TransactionCase):
    """Verifica el formateo AFIP de los CSV (latin-1, ; coma decimal)."""

    def test_transform_value(self):
        self.assertEqual(fmt.transform_value(123.45), "123,45")
        self.assertEqual(fmt.transform_value(-123.45), "123,45")
        self.assertEqual(fmt.transform_value(0), "0,00")
        self.assertEqual(fmt.transform_value(0.0), "0,00")
        self.assertEqual(fmt.transform_value(None), "")
        self.assertEqual(fmt.transform_value("ABC"), "ABC")

    def test_rows_to_csv_bytes(self):
        out = fmt.rows_to_csv_bytes(
            ["Actividad", "Monto Neto Gravado"],
            [{"Actividad": "620", "Monto Neto Gravado": 1000.0}],
        )
        text = out.decode("latin-1")
        self.assertIn("Actividad;Monto Neto Gravado", text)
        self.assertIn("620;1000,00", text)
