##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from .common import TestFiscalWsCommon


@tagged("post_install", "-at_install")
class TestNumbering(TestFiscalWsCommon):
    """Where the number of the document comes from when the journal invoices by web service."""

    def test_number_follows_the_last_authorized_one(self):
        """The service, not the Odoo sequence, decides the next number."""
        invoice = self._new_invoice(self.journal_wsfe)
        ws_code = self.journal_wsfe.l10n_ar_fiscal_ws_id.code

        with self._answers(last_invoice=self._last_invoice_answer(ws_code, 41)):
            self.assertEqual(invoice._l10n_ar_get_next_number(), 42)

        self._number_it(invoice, number=42)
        self.assert_number_matches_authorization(invoice, 42)

    def test_the_service_is_asked_once_per_document_type(self):
        """Asking per invoice turns a batch into one call per invoice."""
        first = self._new_invoice(self.journal_wsfe)
        second = self._new_invoice(self.journal_wsfe)
        ws_code = self.journal_wsfe.l10n_ar_fiscal_ws_id.code

        first._l10n_ar_forget_numbering()
        with self._answers(last_invoice=self._last_invoice_answer(ws_code, 41)):
            first._l10n_ar_get_next_number()
            second._l10n_ar_get_next_number()

        self.assertEqual(self.service_calls.count("last_invoice"), 1)

    def test_each_service_answers_the_number_its_own_way(self):
        """Every service names the last number differently, and all three have to be read."""
        for journal in (self.journal_wsfe, self.journal_wsfex, self.journal_wsbfe):
            ws_code = journal.l10n_ar_fiscal_ws_id.code
            with self.subTest("el último número de %s se lee de su respuesta" % ws_code):
                document_type = self.env["l10n_latam.document.type"].search(
                    [("country_id", "=", self.env.ref("base.ar").id)], limit=1
                )
                with self._answers(last_invoice=self._last_invoice_answer(ws_code, 77)):
                    self.assertEqual(journal._l10n_ar_get_last_invoice_number(document_type), 77)
