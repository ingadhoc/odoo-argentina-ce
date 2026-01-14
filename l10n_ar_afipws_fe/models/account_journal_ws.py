##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# TODO: unir AccountJournalWs con AccountJournal ya que ambos heredan account.journal
# pylint: disable=R8180

# Coloco las funciones de WS aqui para limpiar el codigo
# de funciones que no ayudan a su lectura


class AccountJournalWs(models.Model):
    _inherit = "account.journal"

    def get_pyafipws_post_invoice_numbers(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected on point of sale %s") % (self.name))
        ws = self.company_id.get_connection(afip_ws).connect()
        ret = getattr(self, "%s_pyafipws_cuit_document_classes" % afip_ws)(ws)

        # Convertir string "1:Desc1,2:Desc2,..." a lista
        if ret:
            document_list = ret.split(",")
        else:
            document_list = []

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
        html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Últimos Números de Comprobante en AFIP</h4>')
        html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">')
        html_parts.append(f"<p><strong>Punto de Venta:</strong> {self.l10n_ar_afip_pos_number:04d}</p>")
        html_parts.append("</div>")

        html_parts.append('<div style="margin: 10px 0;">')
        html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
        html_parts.append('<thead><tr style="background: #007bff; color: white;">')
        html_parts.append('<th style="padding: 8px; text-align: left;">Tipo</th>')
        html_parts.append('<th style="padding: 8px; text-align: left;">Descripción</th>')
        html_parts.append('<th style="padding: 8px; text-align: right;">Último Nro</th>')
        html_parts.append("</tr></thead><tbody>")

        for document_line in document_list:
            if not document_line or not document_line.strip():
                continue

            # El formato esperado es "ID:Descripción" o solo "ID"
            if ":" in document_line:
                parts = document_line.split(":", 1)
                doc_id = parts[0].strip()
                doc_desc = parts[1].strip() if len(parts) > 1 else _("Sin descripción")
            elif "," in document_line:
                parts = document_line.split(",", 1)
                doc_id = parts[0].strip()
                doc_desc = parts[1].strip() if len(parts) > 1 else _("Sin descripción")
            else:
                doc_id = document_line.strip()
                doc_desc = _("Sin descripción")

            if not doc_id:
                continue

            # Validar que doc_id sea numérico (AFIP espera int)
            try:
                doc_id_int = int(doc_id)
                doc_id_clean = str(doc_id_int)
            except (ValueError, TypeError):
                _logger.warning(f"Tipo de comprobante con ID no numérico: '{doc_id}'")
                continue

            # call the webservice method to get the last invoice at AFIP:
            try:
                if hasattr(self, "%s_get_pyafipws_last_invoice" % afip_ws):
                    obj_document_type = type("obj", (object,), {"code": doc_id_clean})
                    last_number = getattr(self, "%s_get_pyafipws_last_invoice" % afip_ws)(
                        self.l10n_ar_afip_pos_number, obj_document_type, ws
                    )
                else:
                    raise UserError(_("AFIP WS %s not implemented") % afip_ws)

                formatted_number = "%05d-%08d" % (self.l10n_ar_afip_pos_number, int(last_number))
                html_parts.append('<tr style="border-bottom: 1px solid #ddd;">')
                html_parts.append(f'<td style="padding: 5px; font-weight: bold; color: #007bff;">{doc_id_clean}</td>')
                html_parts.append(f'<td style="padding: 5px;">{doc_desc}</td>')
                html_parts.append(
                    f'<td style="padding: 5px; text-align: right; font-family: monospace;">{formatted_number}</td>'
                )
                html_parts.append("</tr>")
            except Exception as e:
                _logger.warning(f"Error obteniendo último número para tipo {doc_id_clean}: {str(e)}")
                html_parts.append('<tr style="border-bottom: 1px solid #ddd; background: #fff3cd;">')
                html_parts.append(f'<td style="padding: 5px; font-weight: bold; color: #856404;">{doc_id_clean}</td>')
                html_parts.append(f'<td style="padding: 5px;">{doc_desc}</td>')
                html_parts.append(f'<td style="padding: 5px; text-align: right; color: #856404;">Error: {str(e)}</td>')
                html_parts.append("</tr>")

        html_parts.append("</tbody></table></div>")

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
            {"title": _("Últimos Números de Comprobante AFIP"), "html_content": html_content}
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Últimos Números de Comprobante AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def get_pyafipws_last_invoice(self, document_type):
        self.ensure_one()
        company = self.company_id
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected on point of sale %s") % (self.name))
        ws = company.get_connection(afip_ws).connect()
        # call the webservice method to get the last invoice at AFIP:
        try:
            if hasattr(self, "%s_get_pyafipws_last_invoice" % afip_ws):
                last = getattr(self, "%s_get_pyafipws_last_invoice" % afip_ws)(
                    self.l10n_ar_afip_pos_number, document_type, ws
                )
            else:
                raise UserError(_("AFIP WS %s not implemented") % afip_ws)
            return last

        except ValueError as error:
            _logger.warning("exception in get_pyafipws_last_invoice: %s" % (str(error)))
            if "The read operation timed out" in str(error):
                raise UserError(_("Servicio AFIP Ocupado reintente en unos minutos"))
            else:
                raise UserError(
                    _("Hubo un error al conectarse a AFIP, contacte a su" " proveedor de Odoo para mas información")
                )

    def test_pyafipws_point_of_sales(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        ws = self.company_id.get_connection(afip_ws).connect()
        if hasattr(self, "%s_pyafipws_point_of_sales" % afip_ws):
            ret = getattr(self, "%s_pyafipws_point_of_sales" % afip_ws)(ws)
        else:
            raise UserError(_("Get point of sale for ws %s is not implemented yet") % (afip_ws))

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']

        # Puntos de venta obtenidos
        if ret:
            puntos = ret.split() if isinstance(ret, str) else ret
            html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Puntos de Venta Habilitados</h4>')
            html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">')
            html_parts.append(
                "<strong>Puntos de Venta:</strong> "
                + ", ".join(
                    [
                        f'<span style="background:#007bff;color:white;padding:2px 8px;border-radius:3px;margin:0 3px;">{p}</span>'
                        for p in puntos
                    ]
                )
            )
            html_parts.append("</div>")
        else:
            html_parts.append('<h4 style="color: #ffc107;">⚠ Sin Puntos de Venta</h4>')
            html_parts.append("<p>No se obtuvieron puntos de venta desde AFIP</p>")

        # Respuesta detallada de AFIP
        if hasattr(ws, "RawResponse") and ws.RawResponse:
            html_parts.append('<hr style="margin: 15px 0; border: 1px solid #ddd;">')
            html_parts.append('<h4 style="margin: 10px 0;">📋 Respuesta Completa de AFIP</h4>')
            html_parts.append(
                '<div style="background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 300px;">'
            )
            html_parts.append('<pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word;">')
            html_parts.append(str(ws.RawResponse).replace("<", "&lt;").replace(">", "&gt;"))
            html_parts.append("</pre></div>")

        # Errores y observaciones
        error_html = []

        if ws.Excepcion and ws.Excepcion.strip():
            error_html.append(
                '<div style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_html.append(f"<strong>❌ Excepción:</strong> {ws.Excepcion}")
            error_html.append("</div>")

        if ws.ErrMsg and ws.ErrMsg.strip():
            error_html.append(
                '<div style="background: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_html.append(f"<strong>❌ Error:</strong> {ws.ErrMsg}")
            error_html.append("</div>")

        if ws.Obs and ws.Obs.strip():
            error_html.append(
                '<div style="background: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin: 5px 0;">'
            )
            error_html.append(f"<strong>ℹ Observaciones:</strong> {ws.Obs}")
            error_html.append("</div>")

        if error_html:
            html_parts.append('<hr style="margin: 15px 0; border: 1px solid #ddd;">')
            html_parts.extend(error_html)

        html_parts.append("</div>")
        html_content = "".join(html_parts)

        # Crear wizard con el contenido
        wizard = self.env["afip.response.wizard"].create(
            {"title": _("Consulta de Puntos de Venta AFIP"), "html_content": html_content}
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Consulta de Puntos de Venta AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def get_pyafipws_cuit_document_classes(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        ws = self.company_id.get_connection(afip_ws).connect()
        if hasattr(self, "%s_pyafipws_cuit_document_classes" % afip_ws):
            ret = getattr(self, "%s_pyafipws_cuit_document_classes" % afip_ws)(ws)
        else:
            raise UserError(_("Get document types for ws %s is not implemented yet") % (afip_ws))

        # ret es un string "Id1:Desc1,Id2:Desc2,..."
        # Convertirlo a lista para mostrar mejor
        if ret:
            tipos_list = ret.split(",")
        else:
            tipos_list = []

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
        html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Tipos de Comprobante Autorizados</h4>')

        if tipos_list:
            html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">')
            html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
            html_parts.append('<thead><tr style="background: #007bff; color: white;">')
            html_parts.append('<th style="padding: 8px; text-align: left;">ID</th>')
            html_parts.append('<th style="padding: 8px; text-align: left;">Descripción</th>')
            html_parts.append("</tr></thead><tbody>")
            for tipo in tipos_list:
                if ":" in tipo:
                    tipo_id, tipo_desc = tipo.split(":", 1)
                    html_parts.append('<tr style="border-bottom: 1px solid #ddd;">')
                    html_parts.append(f'<td style="padding: 5px; font-weight: bold; color: #007bff;">{tipo_id}</td>')
                    html_parts.append(f'<td style="padding: 5px;">{tipo_desc}</td>')
                    html_parts.append("</tr>")
            html_parts.append("</tbody></table></div>")
            html_parts.append(
                f'<p style="color: #6c757d; margin-top: 10px;"><strong>Total:</strong> {len(tipos_list)} tipos de comprobante</p>'
            )
        else:
            html_parts.append('<p style="color: #ffc107;">No se obtuvieron tipos de comprobante</p>')

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
            {"title": _("Tipos de Comprobante AFIP"), "html_content": html_content}
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Tipos de Comprobante AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def get_pyafipws_zonas(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        ws = self.company_id.get_connection(afip_ws).connect()
        if hasattr(self, "%s_pyafipws_zonas" % afip_ws):
            ret = getattr(self, "%s_pyafipws_zonas" % afip_ws)(ws)
        else:
            raise UserError(_("Get zonas for ws %s is not implemented yet") % (afip_ws))

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
        html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Zonas AFIP</h4>')

        if ret:
            html_parts.append('<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0;">')
            html_parts.append('<ul style="margin: 5px 0; padding-left: 20px;">')
            for zona in ret:
                html_parts.append(f'<li style="margin: 3px 0;">{zona}</li>')
            html_parts.append("</ul></div>")
            html_parts.append(f'<p style="color: #6c757d;"><strong>Total:</strong> {len(ret)} zonas</p>')
        else:
            html_parts.append('<p style="color: #ffc107;">No se obtuvieron zonas desde AFIP</p>')

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
        wizard = self.env["afip.response.wizard"].create({"title": _("Zonas AFIP"), "html_content": html_content})

        return {
            "type": "ir.actions.act_window",
            "name": _("Zonas AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def get_pyafipws_NCM(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        ws = self.company_id.get_connection(afip_ws).connect()
        if hasattr(self, "%s_pyafipws_NCM" % afip_ws):
            ret = getattr(self, "%s_pyafipws_NCM" % afip_ws)(ws)
        else:
            raise UserError(_("Get NCM for ws %s is not implemented yet") % (afip_ws))

        # Construir mensaje HTML estructurado
        html_parts = ['<div style="font-family: monospace; font-size: 12px;">']
        html_parts.append('<h4 style="color: #28a745; margin: 10px 0;">✓ Nomenclador Común del Mercosur (NCM)</h4>')

        if ret:
            html_parts.append(
                '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin: 10px 0; max-height: 400px; overflow-y: auto;">'
            )
            html_parts.append('<ul style="margin: 5px 0; padding-left: 20px;">')
            for ncm in ret:
                html_parts.append(f'<li style="margin: 3px 0; font-size: 11px;">{ncm}</li>')
            html_parts.append("</ul></div>")
            html_parts.append(f'<p style="color: #6c757d;"><strong>Total:</strong> {len(ret)} códigos NCM</p>')
        else:
            html_parts.append('<p style="color: #ffc107;">No se obtuvieron códigos NCM desde AFIP</p>')

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
            {"title": _("Nomenclador Común del Mercosur (NCM)"), "html_content": html_content}
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("NCM AFIP"),
            "res_model": "afip.response.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    # Divido las funciones por WS aunque repita codigo
    # Muchos IF hacen el codigo dificil de leer

    def wsbfe_pyafipws_NCM(self, ws):
        return ws.GetParamNCM()

    def wsbfe_pyafipws_zonas(self, ws):
        return ws.GetParamZonas()

    def wsfex_pyafipws_cuit_document_classes(self, ws):
        return ws.GetParamTipoCbte(sep=",")

    def wsfe_pyafipws_cuit_document_classes(self, ws):
        return ws.ParamGetTiposCbte(sep=",")

    def wsbfe_pyafipws_cuit_document_classes(self, ws):
        return ws.GetParamTipoCbte()

    def wsfex_pyafipws_point_of_sales(self, ws):
        return ws.GetParamPtosVenta()

    def wsfe_pyafipws_point_of_sales(self, ws):
        return ws.ParamGetPtosVenta(sep=" ")

    def wsfe_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws):
        return ws.CompUltimoAutorizado(document_type.code, l10n_ar_afip_pos_number)

    def wsmtxca_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws):
        return ws.CompUltimoAutorizado(document_type.code, l10n_ar_afip_pos_number)

    def wsfex_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws):
        return ws.GetLastCMP(document_type.code, l10n_ar_afip_pos_number)

    def wsbfe_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws):
        return ws.GetLastCMP(document_type.code, l10n_ar_afip_pos_number)
