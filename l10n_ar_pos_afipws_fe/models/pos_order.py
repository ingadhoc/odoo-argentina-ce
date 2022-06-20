from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64


class PosOrder(models.Model):
    _inherit = "pos.order"

    l10n_ar_afip_qr_image = fields.Binary(string="image", compute="compute_qr_image")
    afip_auth_mode = fields.Selection(
        string="AFIP authorization mode",
        related="account_move.afip_auth_mode",
    )
    afip_auth_code = fields.Char(
        string="CAE/CAI/CAEA Code", related="account_move.afip_auth_code"
    )
    afip_auth_code_due = fields.Date(
        string="CAE/CAI/CAEA due Date", related="account_move.afip_auth_code_due"
    )

    def _export_for_ui(self, order):
        res = super()._export_for_ui(order)
        res["l10n_ar_afip_qr_image"] = order.l10n_ar_afip_qr_image
        res["afip_auth_mode"] = order.afip_auth_mode
        res["afip_auth_code"] = order.afip_auth_code
        res["afip_auth_code_due"] = order.afip_auth_code_due
        return res

    """@api.model
    def create_from_ui_extra_fields(self):
        return ['id', 'l10n_ar_afip_qr_image', 'afip_auth_mode',
                'afip_auth_code', 'afip_auth_code_due', 'account_move'
                ]

    @api.model
    def create_from_ui(self, orders, draft=False):
        order_info = super().create_from_ui(orders, draft)
        if order_info:
            order_server_ids = [x['id'] for x in order_info]
            order_extra_fields = self.env['pos.order'].search_read(
                domain=[('id', 'in', order_server_ids)],
                fields=self.create_from_ui_extra_fields()
            )
            for it in zip(order_info, order_extra_fields):
                it[0].update(it[1])
        return order_info"""

    def compute_qr_image(self):
        for order_id in self:
            if order_id.account_move and order_id.account_move.afip_qr_code:
                barcode = self.env["ir.actions.report"].barcode(
                    "QR", order_id.account_move.afip_qr_code, width=180, height=180
                )
                order_id.l10n_ar_afip_qr_image = base64.b64encode(barcode)
            else:
                order_id.l10n_ar_afip_qr_image = False

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()

        invoice_ids = self.refunded_order_ids.mapped("account_move").filtered(
            lambda x: x.company_id.country_id.code == "AR"
            and x.is_invoice()
            and x.move_type in ["out_invoice"]
            and x.journal_id.afip_ws
            and x.afip_auth_code
        )
        if len(invoice_ids) > 1:
            raise UserError(_("Only can refund one invoice at a time"))

        elif len(invoice_ids) == 1:
            vals["reversed_entry_id"] = invoice_ids[0].id
        return vals
