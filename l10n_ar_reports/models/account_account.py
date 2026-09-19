##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/models/account_account.py
# (LGPL-3).
"""Activity ARCA por cuenta contable.

Permite asignar una actividad a una cuenta de ingresos / egresos
específica. Útil cuando una empresa tiene varias actividades y cada
una se factura/imputa a cuentas distintas.

Cadena de fallback al generar IVA Simple:
  1. line.account_id.l10n_ar_arca_activity_id  (más granular)
  2. company.l10n_ar_arca_activity_id           (default empresa)
  3. wizard.activity_id                          (override puntual)
"""
from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    l10n_ar_arca_activity_id = fields.Many2one(
        "l10n_ar.arca.activity",
        string="Actividad ARCA",
        help=(
            "Actividad económica del nomenclador F-883 asignada a esta "
            "cuenta. Se usa al generar el reporte IVA Simple para "
            "agrupar movimientos por actividad. Si está vacío, cae al "
            "default de la empresa."
        ),
    )
