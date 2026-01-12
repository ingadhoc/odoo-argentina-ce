##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class AfipResponseWizard(models.TransientModel):
    _name = "afip.response.wizard"
    _description = "AFIP Response Details"

    title = fields.Char(readonly=True)
    html_content = fields.Html(readonly=True, sanitize=False)
