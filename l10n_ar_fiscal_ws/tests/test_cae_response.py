##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import json

from odoo.tests import tagged

from ..models.account_move import LOCAL_AUTH_CODE
from .common import TestFiscalWsCommon, answer


def cae_answer(result="A", observations=(), errors=()):
    """What WSFE answers to an authorization request."""
    detail = answer(
        CAE="61234567890123" if result == "A" else "",
        CAEFchVto="20301231" if result == "A" else None,
        Resultado=result,
        Observaciones=answer(Obs=list(observations)),
    )
    return answer(FeDetResp=answer(FECAEDetResponse=[detail]), Errors=answer(Err=list(errors)))


@tagged("post_install", "-at_install")
class TestCaeResponse(TestFiscalWsCommon):
    """What the module writes on the invoice for each answer of the service."""

    def setUp(self):
        super().setUp()
        self.invoice = self._new_invoice(self.journal_wsfe)

    def _as_production(self):
        """Without this the invoice validates locally, which is another scenario."""
        self.env["ir.config_parameter"].sudo().set_param("l10n_ar_fiscal_ws.env_type", "production")

    def test_authorized_invoice_keeps_the_authorization(self):
        """An accepted answer leaves the invoice with its CAE and its due date."""
        self._as_production()
        with self._cae_answers(cae_answer()):
            values = self.invoice._l10n_ar_request_cae()[0]

        self.assertEqual(values["l10n_ar_fiscal_result"], "A", "Una respuesta aceptada no es un rechazo")
        self.invoice.write(values)
        self.assertEqual(self.invoice.l10n_ar_fiscal_auth_mode, "CAE")
        self.assertEqual(self.invoice.l10n_ar_fiscal_auth_code, "61234567890123")
        self.assertEqual(self.invoice.l10n_ar_fiscal_auth_code_due.strftime("%Y%m%d"), "20301231")
        self.assertEqual(self.invoice.l10n_ar_fiscal_result, "A")
        self.assert_invoice_is_sound(self.invoice)

    def test_rejected_invoice_is_left_without_authorization(self):
        """A refusal authorizes nothing: no mode, no code, and the reason in the message."""
        self._as_production()
        errors = [answer(Code=10015, Msg="El comprobante ya fue autorizado")]
        with self._cae_answers(cae_answer(result="R", errors=errors)):
            values = self.invoice._l10n_ar_request_cae()[0]

        with self.subTest("la respuesta se devuelve como rechazo, con el motivo de ARCA"):
            self.assertIn("El comprobante ya fue autorizado", values["l10n_ar_fiscal_message"])
            self.assertEqual(values["l10n_ar_fiscal_result"], "R")

        with self.subTest("no queda ningún rastro de autorización"):
            self.assertFalse(values["l10n_ar_fiscal_auth_mode"])
            self.assertFalse(values["l10n_ar_fiscal_auth_code"])
            self.assertFalse(values["l10n_ar_fiscal_auth_code_due"])

        with self.subTest("la factura sigue sin autorización"):
            self.assertFalse(self.invoice.l10n_ar_fiscal_auth_code)
            self.assert_invoice_is_sound(self.invoice)

    def test_observed_invoice_keeps_the_observations(self):
        """An accepted answer with observations is authorized, and the observations are kept."""
        self._as_production()
        observations = [answer(Code=10016, Msg="El número de comprobante no es correlativo")]
        with self._cae_answers(cae_answer(observations=observations)):
            values = self.invoice._l10n_ar_request_cae()[0]

        self.assertEqual(values["l10n_ar_fiscal_result"], "A")
        self.invoice.write(values)
        self.assertIn("no es correlativo", self.invoice.l10n_ar_fiscal_message)
        self.assert_invoice_is_sound(self.invoice)

    def test_local_validation_without_certificates(self):
        """In homologation without certificates the invoice is authorized locally, and says so."""
        ws_code = self.invoice.journal_id.l10n_ar_fiscal_ws_id.code
        with self._answers(last_invoice=self._last_invoice_answer(ws_code, 41)):
            self.invoice._l10n_ar_post_batch(soft=True)

        with self.subTest("queda posteada y autorizada con el código local"):
            self.assertEqual(self.invoice.state, "posted")
            self.assertEqual(self.invoice.l10n_ar_fiscal_auth_code, LOCAL_AUTH_CODE)
            self.assert_number_matches_authorization(self.invoice, 42)
            self.assert_invoice_is_sound(self.invoice)

        with self.subTest("el motivo queda en el historial de la factura"):
            self.assertTrue(self.invoice.message_ids.filtered(lambda x: "solo localmente" in (x.body or "")))

        with self.subTest("el código QR informa los datos del comprobante"):
            values = json.loads(base64.b64decode(self.invoice.l10n_ar_fiscal_qr_code.split("p=")[1]))
            self.assertEqual(values["importe"], float("%.2f" % self.invoice.amount_total))
            self.assertEqual(values["moneda"], self.invoice.currency_id.l10n_ar_afip_code)
            self.assertEqual(values["codAut"], int(LOCAL_AUTH_CODE))
