from odoo import fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    caea_journal_id = fields.Many2one(
        'account.journal',
        string='Caea journal',
    )
    use_for_caea = fields.Boolean(
        string='Use for caea',
    )

    def test_pyafipws_dummy(self):
        """
        AFIP Description: Método Dummy para verificación de funcionamiento de
        infraestructura (FEDummy)
        """
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        view_id = self.env.ref('l10n_ar_afipws_caea.pyafipws_dummy_form').id
        view = {
            'name': _("AFIP service %s") % afip_ws,
            'view_mode': 'form',
            'view_id': view_id,
            'view_type': 'form',
            'res_model': 'pyafipws.dummy',
            'res_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_journal_id': self.id},
        }
        return view
