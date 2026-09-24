##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.tests import tagged

# Widths the authority fixes for each record of the exchange files
CBTE_LINE_LENGTH = 266
ALICUOTAS_LINE_LENGTH = 62


@tagged("post_install", "-at_install")
class TestVatLedger(TestArCommon):
    """The ledger of a period: what it gathers and what it hands to the authority."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        # a preprinted journal: the ledger gathers any invoice, with or without web service
        cls.journal = cls._create_journal("preprinted")
        cls.invoice = cls._create_invoice_ar(
            journal_id=cls.journal, partner_id=cls.res_partner_adhoc, invoice_date=cls.today
        )
        cls.invoice.action_post()

    def _create_ledger(self):
        return self.env["account.vat.ledger"].create(
            {
                "type": "sale",
                "date_from": self.today,
                "date_to": self.today,
                "journal_ids": [(6, 0, self.journal.ids)],
                "first_page": 1,
            }
        )

    def test_the_ledger_gathers_the_invoices_of_its_period(self):
        """The invoice posted in the period shows up in the ledger, through the VAT lines view."""
        ledger = self._create_ledger()

        with self.subTest("la factura del período está en el libro"):
            self.assertIn(self.invoice, ledger.invoice_ids.move_id)

        with self.subTest("el título dice el tipo y el período"):
            self.assertIn("Sales", ledger.name)

    def test_the_exchange_files_have_the_shape_the_authority_asks(self):
        """Each record of the CITI files is a fixed width line: a wrong width is rejected."""
        ledger = self._create_ledger()
        ledger.compute_txt_data()

        with self.subTest("cada comprobante ocupa una línea del ancho declarado"):
            lines = ledger.REGINFO_CV_CBTE.split("\r\n")
            self.assertTrue(lines and lines[0])
            for line in lines:
                self.assertEqual(len(line), CBTE_LINE_LENGTH)

        with self.subTest("cada alícuota ocupa una línea del ancho declarado"):
            for line in ledger.REGINFO_CV_ALICUOTAS.split("\r\n"):
                self.assertEqual(len(line), ALICUOTAS_LINE_LENGTH)

        with self.subTest("los archivos quedan descargables"):
            self.assertTrue(ledger.vouchers_file)
            self.assertTrue(ledger.vouchers_filename.endswith(".txt"))

    def test_the_book_renders_as_a_spreadsheet(self):
        """The ledger is handed to the accountant as a spreadsheet, with its invoices in it."""
        ledger = self._create_ledger()
        content, content_type = self.env["ir.actions.report"]._render_xlsx(
            "l10n_ar_fiscal_ws_reports.account_vat_ledger_xlsx", ledger.ids, None
        )

        self.assertEqual(content_type, "xlsx")
        # a spreadsheet is a zip container: the signature is what tells it apart from an error page
        self.assertTrue(content.startswith(b"PK"))
