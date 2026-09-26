##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from unittest.mock import patch

from odoo.tests import tagged

from ..models.exceptions import FiscalWsError
from .common import TestFiscalWsCommon, answer


def batch_answer(*results):
    """What WSFE answers to a request carrying several vouchers."""
    details = [
        answer(
            CAE="6123456789012%s" % index if result == "A" else "",
            CAEFchVto="20301231" if result == "A" else None,
            Resultado=result,
            Observaciones=answer(Obs=[]),
        )
        for index, result in enumerate(results)
    ]
    return answer(FeDetResp=answer(FECAEDetResponse=details), Errors=answer(Err=[]))


@tagged("post_install", "-at_install")
class TestCaeBatch(TestFiscalWsCommon):
    """Several invoices travelling to the service in the same request."""

    def test_the_request_carries_one_detail_per_invoice(self):
        """The header is built once and the detail is repeated, in the order it was sent."""
        invoices = self._numbered_invoices(self.journal_wsfe, 3)
        payload = self._build_cae_batch(invoices)

        with self.subTest("el encabezado declara cuántos comprobantes viajan"):
            header = payload["FeCAEReq"]["FeCabReq"]
            self.assertEqual(header["CantReg"], 3)
            self.assertEqual(header["PtoVta"], int(self.journal_wsfe.l10n_ar_afip_pos_number))

        with self.subTest("cada comprobante lleva su propio número, en orden"):
            details = payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]
            self.assertEqual([detail["CbteDesde"] for detail in details], [42, 43, 44])
            self.assertEqual([detail["CbteHasta"] for detail in details], [42, 43, 44])

        for detail in payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]:
            self.assert_payload_amounts_add_up("wsfe", detail)

    def test_one_invoice_builds_the_same_request_as_before(self):
        """A batch of one is the flow of always: the service sees no difference."""
        invoice = self._number_it(self._new_invoice(self.journal_wsfe))
        self.assertEqual(self._build_cae_batch(invoice), self._build_cae_request(invoice))

    def test_each_invoice_reads_its_own_answer(self):
        """The answer carries one detail per voucher, and each invoice takes its own."""
        invoices = self._numbered_invoices(self.journal_wsfe, 3)
        with self._cae_answers(batch_answer("A", "R", "R")):
            results = invoices._l10n_ar_request_cae()

        self.assertEqual([values["l10n_ar_fiscal_result"] for values in results], ["A", "R", "R"])
        with self.subTest("la aprobada se queda con el CAE que le tocó"):
            self.assertEqual(results[0]["l10n_ar_fiscal_auth_code"], "61234567890120")
        with self.subTest("las rechazadas no quedan con ningún rastro de autorización"):
            self.assertFalse(results[1]["l10n_ar_fiscal_auth_code"])
            self.assertFalse(results[2]["l10n_ar_fiscal_auth_mode"])

    def test_an_answer_that_is_missing_details_refuses_them(self):
        """The service stops at the first bad one: what it did not answer is not authorized."""
        invoices = self._numbered_invoices(self.journal_wsfe, 3)
        with self._cae_answers(batch_answer("A")):
            results = invoices._l10n_ar_request_cae()

        self.assertEqual([values["l10n_ar_fiscal_result"] for values in results], ["A", "R", "R"])
        self.assertTrue(results[1]["l10n_ar_fiscal_message"], "Un rechazo sin motivo igual dice algo")

    def test_a_request_that_never_got_through_authorizes_nothing(self):
        """When the call itself fails, no invoice of the batch is authorized."""
        invoices = self._numbered_invoices(self.journal_wsfe, 2)

        def _fail(mapping, records, extra=None):
            raise FiscalWsError("El servicio no responde")

        with patch.object(type(self.env["l10n_ar.fiscal.ws.mapping"]), "call_batch", _fail):
            results = invoices._l10n_ar_request_cae()
        self.assertEqual([values["l10n_ar_fiscal_result"] for values in results], ["R", "R"])
        self.assertIn("no responde", results[0]["l10n_ar_fiscal_message"])

    def test_the_batch_is_split_by_the_configured_size(self):
        """Nothing forces the whole selection into one request."""
        self.env["ir.config_parameter"].sudo().set_param("l10n_ar_fiscal_ws.batch_size", 2)
        invoices = self.env["account.move"]
        for _index in range(5):
            invoices |= self._new_invoice(self.journal_wsfe)

        self.assertEqual([len(batch) for batch in invoices._l10n_ar_batches()], [2, 2, 1])

    def test_only_the_service_that_takes_batches_gets_them(self):
        """The fiscal bond service authorizes one voucher per request, and that is respected."""
        bonds = self.env["account.move"]
        for _index in range(3):
            bonds |= self._new_invoice(self.journal_wsbfe)

        self.assertEqual([len(batch) for batch in bonds._l10n_ar_batches()], [1, 1, 1])

    def test_invoices_of_different_journals_travel_apart(self):
        """The header is common to the request, so a batch cannot mix points of sale."""
        domestic = self._new_invoice(self.journal_wsfe)
        bond = self._new_invoice(self.journal_wsbfe)

        batches = (domestic | bond)._l10n_ar_batches()
        self.assertEqual(len(batches), 2)
        self.assertEqual({batch.journal_id for batch in batches}, {domestic.journal_id, bond.journal_id})
