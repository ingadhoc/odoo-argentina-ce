##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestBackgroundBatchCommon


@tagged("post_install", "-at_install")
class TestValidateWizard(TestBackgroundBatchCommon):
    """El botón de validar con varios comprobantes seleccionados."""

    def _wizard(self, moves):
        return (
            self.env["validate.account.move"].with_context(active_model="account.move", active_ids=moves.ids).create({})
        )

    def _validate(self, moves, sent):
        with self._recorded_post(sent), self._neutralized_cursor():
            self._wizard(moves).validate_move()

    def test_the_selection_travels_in_one_request(self):
        """Validar a mano varios comprobantes electrónicos es un pedido, no uno por comprobante."""
        invoices = self.env["account.move"]
        for _index in range(4):
            invoices |= self._new_invoice(self.journal_wsfe)

        sent = []
        self._validate(invoices, sent)

        self.assertEqual([len(batch) for batch in sent], [4])
        self.assertEqual(sent[0], invoices)

    def test_what_does_not_go_by_web_service_keeps_going_one_by_one(self):
        """El circuito original valida de a uno para guardar el estado de cada comprobante."""
        electronic = self._new_invoice(self.journal_wsfe) | self._new_invoice(self.journal_wsfe)
        manual = self.env["account.move"]
        journal = self._create_journal("preprinted")
        for _index in range(2):
            manual |= self._new_invoice(journal)

        sent = []
        self._validate(electronic + manual, sent)

        self.assertEqual([len(batch) for batch in sent], [2, 1, 1])
        self.assertEqual(sent[0], electronic)
        self.assertEqual(sent[1] | sent[2], manual)

    def test_a_selection_without_electronic_invoices_is_the_flow_of_always(self):
        """Sin nada que autorizar, el módulo no se mete en el medio."""
        manual = self.env["account.move"]
        journal = self._create_journal("preprinted")
        for _index in range(3):
            manual |= self._new_invoice(journal)

        sent = []
        self._validate(manual, sent)

        self.assertEqual([len(batch) for batch in sent], [1, 1, 1])

    def test_more_than_the_batch_size_still_asks_for_the_queue(self):
        """El tope del asistente no se toca: arriba de eso se valida en background."""
        self._set_param("batch_size", 2)
        invoices = self.env["account.move"]
        for _index in range(3):
            invoices |= self._new_invoice(self.journal_wsfe)

        sent = []
        with self.assertRaises(UserError), self._recorded_post(sent), self._neutralized_cursor():
            self._wizard(invoices).validate_move()
        self.assertEqual(sent, [], "Con el tope superado no se valida nada")
