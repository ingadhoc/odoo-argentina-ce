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
        string='AFIP enviroment method',
        config_parameter='afip.ws.caea.state',
        default='inactive'
    )
    afip_ws_caea_timeout = fields.Float(
        string='caea timeout',
        config_parameter='afip.ws.caea.timeout',
        default=2
    )

    def afip_red_button(self):
        self.env['afipws.caea.log'].create([
            {'event': 'end_caea', 'user_id': self.env.user.id}
        ])
        self.env['ir.config_parameter'].set_param('afip.ws.caea.state', 'active')
