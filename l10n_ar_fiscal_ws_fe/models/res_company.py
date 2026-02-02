from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ar_afip_fce_transmission = fields.Selection(
        [
            ("SCA", "SCA - TRANSFERENCIA AL SISTEMA DE CIRCULACION ABIERTA"),
            ("ADC", "ADC - AGENTE DE DEPOSITO COLECTIVO"),
        ],
        "FCE: Opción de Transmisión",
        help="Este campo sera necesario cuando informes comprobantes del tipo FCE MiPyME",
    )

    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No"), ("account", "Account's Currency Dependant")],
        string="Default Policy for Payment in Foreign Currency",
        default="account",
    )
