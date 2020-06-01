##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models

class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    afip_ws_env_type = fields.Selection(
        [('homologation', 'homologation'), ('production', 'production')],
        string='AFIP enviroment type',
    )

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res['afip_ws_env_type'] = self.env['ir.config_parameter'].sudo(
        ).get_param('afip.ws.env.type', default=False)
        return res

    def set_values(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'afip.ws.env.type', self.afip_ws_env_type)
        super(ResConfigSettings, self).set_values()
