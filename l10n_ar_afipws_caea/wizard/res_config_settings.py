##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = "res.config.settings"

    use_caea = fields.Boolean(
        string="use caea", related="company_id.use_caea", readonly=False
    )

    afip_ws_caea_state = fields.Selection(
        [("inactive", "Use WS"), ("active", "Use CAEA"), ("syncro", "In AFIP syncro")],
        string="AFIP enviroment method",
        config_parameter="afip.ws.caea.state",
        default="inactive",
    )
    afip_ws_caea_timeout = fields.Float(
        string="caea timeout", config_parameter="afip.ws.caea.timeout", default=2
    )

    def afip_red_button(self):
        """self.env["l10n_ar.afipws.caea.log"].create(
            [{"event": "start_caea", "user_id": self.env.user.id}]
        )"""
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "active")

    def afip_green_button(self):
        """self.env["l10n_ar.afipws.caea.log"].create(
            [{"event": "end_caea", "user_id": self.env.user.id}]
        )"""
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "inactive")
