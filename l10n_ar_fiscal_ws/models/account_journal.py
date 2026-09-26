##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from psycopg2 import errors as pg_errors

from .exceptions import FiscalWsError, serialize_answer

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

    def _l10n_ar_lock(self, document_type):
        """Serialize the numbering of this journal and document type.

        Two posts at the same time would ask the service for the same last number
        and request the authorization of the same voucher; sending batches, they
        would collide over whole ranges. The lock lives in the transaction, so the
        commit of the batch releases it.
        """
        self.ensure_one()
        config = self.env["ir.config_parameter"].sudo()
        timeout = int(config.get_param("l10n_ar_fiscal_ws.lock_timeout", 30))
        key = "l10n_ar_fiscal_ws-%s-%s-%s" % (self.company_id.id, self.id, document_type.id)
        self.env.cr.execute(SQL("SELECT set_config('lock_timeout', %s, true)", "%ss" % timeout))
        try:
            self.env.cr.execute(SQL("SELECT pg_advisory_xact_lock(hashtext(%s))", key))
        except pg_errors.LockNotAvailable as error:
            # the failed lock leaves the transaction aborted, so nothing can be read after it
            self.env.cr.rollback()
            raise FiscalWsError(
                "Hay otro proceso facturando en el diario %s. Probá de nuevo en unos segundos." % self.display_name
            ) from error

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

    def _l10n_ar_get_invoice(self, document_type, number):
        """What the service has registered under a number of this journal.

        Empty when it has nothing: a number it never authorized comes back as an
        error instead of a voucher.
        """
        self.ensure_one()
        response = self._l10n_ar_call("invoice_query", {"document_type_code": document_type.code, "number": number})
        values = self._l10n_ar_build_response("invoice_query_response", response)
        return values if values.get("auth_code") else {}

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

    def l10n_ar_action_recover_invoices(self):
        """Asistente para traer del servicio los comprobantes que autorizó y Odoo no tiene."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("l10n_ar_fiscal_ws.action_fiscal_ws_recover")
        action["context"] = {"default_journal_id": self.id}
        return action

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
