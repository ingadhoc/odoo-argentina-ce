##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import _, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _l10n_ar_get_refunded_pos_orders(self):
        """Return POS orders being refunded by this recordset."""
        origin_orders = self.env["pos.order"]
        if "refunded_order_id" in self._fields:
            origin_orders |= self.refunded_order_id
        if "refunded_order_ids" in self._fields:
            origin_orders |= self.refunded_order_ids
        if not origin_orders:
            origin_orders = self.lines.refunded_orderline_id.order_id
        return origin_orders

    def _l10n_ar_get_refunded_electronic_invoices(self, origin_orders):
        """Return the original AR electronic invoices of the refunded orders."""
        invoices = origin_orders.mapped("account_move")
        if not invoices and origin_orders:
            invoices = self.env["account.move"].search(
                [
                    ("pos_order_ids", "in", origin_orders.ids),
                    ("move_type", "=", "out_invoice"),
                ]
            )
        return invoices.filtered(
            lambda move: move.company_id.country_id.code == "AR"
            and move.is_invoice()
            and move.move_type == "out_invoice"
            and move.journal_id.afip_ws
            and move.afip_auth_code
        )

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        if self.company_id.country_id.code != "AR":
            return vals

        origin_orders = self._l10n_ar_get_refunded_pos_orders()
        invoices = self._l10n_ar_get_refunded_electronic_invoices(origin_orders)
        if len(invoices) > 1:
            raise UserError(_("Only can refund one invoice at a time"))
        if len(invoices) == 1:
            vals["reversed_entry_id"] = invoices.id
        elif vals.get("move_type") == "out_refund" and origin_orders.mapped("account_move").filtered(
            lambda move: move.journal_id.afip_ws
        ):
            raise UserError(
                _(
                    "Cannot create the POS credit note because the original "
                    "electronic invoice with CAE was not found. The credit note "
                    "must reference the original invoice (point of sale and number)."
                )
            )
        return vals
