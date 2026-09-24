##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # the report of l10n_ar prints this code on a fiscal bond voucher, but the field itself
    # is only declared by the enterprise localization
    l10n_ar_ncm_code = fields.Char(
        "Código NCM",
        copy=False,
        help="Código según la Nomenclatura Común del Mercosur, que pide el bono fiscal electrónico.",
    )
