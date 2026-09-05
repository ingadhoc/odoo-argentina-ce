##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from markupsafe import Markup
from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# TODO: unir AccountJournalWs con AccountJournal ya que ambos heredan account.journal
# pylint: disable=R8180

# Coloco las funciones de WS aqui para limpiar el codigo
# de funciones que no ayudan a su lectura


class AccountJournalWs(models.Model):
    _inherit = "account.journal"

    def _afip_ws_error_message(self, ws, result=None):
        """Return AFIP error text from a SOAP result dict and pyafipws attributes."""
        msgs = []
        for error in (result or {}).get("Errors") or []:
            err = error.get("Err") or error
            code = err.get("Code")
            msg = err.get("Msg")
            if code or msg:
                msgs.append("%s: %s" % (code, msg))
        for attr in ("ErrMsg", "Excepcion", "Obs"):
            value = getattr(ws, attr, None)
            if value and str(value) not in msgs:
                msgs.append(str(value))
        return "\n".join(filter(None, msgs))

    def _afip_ws_missing_result_error(self, ws, result=None):
        """Explain a missing ResultGet, including environment mismatch hints."""
        details = self._afip_ws_error_message(ws, result)
        hint = _(
            "AFIP did not return the expected data. Dummy Test only checks that "
            "WSFE servers are up. Use a homologation certificate with environment "
            "Homologation, or a production certificate with environment Production. "
            "The CUIT must have WSFE and the point of sale enabled in that same environment."
        )
        if details:
            return "%s\n\n%s" % (details, hint)
        return hint

    def get_pyafipws_post_invoice_numbers(self):
        for journal_id in self:
            msg = []
            afip_ws = journal_id.afip_ws
            if not afip_ws:
                raise UserError(_("No AFIP WS selected on point of sale %s") % (journal_id.name))
            ws = journal_id.company_id.get_connection(afip_ws).connect()
            ret = getattr(self, "%s_pyafipws_cuit_document_classes" % afip_ws)(ws)

            for document_line in ret:
                document_type = document_line.split(",")
                # call the webservice method to get the last invoice at AFIP:
                if hasattr(self, "%s_get_pyafipws_last_invoice" % afip_ws):
                    obj_document_type = type("obj", (object,), {"code": document_type[0]})
                    document_type.append(
                        getattr(self, "%s_get_pyafipws_last_invoice" % afip_ws)(
                            journal_id.l10n_ar_afip_pos_number, obj_document_type, ws
                        )
                    )
                else:
                    raise UserError(_("AFIP WS %s not implemented") % afip_ws)
                msg.append("%s %05d-%08d" % (document_type[1], int(document_type[0]), int(document_type[-1])))
            journal_id.message_post(body=Markup("<br/>\n").join(msg))

    def get_pyafipws_last_invoice(self, document_type):
        self.ensure_one()
        company = self.company_id
        afip_ws = self.afip_ws
        if not afip_ws:
            return _("No AFIP WS selected on point of sale %s") % (self.name)
        ws = company.get_connection(afip_ws).connect()
        # call the webservice method to get the last invoice at AFIP:
        try:
            if hasattr(self, "%s_get_pyafipws_last_invoice" % afip_ws):
                last = getattr(self, "%s_get_pyafipws_last_invoice" % afip_ws)(
                    self.l10n_ar_afip_pos_number, document_type, ws
                )
            else:
                return _("AFIP WS %s not implemented") % afip_ws
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
        notification_type = "success"
        if hasattr(self, "%s_pyafipws_point_of_sales" % afip_ws):
            ret = getattr(self, "%s_pyafipws_point_of_sales" % afip_ws)(ws)
        else:
            raise UserError(_("Get point of sale for ws %s is not implemented yet") % (afip_ws))
        if not ret:
            notification_type = "warning"
            msg = self._afip_ws_missing_result_error(ws)
        else:
            msg = _(" %s %s") % (
                ". ".join(ret),
                " - ".join([ws.Excepcion, ws.ErrMsg, ws.Obs]),
            )
        title = _("Enabled Point Of Sales on AFIP\n")

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
        msg = _("Authorized Document Clases on AFIP\n%s\n. \nObservations: %s") % (
            "<br/> ".join(ret),
            ".<br/>".join([ws.Excepcion, ws.ErrMsg, ws.Obs]),
        )

        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": Markup(msg),
                "type": "success",
                "sticky": True,  # True/False will display for few seconds if false
            },
        }

        return notification

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
        msg = _("Zonas on AFIP\n%s\n. \nObservations: %s") % (
            "\n ".join(ret),
            ".\n".join([ws.Excepcion, ws.ErrMsg, ws.Obs]),
        )
        raise UserError(msg)

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
        msg = _("Zonas on AFIP\n%s\n. \nObservations: %s") % (
            "\n ".join(ret),
            ".\n".join([ws.Excepcion, ws.ErrMsg, ws.Obs]),
        )
        raise UserError(msg)

    # Divido las funciones por WS aunque repita codigo
    # Muchos IF hacen el codigo dificil de leer

    def wsbfe_pyafipws_NCM(self, ws):
        return ws.GetParamNCM()

    def wsbfe_pyafipws_zonas(self, ws):
        return ws.GetParamZonas()

    def wsfex_pyafipws_cuit_document_classes(self, ws):
        return ws.GetParamTipoCbte(sep=",")

    def wsfe_pyafipws_cuit_document_classes(self, ws):
        try:
            ret = ws.ParamGetTiposCbte(sep=",")
        except (KeyError, TypeError):
            soap = {}
            try:
                soap = ws.client.FEParamGetTiposCbte(
                    Auth={"Token": ws.Token, "Sign": ws.Sign, "Cuit": ws.Cuit},
                )
            except Exception:
                _logger.warning("Could not re-read FEParamGetTiposCbte response", exc_info=True)
            res = soap.get("FEParamGetTiposCbteResult") or {}
            raise UserError(self._afip_ws_missing_result_error(ws, res)) from None
        if not ret:
            raise UserError(self._afip_ws_missing_result_error(ws))
        return ret

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
