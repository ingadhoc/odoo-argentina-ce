##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, api, fields, _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    afip_ws = fields.Selection(
        selection="_get_afip_ws", compute="_compute_afip_ws", string="AFIP WS"
    )

    def _get_afip_ws(self):
        return [
            ("wsfe", _("Domestic market -without detail- RG2485 (WSFEv1)")),
            ("wsfex", _("Export -with detail- RG2758 (WSFEXv1)")),
            ("wsbfe", _("Fiscal Bond -with detail- RG2557 (WSBFE)")),
        ]

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
    def _compute_afip_ws(self):
        """Depending on AFIP POS System selected set the proper AFIP WS"""
        type_mapping = self._get_type_mapping()
        for rec in self:
            rec.afip_ws = type_mapping.get(rec.l10n_ar_afip_pos_system, False)


    def test_pyafipws_dummy(self):
        """
        AFIP Description: Método Dummy para verificación de funcionamiento de
        infraestructura (FEDummy)
        """
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        connection = self.company_id.get_connection(afip_ws)
        client, auth, transport = connection.connect()
        if afip_ws == "wsfe":
            response = client.service.FEDummy()
            status = (response.AppServer, response.DbServer, response.AuthServer)
        elif afip_ws == "wsfex":
            response = client.service.FEXDummy()
            status = (response.AppServer, response.DbServer, response.AuthServer)
        elif afip_ws == "wsbfe":
            response = client.service.BFEDummy()
            status = (response.AppServer, response.DbServer, response.AuthServer)
        elif afip_ws == "wscdc":
            response = client.service.WSCDCDummy()
            status = (getattr(response, "AppServer", "?"), getattr(response, "DbServer", "?"), getattr(response, "AuthServer", "?"))
        else:
            raise UserError(_("AFIP WS %s not implemented") % afip_ws)
        if status == ("OK", "OK", "OK"):
            notification_type = "success"
        else:
            notification_type = "warning"

        msg = "AppServerStatus: %s DbServerStatus: %s AuthServerStatus: %s" % status
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("AFIP service %s\n") % afip_ws + msg,
                "type": notification_type,
                "sticky": True,  # True/False will display for few seconds if false
            },
        }

        return notification

    def action_get_connection(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        self.company_id.get_connection(afip_ws).connect()
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

    # def get_pyafipws_currency_rate(self, currency):
    #     raise UserError(
    #         currency.get_pyafipws_currency_rate(
    #             afip_ws=self.afip_ws,
    #             company=self.company_id,
    #         )[1]
    #     )
