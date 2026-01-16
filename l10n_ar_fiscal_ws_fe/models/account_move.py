##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import json
import logging
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tools import float_repr

from odoo import _, api, fields, models

base64.encodestring = base64.encodebytes

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    afip_auth_mode = fields.Selection(
        [("CAE", "CAE"), ("CAI", "CAI"), ("CAEA", "CAEA")],
        string="AFIP authorization mode",
        copy=False,
    )
    afip_auth_code = fields.Char(
        copy=False,
        string="CAE/CAI/CAEA Code",
        size=24,
    )
    afip_auth_code_due = fields.Date(
        copy=False,
        string="CAE/CAI/CAEA due Date",
    )
    afip_associated_period_from = fields.Date("AFIP Period from")
    afip_associated_period_to = fields.Date("AFIP Period to")
    afip_qr_code = fields.Char(compute="_compute_qr_code", string="AFIP QR code")
    afip_message = fields.Text(
        string="AFIP Message",
        copy=False,
    )
    afip_xml_request = fields.Text(
        string="AFIP XML Request",
        copy=False,
    )
    afip_xml_response = fields.Text(
        string="AFIP XML Response",
        copy=False,
    )
    afip_result = fields.Selection(
        [("", "n/a"), ("A", "Aceptado"), ("R", "Rechazado"), ("O", "Observado")],
        "Resultado",
        copy=False,
        help="AFIP request result",
    )
    validation_type = fields.Char(
        compute="_compute_validation_type",
    )
    afip_fce_es_anulacion = fields.Boolean(
        string="FCE: Es anulacion?",
        help="Solo utilizado en comprobantes MiPyMEs (FCE) del tipo débito o crédito. Debe informar:\n"
        "- SI: sí el comprobante asociado (original) se encuentra rechazado por el comprador\n"
        "- NO: sí el comprobante asociado (original) NO se encuentra rechazado por el comprador",
    )

    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No")],
        compute="_compute_l10n_ar_payment_foreign_currency",
        store=True,
        readonly=False,
    )
    l10n_ar_currency_code = fields.Char("Currency Code", related="currency_id.name")

    @api.onchange("currency_id", "line_ids")
    @api.depends("currency_id")
    def _compute_l10n_ar_payment_foreign_currency(self):
        self.l10n_ar_payment_foreign_currency = False
        for move in self:
            default_value = move.company_id.l10n_ar_payment_foreign_currency
            if default_value == "account":
                account = move.line_ids.account_id.filtered(lambda x: x.account_type == "asset_receivable")
                default_value = "S" if account.currency_id and account.currency_id != move.company_currency_id else "N"
            move.l10n_ar_payment_foreign_currency = default_value

    # @api.depends('journal_id', 'l10n_latam_document_type_id')
    # def _compute_highest_name(self):
    #     manual_records = self.filtered(lambda move: move.journal_id.arcaws in ['wsfe', 'wsfex', 'wsbfe'])
    #     manual_records.highest_name = ''
    #     super(AccountMove, self - manual_records)._compute_highest_name()

    def _get_starting_sequence(self):
        """If use documents then will create a new starting sequence using the document type code prefix and the
        journal document number with a 8 padding number"""
        if (
            self.journal_id.l10n_latam_use_documents
            and self.company_id.account_fiscal_country_id.code == "AR"
            and self.journal_id.arcaws
        ):
            if self.l10n_latam_document_type_id:
                number = int(self.journal_id._get_last_invoice_number(self.l10n_latam_document_type_id))
                return self._get_formatted_sequence(number)
        return super()._get_starting_sequence()

    # def _set_next_sequence(self):
    #     self.ensure_one()
    #     if self.afip_auth_code and self.journal_id.arcaws and self.afip_xml_response:
    #         invoice_number = get_invoice_number_from_response(self.afip_xml_response, self.journal_id.arcaws)
    #         if invoice_number:
    #             last_sequence = self._get_formatted_sequence(invoice_number)
    #             format, format_values = self._get_sequence_format_param(last_sequence)
    #             format_values["year"] = self[self._sequence_date_field].year % (10 ** format_values["year_length"])
    #             format_values["month"] = self[self._sequence_date_field].month
    #             format_values["seq"] = invoice_number

    #             self[self._sequence_field] = format.format(**format_values)
    #             return
    #     super()._set_next_sequence()

    # TODO Esto se deprecaria si la secuencia solo viene de  result de afip
    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        if (
            self._name == "account.move"
            and self.journal_id.l10n_latam_use_documents
            and self.company_id.account_fiscal_country_id.code == "AR"
            and not self.afip_auth_code
            and self.journal_id.arcaws
            and self.l10n_latam_document_type_id
        ):
            number = int(self.journal_id._get_last_invoice_number(self.l10n_latam_document_type_id))
            res = self._get_formatted_sequence(number)
        else:
            res = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
        return res

    @api.depends("journal_id", "afip_auth_code")
    def _compute_validation_type(self):
        for rec in self:
            if rec.journal_id.arcaws and not rec.afip_auth_code:
                validation_type = self.env["res.company"]._get_environment_type()
                # if we are on homologation env and we dont have certificates
                # we validate only locally
                if validation_type == "homologation":
                    try:
                        rec.company_id.get_key_and_certificate(validation_type)
                    except Exception:
                        validation_type = False
                rec.validation_type = validation_type
            else:
                rec.validation_type = False

    @api.depends("afip_auth_code")
    def _compute_qr_code(self):
        for rec in self:
            if rec.afip_auth_mode in ["CAE", "CAEA"] and rec.afip_auth_code:
                number_parts = self._l10n_ar_get_document_number_parts(
                    rec.l10n_latam_document_number, rec.l10n_latam_document_type_id.code
                )

                qr_dict = {
                    "ver": 1,
                    "fecha": str(rec.invoice_date),
                    "cuit": int(rec.company_id.partner_id.l10n_ar_vat),
                    "ptoVta": number_parts["point_of_sale"],
                    "tipoCmp": int(rec.l10n_latam_document_type_id.code),
                    "nroCmp": number_parts["invoice_number"],
                    "importe": float(float_repr(rec.amount_total, 2)),
                    "moneda": rec.currency_id.l10n_ar_afip_code,
                    "ctz": float(float_repr(rec.invoice_currency_rate, 2)),
                    "tipoCodAut": "E" if rec.afip_auth_mode == "CAE" else "A",
                    "codAut": int(rec.afip_auth_code),
                }
                if len(rec.commercial_partner_id.l10n_latam_identification_type_id) and rec.commercial_partner_id.vat:
                    qr_dict["tipoDocRec"] = int(
                        rec.commercial_partner_id.l10n_latam_identification_type_id.l10n_ar_afip_code
                    )
                    qr_dict["nroDocRec"] = int(rec.commercial_partner_id.vat.replace("-", "").replace(".", ""))
                qr_data = base64.encodestring(json.dumps(qr_dict, indent=None).encode("ascii")).decode("ascii")
                qr_data = str(qr_data).replace("\n", "")
                rec.afip_qr_code = "https://www.afip.gob.ar/fe/qr/?p=%s" % qr_data
            else:
                rec.afip_qr_code = False

    def get_related_invoices_data(self):
        """
        List related invoice information to fill CbtesAsoc.
        """
        self.ensure_one()
        if self.l10n_latam_document_type_id.internal_type == "credit_note":
            return self.reversed_entry_id
        elif self.l10n_latam_document_type_id.internal_type == "debit_note":
            return self.debit_origin_id
        else:
            return self.browse()

    def _post(self, soft=True):
        request_cae_invoices = self.filtered(
            lambda x: x.company_id.country_id.code == "AR"
            and x.is_invoice()
            and x.move_type in ["out_invoice", "out_refund"]
            and x.journal_id.arcaws
            and not x.afip_auth_code
        )
        a_invoices, r_invoices = request_cae_invoices.do_pyafipws_request_cae()
        if len(self) == 1 and r_invoices:
            raise (UserError(r_invoices.afip_message))
        return super(AccountMove, self - r_invoices)._post(soft=soft)

    def do_pyafipws_request_cae(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        a_invoices = r_invoices = self.env["account.move"]

        for inv in self:
            arcaws = inv.journal_id.arcaws
            if not arcaws:
                continue

            # if no validation type and we are on electronic invoice, it means
            # that we are on a testing database without homologation
            # certificates
            if not inv.validation_type:
                msg = (
                    "Factura validada solo localmente por estar en ambiente de homologación sin claves de homologación"
                )
                inv.sudo().write(
                    {
                        "afip_auth_mode": "CAE",
                        "afip_auth_code": "68448767638166",
                        "afip_auth_code_due": inv.invoice_date,
                        "afip_result": "",
                        "afip_message": msg,
                    }
                )
                inv.message_post(body=msg)
                a_invoices += inv
                continue

            # Inicio conexion
            ws = inv.company_id.arca_get_connection(arcaws.code)

            # Preparo los datos
            invoice_info = arcaws.map_invoice_info(inv)
            # Esto no es necesario ahora ya que el numero se obtiene desde el result
            document_number = inv._get_formatted_sequence(
                int(invoice_info["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["CbteDesde"])
            )
            doc_code_prefix = inv.l10n_latam_document_type_id.doc_code_prefix
            if doc_code_prefix and document_number:
                document_number = document_number.split(" ", 1)[-1]
            inv.l10n_latam_document_number = document_number
            # method = last_invoice_info.get("method")
            method = "FECAESolicitar"
            auth = arcaws.ws_parameters.get("auth")

            response = ws.call_arca_service(method, invoice_info, auth=auth)

            # # Request the authorization! (call the AFIP webservice method)
            # vto = None
            # msg = False
            # try:
            #     # Pido autorizacion
            #     inv.pyafipws_request_autorization(ws, arcaws)
            # except Exception as e:
            #     msg = e
            # except Exception:
            #     if ws.Excepcion:
            #         # get the exception already parsed by the helper
            #         msg = ws.Excepcion
            #     else:
            #         # avoid encoding problem when raising error
            #         msg = traceback.format_exception_only(sys.exc_type, sys.exc_value)[0]
            # if msg:
            #     _logger.error(
            #         _("AFIP Validation Error. %s") % msg
            #         + " XML Request: %s XML Response: %s" % (ws.XmlRequest, ws.XmlResponse)
            #     )

            # msg = "\n".join([ws.Obs or "", ws.ErrMsg or ""])

            ws_res = response["FeDetResp"]["FECAEDetResponse"][0]

            if not ws_res.CAE or ws_res.Resultado != "A":
                r_invoices += inv

                vals = {
                    "name": "/",
                    "afip_result": "R",
                    "afip_message": self.l10n_ar_arca_ws_parse_observations(ws_res["Observaciones"]),
                    "afip_xml_request": response.xml_request if "xml_request" in response else "",
                    "afip_xml_response": response.xml_response if "xml_response" in response else "",
                }
                inv.sudo().write(vals)
                inv.env.cr.commit()
                continue
            if "CAEFchVto" in ws_res:
                vto = datetime.strptime(ws_res.CAEFchVto, "%Y%m%d").date()
            elif "FchVencCAE" in ws_res:
                vto = datetime.strptime(ws_res.FchVencCAE, "%Y%m%d").date()

            _logger.info("CAE solicitado con exito. CAE: %s. Resultado %s" % (ws_res.CAE, ws_res.Resultado))
            vals = {
                "afip_auth_mode": "CAE",
                "afip_auth_code": ws_res.CAE,
                "afip_auth_code_due": vto,
                "afip_result": ws_res.Resultado,
                # "afip_message": msg,
                "afip_xml_request": response.xml_request,
                "afip_xml_response": response.xml_response,
            }

            inv.sudo().write(vals)
            inv.env.cr.commit()
            # si obtuvimos el cae hacemos el commit porque estoya no se puede
            # volver atras
            a_invoices += inv
        return (a_invoices, r_invoices)

    def get_pyafipws_currency_rate(self):
        self.ensure_one()
        arcaws = self.journal_id.arcaws
        ws = self.company_id.get_connection(arcaws).connect()
        afipws_get_currency_rate = self.pyafipws_get_currency_rate(ws)
        # TODO: crear cotizacion?
        self.invoice_currency_rate = 1 / float(afipws_get_currency_rate)
        self.message_post(body=_("AFIP currency rate: %s") % afipws_get_currency_rate)

    def wsfe_map_invoice_info(self):
        ws_dict = {}
        next_invoice_number = int(self.journal_id._get_last_invoice_number(self.l10n_latam_document_type_id)) + 1
        amounts = self._l10n_ar_get_amounts()
        arca_document_code = self.partner_id.l10n_latam_identification_type_id.l10n_ar_afip_code
        ws_dict["FeCAEReq"] = {}

        ws_dict["FeCAEReq"]["FeCabReq"] = {
            "CantReg": 1,
            "PtoVta": self.journal_id.l10n_ar_afip_pos_number,
            "CbteTipo": int(self.l10n_latam_document_type_id.code),
        }
        ws_dict["FeCAEReq"]["FeDetReq"] = {
            "FECAEDetRequest": {
                "Concepto": int(self.l10n_ar_afip_concept),
                "DocTipo": int(arca_document_code),
                "DocNro": int(self.partner_id.vat),
                "CbteDesde": next_invoice_number,
                "CbteHasta": next_invoice_number,
                "CbteFch": self.invoice_date.strftime("%Y%m%d"),
                "ImpTotal": float_repr(self.amount_total, 2),
                "ImpTotConc": float_repr(amounts["vat_untaxed_base_amount"], 2),
                "ImpNeto": float_repr(
                    self.amount_untaxed
                    if self.l10n_latam_document_type_id.l10n_ar_letter == "C"
                    else amounts["vat_taxable_amount"],
                    2,
                ),
                "ImpOpEx": float_repr(amounts["vat_exempt_base_amount"], 2),
                "ImpTrib": float_repr(amounts["not_vat_taxes_amount"], 2),
                "ImpIVA": float_repr(amounts["vat_amount"], 2),
                "FchVtoPago": None,
                "CbtesAsoc": None,
                "Compradores": None,
                "Iva": None,
                "MonId": self.currency_id.l10n_ar_afip_code,
                "MonCotiz": 1 / self.invoice_currency_rate or 1,
                "CanMisMonExt": self.l10n_ar_payment_foreign_currency,
                "CondicionIVAReceptorId": int(self.partner_id.l10n_ar_afip_responsibility_type_id.code),
            }
        }
        if vats := self._get_vat():
            for vat in vats:
                AlicIva = []
                if "BaseImp" in vat and "Importe" in vat:
                    AlicIva.append(
                        {
                            "Id": vat["Id"],
                            "BaseImp": float_repr(vat["BaseImp"], precision_digits=2),
                            "Importe": float_repr(vat["Importe"], precision_digits=2),
                        }
                    )
            ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["Iva"] = {"AlicIva": AlicIva}

        if self.afip_associated_period_from and self.afip_associated_period_to:
            ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["PeriodoAsoc"]["FchDesde"] = (
                self.afip_associated_period_from.strftime("%Y%m%d")
            )
            ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["PeriodoAsoc"]["FchHasta"] = (
                self.afip_associated_period_to.strftime("%Y%m%d")
            )
        elif related_invoice_ids := self.get_related_invoices_data():
            CbtesAsoc = []
            for related_invoice in related_invoice_ids:
                doc_number_parts = self._l10n_ar_get_document_number_parts(
                    related_invoice.l10n_latam_document_number,
                    related_invoice.l10n_latam_document_type_id.code,
                )

                CbtesAsoc.append(
                    {
                        "CbteAsoc": {
                            "Tipo": related_invoice.l10n_latam_document_type_id.code,
                            "PtoVta": doc_number_parts["point_of_sale"],
                            "Nro": doc_number_parts["invoice_number"],
                            "Cuit": self.company_id.vat,
                            "CbteFch": related_invoice.invoice_date.strftime("%Y%m%d"),
                        }
                    }
                )
            ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["CbtesAsoc"] = CbtesAsoc

        if self.l10n_ar_afip_concept != "1":
            ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"].update(
                {
                    "FchServDesde": self.l10n_ar_afip_service_start.strftime("%Y%m%d"),
                    "FchServHasta": self.l10n_ar_afip_service_end.strftime("%Y%m%d"),
                }
            )
            if arca_document_code in ("201", "206", "211"):
                ws_dict["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]["FchVtoPago"] = (
                    self.invoice_date_due or self.invoice_date
                ).strftime("%Y%m%d")
        return ws_dict

    def l10n_ar_arca_ws_parse_observations(self, observations):
        """
        Parse ARCA observations from ARCA WS response
        :param observations: list of observation dicts
        :return: string with formatted observations
        """
        obs_msgs = []
        for obs in observations["Obs"]:
            obs_code = obs["Code"]
            obs_msg = obs["Msg"]
            if obs_code and obs_msg:
                obs_msgs.append("(%s) %s" % (obs_code, obs_msg))
        return "\n".join(obs_msgs)
