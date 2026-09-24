##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ar_fiscal_ws_env_type = fields.Selection(
        [("homologation", "Homologation"), ("production", "Production")],
        string="Fiscal web services environment",
        config_parameter="l10n_ar_fiscal_ws.env_type",
    )
    l10n_ar_fce_transmission_type = fields.Selection(
        related="company_id.l10n_ar_fce_transmission_type",
        readonly=False,
    )
    l10n_ar_fiscal_payment_foreign_currency = fields.Selection(
        related="company_id.l10n_ar_fiscal_payment_foreign_currency",
        readonly=False,
    )
