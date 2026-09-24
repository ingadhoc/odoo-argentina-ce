##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models


class AccountPaymentInvoiceWizard(models.TransientModel):
    _inherit = "account.payment.invoice.wizard"

    l10n_ar_fiscal_period_from = fields.Date("Período asociado desde")
    l10n_ar_fiscal_period_to = fields.Date("Período asociado hasta")
    origin_invoice_id = fields.Many2one("account.move", "Comprobante de origen")
    commercial_partner_id = fields.Many2one("res.partner", related="payment_id.partner_id.commercial_partner_id")

    def get_invoice_vals(self):
        self.ensure_one()
        invoice_vals = super().get_invoice_vals()
        origin_field = (
            "reversed_entry_id" if invoice_vals["move_type"] in ("in_refund", "out_refund") else "debit_origin_id"
        )
        invoice_vals.update(
            {
                "l10n_ar_fiscal_period_from": self.l10n_ar_fiscal_period_from,
                "l10n_ar_fiscal_period_to": self.l10n_ar_fiscal_period_to,
                origin_field: self.origin_invoice_id.id,
            }
        )
        if self.env.context.get("is_automatic_subcharge"):
            journal = self.env["account.journal"].browse(invoice_vals.get("journal_id"))
            if journal.l10n_ar_fiscal_ws_id:
                # the automatic debit note of the financial surcharge has no related document,
                # so the authority asks for the period instead: the month before the receipt
                period_date = fields.Date.context_today(self)
                invoice_vals.update(
                    {
                        "l10n_ar_fiscal_period_from": fields.Date.subtract(period_date, months=1),
                        "l10n_ar_fiscal_period_to": period_date,
                    }
                )
        return invoice_vals
