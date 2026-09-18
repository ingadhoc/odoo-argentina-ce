##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/models/l10n_ar_arca_activity.py
# (LGPL-3).
"""Padrón de actividades ARCA (ex AFIP).

Nomenclador F-883 — actividades a 6 dígitos. Para el reporte IVA Simple
sólo se usan los **3 dígitos** del código (sección/división), pero
el modelo guarda el código completo para futura extensibilidad.

Carga inicial: las actividades más usadas en data/. El usuario puede
agregar más manualmente o importar desde CSV.
"""
from odoo import fields, models


class L10nArArcaActivity(models.Model):
    _name = "l10n_ar.arca.activity"
    _description = "ARCA — Actividad económica (Nomenclador F-883)"
    _order = "code"
    _rec_name = "display_name"

    code = fields.Char(
        string="Código",
        required=True,
        help="Código del nomenclador F-883. Para IVA Simple se usan los 3 primeros dígitos.",
        index=True,
    )
    name = fields.Char(string="Descripción", required=True, translate=True)
    active = fields.Boolean(default=True)
    display_name = fields.Char(compute="_compute_display_name", store=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "El código de actividad debe ser único."),
    ]

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s · %s" % (rec.code, rec.name) if rec.code else rec.name

    @property
    def code3(self):
        """Devuelve los 3 primeros dígitos del código (para IVA Simple)."""
        return (self.code or "")[:3]
