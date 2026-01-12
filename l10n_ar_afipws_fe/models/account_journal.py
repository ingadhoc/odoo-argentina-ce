##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    afip_ws = fields.Selection(selection="_get_afip_ws", compute="_compute_afip_ws", string="AFIP WS")
    afip_certificate_info = fields.Char(
        string="Certificate Info",
        compute="_compute_afip_certificate_info",
        help="Information about the AFIP certificate being used",
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

    @api.depends("afip_ws", "company_id")
    def _compute_afip_certificate_info(self):
        """Compute certificate information for display"""
        for rec in self:
            if not rec.afip_ws or not rec.company_id:
                rec.afip_certificate_info = False
                continue

            try:
                environment_type = rec.company_id._get_environment_type()
                _logger.debug(f"Computing certificate info for journal {rec.name}, environment: {environment_type}")

                certificate = self.env["afipws.certificate"].search(
                    [
                        ("alias_id.company_id", "=", rec.company_id.id),
                        ("alias_id.type", "=", environment_type),
                        ("state", "=", "confirmed"),
                    ],
                    limit=1,
                )

                if certificate:
                    # Obtener información del certificado
                    cert_info_parts = []

                    # Agregar CUIT
                    if certificate.alias_id.cuit:
                        cert_info_parts.append(f"CUIT: {certificate.alias_id.cuit}")

                    # Agregar common name
                    if certificate.alias_id.common_name:
                        cert_info_parts.append(f"CN: {certificate.alias_id.common_name}")

                    # Agregar ambiente
                    env_label = "Producción" if environment_type == "production" else "Homologación"
                    cert_info_parts.append(f"Ambiente: {env_label}")

                    # Intentar obtener fecha de vencimiento del certificado X.509
                    try:
                        cert_obj = certificate.get_certificate()
                        if cert_obj and hasattr(cert_obj, "not_valid_after_utc"):
                            # cryptography >= 42.0.0
                            expiry_date = cert_obj.not_valid_after_utc
                        elif cert_obj and hasattr(cert_obj, "not_valid_after"):
                            # cryptography < 42.0.0
                            expiry_date = cert_obj.not_valid_after
                        else:
                            expiry_date = None

                        if expiry_date:
                            cert_info_parts.append(f"Vence: {expiry_date.strftime('%d/%m/%Y')}")
                    except Exception as e:
                        _logger.debug(f"No se pudo obtener fecha de vencimiento: {e}")

                    rec.afip_certificate_info = " | ".join(cert_info_parts)
                    _logger.debug(f"Certificate info computed: {rec.afip_certificate_info}")
                else:
                    rec.afip_certificate_info = f"⚠ Sin certificado confirmado ({environment_type})"
                    _logger.debug(f"No confirmed certificate found for {environment_type}")
            except Exception as e:
                _logger.warning(f"Error computing certificate info for journal {rec.name}: {e}")
                rec.afip_certificate_info = f"Error: {str(e)}"

    def test_pyafipws_dummy(self):
        """
        AFIP Description: Método Dummy para verificación de funcionamiento de
        infraestructura (FEDummy)
        """
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        ws = self.company_id.get_connection(afip_ws).connect()
        ws.Dummy()
        title = _("AFIP service %s\n") % afip_ws
        if ws.AppServerStatus == ws.DbServerStatus == ws.AuthServerStatus == "OK":
            notification_type = "success"
        else:
            notification_type = "warning"

        msg = "AppServerStatus: %s DbServerStatus: %s AuthServerStatus: %s" % (
            ws.AppServerStatus,
            ws.DbServerStatus,
            ws.AuthServerStatus,
        )
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title + msg,
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
                "title": _("Great, everything seems fine. The connection did not fail."),
                "type": "success",
                "sticky": True,  # True/False will display for few seconds if false
            },
        }
        return notification
