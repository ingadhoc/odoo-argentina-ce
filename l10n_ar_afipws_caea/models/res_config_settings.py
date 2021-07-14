##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    afip_ws_caea_state = fields.Selection(
        [('inactive', 'Use WS'), ('active', 'Use CAEA'),
         ('syncro', 'In AFIP syncro')],
        string='AFIP enviroment type',
        config_parameter='afip.ws.caea.state',
        default='inactive'
    )

    def afip_red_button(self):
        self.env['ir.config_parameter'].set_param('afip.ws.caea.state', 'active')
