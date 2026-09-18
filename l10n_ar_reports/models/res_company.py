##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/models/res_company.py
# (LGPL-3).
"""Activity ARCA default por empresa."""
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ar_arca_activity_id = fields.Many2one(
        "l10n_ar.arca.activity",
        string="Actividad ARCA principal",
        help=(
            "Actividad económica principal de la empresa según el "
            "nomenclador F-883. Se usa como default al generar IVA "
            "Simple si la cuenta contable no tiene actividad propia."
        ),
    )
