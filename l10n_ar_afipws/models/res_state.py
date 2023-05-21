from odoo import fields, models


class State(models.Model):
    _inherit = 'res.country.state'

    supa_code = fields.Integer(string='Código SUPA')
