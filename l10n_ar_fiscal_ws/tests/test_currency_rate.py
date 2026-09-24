##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from ..models.exceptions import FiscalWsError
from .common import TestFiscalWsCommon, answer


@tagged("post_install", "-at_install")
class TestCurrencyRate(TestFiscalWsCommon):
    """Bringing the rate of the day from the service and applying it to the invoice."""

    def setUp(self):
        super().setUp()
        self._prepare_multicurrency_values()
        self.invoice = self._new_invoice(self.journal_wsfe, currency_id=self.env.ref("base.USD"))

    def test_rate_of_the_service_is_applied_to_the_invoice(self):
        """ARCA answers pesos per unit of foreign currency; the invoice stores the inverse."""
        rate = answer(ResultGet=answer(MonCotiz="1200.50"), Errors=None)
        with self._answers(currency_rate=rate):
            self.invoice.l10n_ar_action_get_currency_rate()

        with self.subTest("la cotización queda aplicada en la factura"):
            self.assertAlmostEqual(self.invoice.invoice_currency_rate, 1 / 1200.50, places=6)

        with self.subTest("queda registrada en el historial"):
            self.assertTrue(self.invoice.message_ids.filtered(lambda x: "1200.5" in (x.body or "")))

        self.assert_invoice_is_sound(self.invoice)

    def test_an_error_of_the_service_is_not_applied(self):
        """A refusal has to reach the user, and leave the rate as it was."""
        before = self.invoice.invoice_currency_rate
        rate = answer(ResultGet=None, Errors=answer(Err=[answer(Code=602, Msg="No existe la moneda")]))
        with self._answers(currency_rate=rate):
            with self.assertRaises(FiscalWsError):
                self.invoice.l10n_ar_action_get_currency_rate()

        self.assertEqual(self.invoice.invoice_currency_rate, before)
