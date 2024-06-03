from odoo import api, models, fields


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    afipws_cbu = fields.Char(string='CBU')
