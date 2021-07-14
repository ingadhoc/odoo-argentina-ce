from odoo import fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    caea_id = fields.Many2one(
        'afipws.caea',
        string='Caea',
        copy=False
    )

    def get_pyafipws_last_invoice(self, document_type):
        if self.journal_id.use_for_caea:
            return self._l10n_ar_get_document_number_parts(self.l10n_latam_document_number,
                                                           self.l10n_latam_document_type_id.code)['invoice_number']
        else:
            return super().get_pyafipws_last_invoice(document_type)

    def post(self):
        caea_state = self.env['ir.config_parameter'].get_param(
            'afip.ws.caea.state', 'inactive')
        if caea_state == 'active':
            inv_ids = self.filtered(
                lambda record: record.journal_id.use_for_caea is False)
            for inv in inv_ids:
                if len(inv.journal_id.caea_journal_id):
                    inv.journal_id = inv.journal_id.caea_journal_id.id

        res = super().post()
        return res

    def do_pyafipws_request_cae(self):
        caea_state = self.env['ir.config_parameter'].get_param(
            'afip.ws.caea.state', 'inactive')
        if caea_state == 'inactive':
            return super().do_pyafipws_request_cae()
        elif caea_state == 'active':
            return self.do_pyafipws_request_caea()

    def do_pyafipws_request_caea(self):
        for inv in self:
            if inv.journal_id.use_for_caea is False:
                continue
            # Ignore invoices with cae (do not check date)
            if inv.afip_auth_code:
                continue

            afip_ws = inv.journal_id.afip_ws
            if not afip_ws:
                continue

            # Ignore invoice if not ws on point of sale
            if not afip_ws:
                raise UserError(_(
                    'If you use electronic journals (invoice id %s) you need '
                    'configure AFIP WS on the journal') % (inv.id))

            active_caea = inv.company_id.get_active_caea()
            if len(active_caea):
                msg = (
                    _('Afip conditional validation (CAEA %s)') % active_caea.afip_caea)
                inv.write({
                    'afip_auth_mode': 'CAEA',
                    'afip_auth_code': active_caea.afip_caea,
                    'afip_auth_code_due': inv.invoice_date,
                    'afip_result': '',
                    'afip_message': msg,
                    'caea_id': active_caea.id
                })
                inv.message_post(body=msg)
                continue
            else:
                raise UserError(_('The company does not have active CAEA'))
