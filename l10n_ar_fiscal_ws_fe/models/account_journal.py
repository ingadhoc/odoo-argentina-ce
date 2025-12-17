##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo.addons.l10n_ar_fiscal_ws.models.exceptions import ArcaError
from odoo.exceptions import UserError

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


ARCA_INVOCING_WS = [("code", "in", ["wsfe", "wsfex", "wsbfe"])]


class AccountJournal(models.Model):
    _inherit = "account.journal"

    arcaws = fields.Many2one(
        "arcaws",
        domain=ARCA_INVOCING_WS,
        compute="_compute_arcaws",
        store=True,
    )

    def _get_l10n_ar_afip_pos_types_selection(self):
        res = super()._get_l10n_ar_afip_pos_types_selection()
        res.insert(0, ("RAW_MAW", _("Electronic Invoice - Web Service")))
        res.insert(3, ("BFEWS", _("Electronic Fiscal Bond - Web Service")))
        res.insert(5, ("FEEWS", _("Export Voucher - Web Service")))
        return res

    @api.model
    def _get_type_mapping(self):
        return {"RAW_MAW": "wsfe", "FEEWS": "wsfex", "BFEWS": "wsbfe"}

    @api.depends("l10n_ar_afip_pos_system")
    def _compute_arcaws(self):
        type_mapping = self._get_type_mapping()
        with_ws_pos_type = self.filtered(
            lambda x: x.l10n_ar_afip_pos_system in type_mapping.keys()
        )
        for rec in with_ws_pos_type:
            rec.arcaws = self.env["arcaws"].search(
                [("code", "=", type_mapping[rec.l10n_ar_afip_pos_system])], limit=1
            )
        (self - with_ws_pos_type).arcaws = False

    def test_pyafipws_dummy(self):
        """
        ARCA Description: Método Dummy para verificación de funcionamiento de
        infraestructura (FEDummy)
        """
        self.ensure_one()
        if not self.arcaws:
            raise UserError(_("No ARCA WS selected"))
        return self.arcaws.action_dummie()

    def action_get_connection(self):
        self.ensure_one()
        if not self.arcaws:
            raise UserError(_("No ARCA WS selected"))
        self.company_id.arca_get_connection(self.arcaws.code)
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _(
                    "Great, everything seems fine. The connection did not fail."
                ),
                "type": "success",
                "sticky": True,  # True/False will display for few seconds if false
            },
        }
        return notification

    def test_pyafipws_point_of_sales(self):
        """
        ARCA Description: Método para obtener los puntos de venta habilitados
        """
        self.ensure_one()
        if not self.arcaws:
            raise ArcaError(_("No ARCA WS selected"))
        connection = self.company_id.arca_get_connection(self.arcaws.code)
        method = self.arcaws.ws_parameters.get("get_point_of_sale")
        auth = self.arcaws.ws_parameters.get("auth")
        raise ArcaError(connection.call_arca_service(method, {}, auth=auth))

    def get_pyafipws_cuit_document_classes(self):
        """
        ARCA Description: Método para obtener los puntos de venta habilitados
        """
        self.ensure_one()
        if not self.arcaws:
            raise ArcaError(_("No ARCA WS selected"))
        connection = self.company_id.arca_get_connection(self.arcaws.code)
        method = self.arcaws.ws_parameters.get("cuit_document_classes")
        auth = self.arcaws.ws_parameters.get("auth")
        raise ArcaError(connection.call_arca_service(method, {}, auth=auth))

    def _get_last_invoice_number(self, l10n_latam_document_type):
        self.ensure_one()
        if not self.arcaws:
            raise ArcaError(_("No ARCA WS selected"))
        connection = self.company_id.arca_get_connection(self.arcaws.code)
        last_invoice_info = self.arcaws.ws_parameters.get("last_invoice")

        method = last_invoice_info.get("method")
        auth = self.arcaws.ws_parameters.get("auth")
        pos_number = self.l10n_ar_afip_pos_number
        doc_type_code = l10n_latam_document_type.code
        params = {
            last_invoice_info.get("ptovta"): pos_number,
            last_invoice_info.get("tipocbte"): doc_type_code,
        }
        response = connection.call_arca_service(method, params, auth=auth)
        return response[last_invoice_info.get("cbtenro")]
