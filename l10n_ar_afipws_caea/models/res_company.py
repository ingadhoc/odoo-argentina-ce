from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_caea = fields.Boolean(
        string='Request Caea autorization',
    )

    def get_active_caea(self):
        self.ensure_one()
        today = fields.Date.today()
        return self.env['afipws.caea'].search([
            ('company_id', '=', self.id),
            ('date_from', '<=', today),
            ('date_to', '>=', today),
        ], limit=1)
