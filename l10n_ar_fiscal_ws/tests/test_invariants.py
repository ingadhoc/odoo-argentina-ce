##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from .common import TestFiscalWsCommon


@tagged("post_install", "-at_install")
class TestInvariants(TestFiscalWsCommon):
    """Each invariant, on a sound operation and on a defective one.

    Without the second case an invariant that looks at nothing stays green forever.
    """

    def test_authorization_is_complete(self):
        invoice = self._new_invoice(self.journal_wsfe)

        with self.subTest("una factura sin autorizar no molesta"):
            self.assert_authorization_is_complete(invoice)

        with self.subTest("un modo de autorización sin código se detecta"):
            invoice.l10n_ar_fiscal_auth_mode = "CAE"
            with self.assertRaises(AssertionError):
                self.assert_authorization_is_complete(invoice)

        with self.subTest("un código sin modo también se detecta"):
            invoice.write({"l10n_ar_fiscal_auth_mode": False, "l10n_ar_fiscal_auth_code": "61234567890123"})
            with self.assertRaises(AssertionError):
                self.assert_authorization_is_complete(invoice)

    def test_number_matches_authorization(self):
        invoice = self._new_invoice(self.journal_wsfe)
        self._number_it(invoice, number=42)

        with self.subTest("el número que autorizó ARCA no molesta"):
            self.assert_number_matches_authorization(invoice, 42)

        with self.subTest("un número distinto al autorizado se detecta"):
            with self.assertRaises(AssertionError):
                self.assert_number_matches_authorization(invoice, 43)

    def test_payload_amounts_add_up(self):
        voucher = {"ImpTotal": "121.00", "ImpNeto": "100.00", "ImpIVA": "21.00"}

        with self.subTest("un comprobante que cierra no molesta"):
            self.assert_payload_amounts_add_up("wsfe", voucher)

        with self.subTest("un total que no es la suma de sus partes se detecta"):
            with self.assertRaises(AssertionError):
                self.assert_payload_amounts_add_up("wsfe", dict(voucher, ImpIVA="10.00"))

    def test_items_add_up_to_total(self):
        voucher = {
            "Imp_total": "121.00",
            "Items": {"Item": [{"Imp_total": "100.00"}, {"Imp_total": "21.00"}]},
        }

        with self.subTest("ítems que suman el total no molestan"):
            self.assert_items_add_up_to_total(voucher, "Imp_total")

        with self.subTest("un ítem que falta se detecta"):
            broken = {"Imp_total": "121.00", "Items": {"Item": [{"Imp_total": "100.00"}]}}
            with self.assertRaises(AssertionError):
                self.assert_items_add_up_to_total(broken, "Imp_total")
