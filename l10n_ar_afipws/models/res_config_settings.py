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
        config_parameter='afip.ws.env.type'
    )
