##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    # TODO podriamos mejorar y no requerir todos estos y usar alguno de los
    # nativos company signed
    # no gravado en iva
    # cc_vat_untaxed = fields.Monetary(
    cc_vat_untaxed_base_amount = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. VAT Untaxed',
    )
    # company currency default odoo fields
    cc_amount_total = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. Total',
    )
    cc_amount_untaxed = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. Untaxed',
    )
    cc_amount_tax = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. Tax',
    )
    # von iva
    cc_vat_amount = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. VAT Amount',
    )
    cc_other_taxes_amount = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. Other Taxes Amount'
    )
    cc_vat_exempt_base_amount = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. VAT Exempt Base Amount'
    )
    cc_vat_taxable_amount = fields.Monetary(
        compute="_compute_currency_values",
        string='Company Cur. VAT Taxable Amount'
    )

    @api.depends('currency_id')
    def _compute_currency_values(self):
        # TODO si traer el rate de esta manera no resulta (por ej. porque
        # borran una linea de rate), entonces podemos hacerlo desde el move
        # mas o menos como hace account_invoice_currency o viendo el total de
        # debito o credito de ese mismo
        for rec in self.filtered('currency_id'):
            if rec.company_id.currency_id == rec.currency_id:
                rec.cc_amount_untaxed = rec.amount_untaxed
                rec.cc_amount_tax = rec.amount_tax
                rec.cc_amount_total = rec.amount_total
                rec.cc_vat_untaxed_base_amount = rec.vat_untaxed_base_amount
                rec.cc_vat_amount = rec.vat_amount
                rec.cc_other_taxes_amount = rec.other_taxes_amount
                rec.cc_vat_exempt_base_amount = rec.vat_exempt_base_amount
                rec.cc_vat_taxable_amount = rec.vat_taxable_amount
                # rec.currency_rate = 1.0
            else:
                # nueva modalidad de currency_rate
                # el or es por si la factura no esta balidad o no es l10n_ar
                currency_rate = rec.currency_rate or rec.currency_id._convert(
                    1., rec.company_id.currency_id, rec.company_id,
                    rec.date_invoice or fields.Date.context_today(rec),
                    round=False)
                rec.cc_amount_untaxed = rec.currency_id.round(
                    rec.amount_untaxed * currency_rate)
                rec.cc_amount_tax = rec.currency_id.round(
                    rec.amount_tax * currency_rate)
                rec.cc_amount_total = rec.currency_id.round(
                    rec.amount_total * currency_rate)
                rec.cc_vat_untaxed_base_amount = rec.currency_id.round(
                    rec.vat_untaxed_base_amount * currency_rate)
                rec.cc_vat_amount = rec.currency_id.round(
                    rec.vat_amount * currency_rate)
                rec.cc_other_taxes_amount = rec.currency_id.round(
                    rec.other_taxes_amount * currency_rate)
                rec.cc_vat_exempt_base_amount = rec.currency_id.round(
                    rec.vat_exempt_base_amount * currency_rate)
                rec.cc_vat_taxable_amount = rec.currency_id.round(
                    rec.vat_taxable_amount * currency_rate)
