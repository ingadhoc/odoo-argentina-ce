##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from unittest.mock import patch

from odoo.addons.l10n_ar_fiscal_ws.models.exceptions import FiscalWsError
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestBackgroundBatchCommon


@tagged("post_install", "-at_install")
class TestCronBatches(TestBackgroundBatchCommon):
    """Cómo sale la cola de background hacia el servicio."""

    def test_the_queue_travels_in_batches(self):
        """Una corrida pide la autorización de a lotes, no de a un comprobante."""
        self.env["ir.config_parameter"].sudo().set_param("l10n_ar_fiscal_ws.batch_size", 2)
        invoices = self._queued_invoices(self.journal_wsfe, 5)

        sent = []
        with self._recorded_post(sent):
            self._run_cron()

        self.assertEqual([len(batch) for batch in sent], [2, 2, 1])
        self.assertEqual(self.env["account.move"].union(*sent), invoices, "La corrida dejó comprobantes afuera")

    def test_each_journal_gets_its_own_request(self):
        """El encabezado del pedido es del diario, así que dos diarios no viajan juntos."""
        electronic = self._queued_invoices(self.journal_wsfe, 2)
        bonds = self._queued_invoices(self.journal_wsbfe, 1)

        sent = []
        with self._recorded_post(sent):
            self._run_cron()

        self.assertEqual(len(sent), 2)
        self.assertEqual({batch.journal_id for batch in sent}, {electronic.journal_id, bonds.journal_id})

    def test_a_refusal_only_charges_the_one_the_service_refused(self):
        """El servicio rechaza uno y devuelve sin enviar a los que venían detrás.

        El intento lo paga el rechazado, y el resto vuelve a la cola en la misma corrida,
        para que un comprobante malo no le haga esperar diez minutos a los que están sanos.
        """
        self._set_param("max_retries", 3)
        invoices = self._queued_invoices(self.journal_wsfe, 4)
        ordered = invoices._l10n_ar_batches()[0]

        sent = []
        with self._recorded_post(sent, error=FiscalWsError("El servicio rechazó el comprobante")):
            self._run_cron()

        self.assertEqual([len(batch) for batch in sent], [4, 3])
        self.assertEqual(sent[1], ordered[1:], "Los que no llegaron al servicio se mandan juntos de nuevo")
        self.assertEqual(ordered[0].background_post_attempts, 1)
        self.assertEqual(ordered[1:].mapped("background_post_attempts"), [0, 0, 0])
        self.assert_background_post_invariants(invoices)

    def test_a_failure_that_is_not_an_answer_falls_back_one_by_one(self):
        """Sin respuesta del servicio no hay forma de saber cuál rompió.

        El circuito original las toma de a una y le carga el intento a la que falla.
        """
        self._set_param("max_retries", 3)
        invoices = self._queued_invoices(self.journal_wsfe, 3)
        ordered = invoices._l10n_ar_batches()[0]
        broken = ordered[1]

        sent = []

        def action_post(this):
            sent.append(this)
            if len(sent) == 1 or this == broken:
                raise UserError("Se cayó la conexión")

        with patch.object(type(self.env["account.move"]), "action_post", action_post):
            self._run_cron()

        self.assertEqual([len(batch) for batch in sent], [3, 1, 1, 1], "El lote falló y se reintentó de a uno")
        self.assertEqual(broken.background_post_attempts, 1)
        self.assertEqual((ordered - broken).mapped("background_post_attempts"), [0, 0])
        self.assert_background_post_invariants(invoices)

    def test_the_rest_of_the_queue_keeps_going_one_by_one(self):
        """Un comprobante que no factura por web service no entra en ningún lote."""
        electronic = self._queued_invoices(self.journal_wsfe, 2)
        manual = self._queued_invoices(self._create_journal("preprinted"), 2)

        sent = []
        with self._recorded_post(sent):
            self._run_cron()

        self.assertEqual([len(batch) for batch in sent], [2, 1, 1])
        self.assertEqual(sent[0], electronic)
        self.assertEqual(sent[1] | sent[2], manual)

    def test_a_queue_without_electronic_invoices_is_the_circuit_of_always(self):
        """Sin nada que autorizar, el módulo no se mete en el medio."""
        manual = self._queued_invoices(self._create_journal("preprinted"), 3)

        sent = []
        with self._recorded_post(sent):
            self._run_cron()

        self.assertEqual([len(batch) for batch in sent], [1, 1, 1])
        self.assertEqual(self.env["account.move"].union(*sent), manual)
