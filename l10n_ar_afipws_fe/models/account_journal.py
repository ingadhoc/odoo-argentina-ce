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

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']

        # Estado de servidores
        all_ok = ws.AppServerStatus == ws.DbServerStatus == ws.AuthServerStatus == "OK"
        if all_ok:
            html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Conexión Exitosa con AFIP</h4>')
        else:
            html_parts.append('<h4 style="color: #dc3545; margin: 10px 0;">⚠ Problemas de Conexión</h4>')

        html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">')
        html_parts.append(f"<p><strong>Servicio:</strong> {afip_ws}</p>")

        # Estado de cada servidor
        def status_badge(status):
            if status == "OK":
                return (
                    f'<span style="background:#28a745;color:white;padding:3px 10px;border-radius:3px;">{status}</span>'
                )
            else:
                return (
                    f'<span style="background:#dc3545;color:white;padding:3px 10px;border-radius:3px;">{status}</span>'
                )

        html_parts.append(f"<p><strong>App Server:</strong> {status_badge(ws.AppServerStatus)}</p>")
        html_parts.append(f"<p><strong>Database Server:</strong> {status_badge(ws.DbServerStatus)}</p>")
        html_parts.append(f"<p><strong>Auth Server:</strong> {status_badge(ws.AuthServerStatus)}</p>")
        html_parts.append("</div>")

        # Agregar errores/observaciones si existen
        error_parts = []
        if ws.Excepcion and ws.Excepcion.strip():
            error_parts.append(
                '<div style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_parts.append(f"<strong>❌ Excepción:</strong> {ws.Excepcion}</div>")
        if ws.ErrMsg and ws.ErrMsg.strip():
            error_parts.append(
                '<div style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_parts.append(f"<strong>❌ Error:</strong> {ws.ErrMsg}</div>")
        if ws.Obs and ws.Obs.strip():
            error_parts.append(
                '<div style="background: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_parts.append(f"<strong>ℹ Observaciones:</strong> {ws.Obs}</div>")

        if error_parts:
            html_parts.append('<hr style="margin: 15px 0; border: 1px solid #ddd;">')
            html_parts.extend(error_parts)

        html_parts.append("</div>")
        html_content = "".join(html_parts)

        # Crear wizard con el contenido
        wizard = self.env["afip.response.wizard"].create(
            {"title": _("Test de Conexión AFIP - %s") % afip_ws, "html_content": html_content}
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Test de Conexión AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_get_connection(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        try:
            ws = self.company_id.get_connection(afip_ws).connect()

            # Construir mensaje HTML estructurado
            html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
            html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Conexión Exitosa</h4>')
            html_parts.append(
                '<div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin: 10px 0;">'
            )
            html_parts.append(
                '<p style="margin: 0; font-size: 14px;">La conexión con AFIP se estableció correctamente.</p>'
            )
            html_parts.append(f'<p style="margin: 5px 0 0 0;"><strong>Servicio:</strong> {afip_ws}</p>')
            html_parts.append("</div>")

            # Si el ws tiene información de estado, mostrarla
            if hasattr(ws, "AppServerStatus"):
                html_parts.append('<hr style="margin: 15px 0; border: 1px solid #ddd;">')
                html_parts.append('<h4 style="margin: 10px 0;">Estado de Servidores</h4>')
                html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">')
                if hasattr(ws, "AppServerStatus") and ws.AppServerStatus:
                    html_parts.append(f"<p>App Server: <strong>{ws.AppServerStatus}</strong></p>")
                if hasattr(ws, "DbServerStatus") and ws.DbServerStatus:
                    html_parts.append(f"<p>Database Server: <strong>{ws.DbServerStatus}</strong></p>")
                if hasattr(ws, "AuthServerStatus") and ws.AuthServerStatus:
                    html_parts.append(f"<p>Auth Server: <strong>{ws.AuthServerStatus}</strong></p>")
                html_parts.append("</div>")

            html_parts.append("</div>")
            html_content = "".join(html_parts)

            # Crear wizard con el contenido
            wizard = self.env["afip.response.wizard"].create(
                {"title": _("Obtener Conexión AFIP"), "html_content": html_content}
            )

            return {
                "type": "ir.actions.act_window",
                "name": _("Obtener Conexión AFIP"),
                "res_model": "afip.response.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }
        except Exception as e:
            # En caso de error, también mostrarlo en wizard
            html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
            html_parts.append('<h4 style="color: #dc3545; margin: 10px 0;">❌ Error de Conexión</h4>')
            html_parts.append(
                '<div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 10px 0;">'
            )
            html_parts.append(f"<p><strong>Error:</strong> {str(e)}</p>")
            html_parts.append(f"<p><strong>Servicio:</strong> {afip_ws}</p>")
            html_parts.append("</div>")
            html_parts.append("</div>")
            html_content = "".join(html_parts)

            wizard = self.env["afip.response.wizard"].create(
                {"title": _("Error de Conexión AFIP"), "html_content": html_content}
            )

            return {
                "type": "ir.actions.act_window",
                "name": _("Error de Conexión AFIP"),
                "res_model": "afip.response.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }
