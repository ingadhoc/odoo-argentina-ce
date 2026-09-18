##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from markupsafe import Markup
from odoo import models, _
import logging
from odoo.exceptions import UserError
import zeep.helpers

_logger = logging.getLogger(__name__)

# Coloco las funciones de WS aqui para limpiar el codigo
# de funciones que no ayudan a su lectura


class AccountJournalWs(models.Model):
    _inherit = "account.journal"

    # ---------------- API nueva zeep ----------------

    def get_afip_last_invoice(self, document_type):
        """Último comprobante autorizado en AFIP vía zeep."""
        self.ensure_one()
        company = self.company_id
        afip_ws = self.afip_ws
        if not afip_ws:
            return _("No AFIP WS selected on point of sale %s") % (self.name)
        connection = company.get_connection(afip_ws)
        try:
            client, auth, transport = connection.connect()
            if afip_ws == "wsfe":
                response = client.service.FECompUltimoAutorizado(auth, self.l10n_ar_afip_pos_number, document_type.code)
                if getattr(response, "Errors", None):
                    raise UserError(_("AFIP error: %s") % (response.Errors,))
                return response.CbteNro
            elif afip_ws == "wsfex":
                data = auth.copy()
                data.update({"Cbte_Tipo": document_type.code, "Pto_venta": self.l10n_ar_afip_pos_number})
                response = client.service.FEXGetLast_CMP(Auth=data)
                if response.FEXErr.ErrCode != 0 or response.FEXErr.ErrMsg != "OK":
                    raise UserError(_("AFIP error: %s - %s") % (response.FEXErr.ErrCode, response.FEXErr.ErrMsg))
                return response.FEXResult_LastCMP.Cbte_nro
            elif afip_ws == "wsbfe":
                data = auth.copy()
                data.update({"Tipo_cbte": document_type.code, "Pto_venta": self.l10n_ar_afip_pos_number})
                response = client.service.BFEGetLast_CMP(Auth=data)
                if response.BFEErr.ErrCode != 0 or response.BFEErr.ErrMsg != "OK":
                    raise UserError(_("AFIP error: %s - %s") % (response.BFEErr.ErrCode, response.BFEErr.ErrMsg))
                return response.BFEResult_LastCMP.Cbte_nro
            else:
                return _("AFIP WS %s not implemented") % afip_ws
        except UserError:
            raise
        except ValueError as error:
            _logger.warning("exception in get_afip_last_invoice: %s" % (str(error)))
            if "The read operation timed out" in str(error):
                raise UserError(_("Servicio AFIP Ocupado reintente en unos minutos"))
            raise UserError(
                _(
                    "Hubo un error al conectarse a AFIP, contacte a su"
                    " proveedor de Odoo para mas información"
                )
            )

    def _zeep_call_dummy(self, client, auth, afip_ws):
        if afip_ws == "wsfe":
            return client.service.FEDummy()
        elif afip_ws == "wsfex":
            return client.service.FEXDummy()
        elif afip_ws == "wsbfe":
            return client.service.BFEDummy()
        elif afip_ws == "wscdc":
            return client.service.WSCDCDummy()
        raise UserError(_("Dummy not implemented for ws %s") % afip_ws)

    # ---------------- Compatibilidad pyafipws (wrappers) ----------------
    # Se mantienen los nombres viejos para facilitar el PR y no romper
    # llamadas externas; implementan vía zeep.

    def get_pyafipws_last_invoice(self, document_type):
        return self.get_afip_last_invoice(document_type)

    def get_pyafipws_post_invoice_numbers(self):
        for journal_id in self:
            msg = []
            afip_ws = journal_id.afip_ws
            if not afip_ws:
                raise UserError(_("No AFIP WS selected on point of sale %s") % (journal_id.name))
            connection = journal_id.company_id.get_connection(afip_ws)
            client, auth, transport = connection.connect()
            if afip_ws == "wsfe":
                response = client.service.FEParamGetTiposCbte(auth)
                items = ["%s,%s" % (t.Id, t.Desc) for t in response.ResultGet.CbteTipo]
            elif afip_ws in ("wsfex", "wsbfe"):
                response = client.service.FEXGetPARAM_Tipo_Cbte(auth) if afip_ws == "wsfex" else client.service.BFEGetPARAM_Tipo_Cbte(auth)
                items = ["%s,%s" % (t.Id, t.Desc) for t in zeep.helpers.serialize_object(response, dict).get("ResultGet", {}).get("Cbte_Tipo", [])]
            else:
                raise UserError(_("AFIP WS %s not implemented") % afip_ws)
            for document_line in items:
                document_type = document_line.split(",")
                obj_document_type = type("obj", (object,), {"code": document_type[0]})
                last = journal_id.get_afip_last_invoice(obj_document_type)
                msg.append("%s %05d-%08d" % (document_type[1], int(document_type[0]), int(last or 0)))
            journal_id.message_post(body=Markup("<br/>\n").join(msg))

    def test_pyafipws_point_of_sales(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        connection = self.company_id.get_connection(afip_ws)
        client, auth, transport = connection.connect()
        if afip_ws == "wsfe":
            response = client.service.FEParamGetPtosVenta(auth)
            ret = ["%s" % p.Nro for p in response.ResultGet.PtoVenta]
        elif afip_ws == "wsfex":
            response = client.service.FEXGetPARAM_PtoVenta(auth)
            ret = ["%s" % p.PtoVenta for p in zeep.helpers.serialize_object(response, dict)["FEXResultGet"]["PtoVenta"]]
        else:
            raise UserError(_("Get point of sale for ws %s is not implemented yet") % (afip_ws))
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Enabled Point Of Sales on AFIP\n") + " ".join(ret),
                "type": "success",
                "sticky": True,
            },
        }
        return notification

    def get_pyafipws_cuit_document_classes(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        connection = self.company_id.get_connection(afip_ws)
        client, auth, transport = connection.connect()
        if afip_ws == "wsfe":
            response = client.service.FEParamGetTiposCbte(auth)
            ret = ["%s,%s" % (t.Id, t.Desc) for t in response.ResultGet.CbteTipo]
        elif afip_ws == "wsfex":
            response = client.service.FEXGetPARAM_Tipo_Cbte(auth)
            ret = ["%s" % t for t in response.FEXResultGet.Cbte_Tipo]
        elif afip_ws == "wsbfe":
            response = client.service.BFEGetPARAM_Tipo_Cbte(auth)
            ret = ["%s" % t for t in response.BFEResultGet.Cbte_Tipo]
        else:
            raise UserError(_("Get document types for ws %s is not implemented yet") % (afip_ws))
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": Markup(_("Authorized Document Clases on AFIP\n%s") % ("<br/> ".join(ret))),
                "type": "success",
                "sticky": True,
            },
        }
        return notification

    def get_pyafipws_zonas(self):
        raise UserError(_("Use zeep BFEGetPARAM_Zonas via get_afip_zonas (wsbfe)"))

    def get_pyafipws_NCM(self):
        raise UserError(_("Use zeep BFEGetPARAM_NCM via get_afip_ncm (wsbfe)"))

    # Métodos legacy por WS (ya no reciben objeto pyafipws `ws`)
    def wsbfe_pyafipws_NCM(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsbfe").connect()
        return client.service.BFEGetPARAM_NCM(auth)

    def wsbfe_pyafipws_zonas(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsbfe").connect()
        return client.service.BFEGetPARAM_Zonas(auth)

    def wsfex_pyafipws_cuit_document_classes(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsfex").connect()
        return client.service.FEXGetPARAM_Tipo_Cbte(auth)

    def wsfe_pyafipws_cuit_document_classes(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsfe").connect()
        return client.service.FEParamGetTiposCbte(auth)

    def wsbfe_pyafipws_cuit_document_classes(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsbfe").connect()
        return client.service.BFEGetPARAM_Tipo_Cbte(auth)

    def wsfex_pyafipws_point_of_sales(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsfex").connect()
        return client.service.FEXGetPARAM_PtoVenta(auth)

    def wsfe_pyafipws_point_of_sales(self, ws=None):
        self.ensure_one()
        client, auth, transport = self.company_id.get_connection("wsfe").connect()
        return client.service.FEParamGetPtosVenta(auth)

    def wsfe_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws=None):
        return self.get_afip_last_invoice(document_type)

    def wsmtxca_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws=None):
        raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))

    def wsfex_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws=None):
        return self.get_afip_last_invoice(document_type)

    def wsbfe_get_pyafipws_last_invoice(self, l10n_ar_afip_pos_number, document_type, ws=None):
        return self.get_afip_last_invoice(document_type)
