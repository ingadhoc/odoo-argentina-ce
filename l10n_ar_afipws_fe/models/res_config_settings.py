##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = "res.config.settings"

    l10n_ar_afip_fce_transmission = fields.Selection(
        [
            ("SCA", "SCA - TRANSFERENCIA AL SISTEMA DE CIRCULACION ABIERTA"),
            ("ADC", "ADC - AGENTE DE DEPOSITO COLECTIVO"),
        ],
        "FCE: Opción de Transmisión",
        help="Este campo sera necesario cuando informes comprobantes del tipo FCE MiPyME",
        config_parameter="l10n_ar_afipws_fe.fce_transmission",
    )

    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No"), ("account", "Account's Currency Dependant")],
        related="company_id.l10n_ar_payment_foreign_currency",
        readonly=False,
    )
    
