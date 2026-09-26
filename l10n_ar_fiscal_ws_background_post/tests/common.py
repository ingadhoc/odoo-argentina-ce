##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from odoo.addons.account_background_post.tests.invariants import BackgroundPostInvariants
from odoo.addons.l10n_ar_fiscal_ws.tests.common import TestFiscalWsCommon


class TestBackgroundBatchCommon(TestFiscalWsCommon, BackgroundPostInvariants):
    """Escenarios de la cola de background sobre diarios que facturan por web service."""

    def _set_param(self, key, value):
        self.env["ir.config_parameter"].sudo().set_param("account_background_post.%s" % key, value)

    @contextmanager
    def _neutralized_cursor(self):
        """El circuito commitea cada lote y hace rollback ante un error; el cursor de test
        prohíbe las dos cosas."""
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.env.cr, "commit", self.env.flush_all))
            stack.enter_context(patch.object(self.env.cr, "rollback", lambda: None))
            yield

    @contextmanager
    def _recorded_post(self, sent, error=None):
        """Anota con qué comprobantes se llamó a action_post, sin llegar al servicio.

        Con `error`, la primera llamada falla: es la forma de mirar qué hace el circuito
        con lo que quedó en borrador sin tener que simular una respuesta del organismo.
        """

        def action_post(this):
            sent.append(this)
            if error is not None and len(sent) == 1:
                raise error

        with patch.object(type(self.env["account.move"]), "action_post", action_post):
            yield

    @contextmanager
    def _no_service(self):
        """Falla el test si algo sale a pedir una autorización."""

        def _never(this, soft=True):
            raise AssertionError("Ningún comprobante de este escenario tenía que ir al servicio")

        with patch.object(type(self.env["account.move"]), "_l10n_ar_post_batch", _never):
            yield

    def _queued_invoices(self, journal, count):
        """Comprobantes en borrador, marcados para que los valide el cron."""
        invoices = self.env["account.move"]
        for _index in range(count):
            invoices |= self._new_invoice(journal)
        invoices._schedule_background_post()
        return invoices

    def _run_cron(self):
        with self._neutralized_cursor():
            self.env["account.move"].sudo()._cron_background_post_invoices()
