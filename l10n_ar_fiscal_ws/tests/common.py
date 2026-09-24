##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields
from odoo.addons.l10n_ar.tests.common import TestArCommon

from .invariants import FiscalWsInvariants


def answer(**values):
    """Stand-in for what the service answers, read the same way as the real one."""
    return SimpleNamespace(**values)


class TestFiscalWsCommon(TestArCommon, FiscalWsInvariants):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Anchor every date of the scenarios to a single "today"
        cls.today = fields.Date.today()
        cls.journal_wsfe = cls._create_journal("wsfe")
        cls.journal_wsfex = cls._create_journal("wsfex")
        cls.journal_wsbfe = cls._create_journal("wsbfe")
        # A customer abroad, which is what the export service expects
        cls.partner_export = cls.env["res.partner"].create(
            {
                "name": "Cliente del exterior",
                "is_company": True,
                "street": "Rua Falsa 123",
                "city": "Sao Paulo",
                "zip": "01000",
                "country_id": cls.env.ref("base.br").id,
                "l10n_ar_afip_responsibility_type_id": cls.env.ref("l10n_ar.res_EXT").id,
                "l10n_latam_identification_type_id": cls.env.ref("l10n_ar.it_Sigd").id,
            }
        )

    @classmethod
    def _get_afip_pos_system_real_name(cls):
        """The point of sale systems that this module turns into a web service."""
        res = super()._get_afip_pos_system_real_name()
        res.update({"WSFE": "RAW_MAW", "WSFEX": "FEEWS", "WSBFE": "BFEWS"})
        return res

    def _new_invoice(self, journal, partner=None, **values):
        """Draft invoice of this journal, on a customer that gives it a document type."""
        values.setdefault("invoice_date", self.today)
        return self._create_invoice_ar(
            journal_id=journal,
            partner_id=partner or self.res_partner_adhoc,
            **values,
        )

    def _answers(self, **by_code):
        """Answer the calls of the journal with fixtures, so no test reaches the network."""

        self.service_calls = []

        def _call(journal, code, extra=None):
            self.service_calls.append(code)
            if code not in by_code:
                raise AssertionError("El test no previó la llamada al servicio '%s'" % code)
            return by_code[code]

        return patch.object(type(self.env["account.journal"]), "_l10n_ar_call", _call)

    def _last_invoice_answer(self, ws_code, number):
        """What each service answers when asked for the last authorized number."""
        if ws_code == "wsfe":
            return answer(CbteNro=number)
        if ws_code == "wsfex":
            return answer(FEXResult_LastCMP=answer(Cbte_nro=number))
        return answer(BFEResult_LastCMP=answer(Cbte_nro=number))

    def _number_it(self, invoice, number=42):
        """Give the invoice the number the service would have authorized.

        Posting is not an option here: the module commits after each authorized
        invoice and Odoo forbids committing from inside a test.
        """
        ws_code = invoice.journal_id.l10n_ar_fiscal_ws_id.code
        # writing the number recomputes the sequence, which asks the service for the last one
        with self._answers(last_invoice=self._last_invoice_answer(ws_code, number - 1)):
            invoice.l10n_latam_document_number = "%05d-%08d" % (
                int(invoice.journal_id.l10n_ar_afip_pos_number),
                number,
            )
        return invoice

    def _build_cae_request(self, invoice, extra=None):
        """Payload this invoice would send, built without calling the service."""
        ws_code = invoice.journal_id.l10n_ar_fiscal_ws_id.code
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping(ws_code, "cae_request")
        # the detail services ask for a request id, which is seeded so no call is made
        return mapping.build(invoice, dict(extra or {}, request_id=1))

    def _cae_answers(self, response):
        """Answer the authorization request with a fixture, keeping the xml the flow expects."""
        xml = {"xml_request": "<request/>", "xml_response": "<response/>"}
        return patch.object(
            type(self.env["l10n_ar.fiscal.ws.mapping"]),
            "call",
            lambda mapping, record, extra=None: (response, xml),
        )
