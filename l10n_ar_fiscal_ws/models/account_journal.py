##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .exceptions import serialize_answer

_logger = logging.getLogger(__name__)

# Point of sale systems that invoice through a web service, and their service
POS_SYSTEM_WS = {"RAW_MAW": "wsfe", "FEEWS": "wsfex", "BFEWS": "wsbfe"}


class AccountJournal(models.Model):
    _inherit = "account.journal"

    l10n_ar_fiscal_ws_id = fields.Many2one(
        "l10n_ar.fiscal.ws",
        string="Fiscal web service",
        compute="_compute_l10n_ar_fiscal_ws_id",
        store=True,
    )

    def _get_l10n_ar_afip_pos_types_selection(self):
        res = super()._get_l10n_ar_afip_pos_types_selection()
        res.insert(0, ("RAW_MAW", _("Electronic Invoice - Web Service")))
        res.insert(3, ("BFEWS", _("Electronic Fiscal Bond - Web Service")))
        res.insert(5, ("FEEWS", _("Export Voucher - Web Service")))
        return res

    @api.depends("l10n_ar_afip_pos_system")
    def _compute_l10n_ar_fiscal_ws_id(self):
        services = self.env["l10n_ar.fiscal.ws"].search([("code", "in", list(POS_SYSTEM_WS.values()))])
        by_code = {service.code: service for service in services}
        for rec in self:
            rec.l10n_ar_fiscal_ws_id = by_code.get(POS_SYSTEM_WS.get(rec.l10n_ar_afip_pos_system))

    def _l10n_ar_call(self, code, extra=None):
        """Call a mapping of this journal's service and return its response."""
        self.ensure_one()
        if not self.l10n_ar_fiscal_ws_id:
            raise UserError(_("El diario %s no factura por web service.", self.display_name))
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping(self.l10n_ar_fiscal_ws_id.code, code)
        response, _xml = mapping.call(self, extra)
        return response

    def _l10n_ar_get_last_invoice_number(self, document_type):
        """Last number authorized by the service for a document type."""
        self.ensure_one()
        response = self._l10n_ar_call("last_invoice", {"document_type_code": document_type.code})
        values = self._l10n_ar_build_response("last_invoice_response", response)
        return int(values.get("number") or 0)

    def _l10n_ar_build_response(self, code, response):
        """Read a response through the mapping of this journal's service."""
        self.ensure_one()
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping(self.l10n_ar_fiscal_ws_id.code, code)
        return mapping.build(response)

    def l10n_ar_action_check_service(self):
        """Ask the service whether it is up."""
        self.ensure_one()
        return self._l10n_ar_show(self._l10n_ar_call("dummy"), _("Estado del servicio"))

    def l10n_ar_action_get_points_of_sale(self):
        self.ensure_one()
        return self._l10n_ar_show(self._l10n_ar_call("point_of_sale"), _("Puntos de venta habilitados"))

    def l10n_ar_action_get_document_types(self):
        self.ensure_one()
        return self._l10n_ar_show(self._l10n_ar_call("document_types"), _("Tipos de documento habilitados"))

    @staticmethod
    def _l10n_ar_show(answer, title):
        """Show what the service answered. Asking is not an error, so it is not raised.

        The client action decides between a notification and a dialog by the length
        of the answer.
        """
        return {
            "type": "ir.actions.client",
            "tag": "l10n_ar_fiscal_ws.service_answer",
            "params": {"title": title, "message": serialize_answer(answer)},
        }
