from odoo import fields, models
 
 
class ResCompany(models.Model):
 
    _inherit = "res.company"
 
    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No"), ("account", "Account's Currency Dependant")],
        string="Default Policy for Payment in Foreign Currency",
        default="account"
    )
