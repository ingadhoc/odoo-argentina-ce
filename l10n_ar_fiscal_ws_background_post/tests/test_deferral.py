##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import TestBackgroundBatchCommon


@tagged("post_install", "-at_install")
class TestDeferral(TestBackgroundBatchCommon):
    """Mandar a la cola y pedir la autorización son excluyentes."""

    def test_an_invoice_sent_to_the_queue_does_not_reach_the_service(self):
        """El diferido no queda posteado, así que el lote no tiene qué autorizar.

        Los dos módulos definen `_post` y el orden en que se encadenan depende de cómo
        cargan: sin este puente, con el lote afuera el comprobante se difiere y se pide
        igual, para un comprobante que nadie numeró.
        """
        invoice = self._new_invoice(self.journal_wsfe)

        with self._no_service():
            invoice.with_context(force_background_post=True).action_post()

        self.assertEqual(invoice.state, "draft")
        self.assertTrue(invoice.background_post)
        self.assertFalse(invoice.l10n_ar_fiscal_auth_code)
        self.assert_background_post_invariants(invoice)

    def test_the_queue_waits_for_the_date_the_context_brings(self):
        """Diferir con fecha deja el comprobante esperando, y tampoco toca el servicio."""
        invoice = self._new_invoice(self.journal_wsfe)
        when = (fields.Datetime.now() + timedelta(hours=1)).replace(microsecond=0)

        with self._no_service():
            invoice.with_context(force_background_post=when).action_post()

        self.assertEqual(invoice.background_post_date, when)
        self.assertEqual(invoice.state, "draft")
