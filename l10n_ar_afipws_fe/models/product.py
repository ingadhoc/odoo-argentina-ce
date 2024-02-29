from odoo import api, models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_ar_ncm_code = fields.Char(string='NCM')
