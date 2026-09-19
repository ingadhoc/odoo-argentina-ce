##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import json
import logging
from datetime import datetime
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools import float_repr
from odoo.addons.l10n_ar_afipws_fe.afip_utils import get_invoice_number_from_response
import base64

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
    afip_associated_period_from = fields.Date(
        'AFIP Period from'
    )
    afip_associated_period_to = fields.Date(
        'AFIP Period to'
    )
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
        "Validation Type",
        compute="_compute_validation_type",
    )
    afip_fce_es_anulacion = fields.Boolean(
        string="FCE: Es anulacion?",
        help="Solo utilizado en comprobantes MiPyMEs (FCE) del tipo débito o crédito. Debe informar:\n"
        "- SI: sí el comprobante asociado (original) se encuentra rechazado por el comprador\n"
        "- NO: sí el comprobante asociado (original) NO se encuentra rechazado por el comprador",
    )
    asynchronous_post = fields.Boolean()

    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No")],
        compute="compute_l10n_ar_payment_foreign_currency",
        store=True,
        readonly=False
    )
    l10n_ar_currency_code = fields.Char("Currency Code", related="currency_id.name")

    @api.onchange("currency_id", "line_ids")
    @api.depends("currency_id")
    def compute_l10n_ar_payment_foreign_currency(self):
        self.l10n_ar_payment_foreign_currency = False
        for move in self:
            default_value = move.company_id.l10n_ar_payment_foreign_currency
            if default_value == "account":
                account = move.line_ids.account_id.filtered(lambda x: x.account_type == "asset_receivable")
                default_value = "S" if account.currency_id and account.currency_id != move.company_currency_id else "N"
            move.l10n_ar_payment_foreign_currency = default_value

    # @api.depends('journal_id', 'l10n_latam_document_type_id')
    # def _compute_highest_name(self):
    #     manual_records = self.filtered(lambda move: move.journal_id.afip_ws in ['wsfe', 'wsfex', 'wsbfe'])
    #     manual_records.highest_name = ''
    #     super(AccountMove, self - manual_records)._compute_highest_name()

    def cron_asynchronous_post(self):
        queue_limit = self.env['ir.config_parameter'].sudo().get_param('l10n_ar_afipws_fe.queue_limit', 20)
        queue = self.search([
            ('asynchronous_post', '=', True), '|',
            ('afip_result', '=', False),
            ('afip_result', '=', ''),
        ], limit=queue_limit)
        if queue:
            queue._post()

    def _get_starting_sequence(self):
        """ If use documents then will create a new starting sequence using the document type code prefix and the
        journal document number with a 8 padding number """
        if self.journal_id.l10n_latam_use_documents and self.company_id.account_fiscal_country_id.code == "AR" and self.journal_id.afip_ws:
            if self.l10n_latam_document_type_id:
                number = int(
                    self.journal_id.get_pyafipws_last_invoice(
                        self.l10n_latam_document_type_id
                    )
                )
                return self._get_formatted_sequence(number)
        return super()._get_starting_sequence()

    def _set_next_sequence(self):
        self.ensure_one()
        if self.afip_auth_code and self.journal_id.afip_ws and self.afip_xml_response:
            invoice_number = get_invoice_number_from_response(self.afip_xml_response, self.journal_id.afip_ws)
            if invoice_number:
                last_sequence = self._get_formatted_sequence(invoice_number)
                format, format_values = self._get_sequence_format_param(last_sequence)
                format_values['year'] = self[self._sequence_date_field].year % (10 ** format_values['year_length'])
                format_values['month'] = self[self._sequence_date_field].month
                format_values['seq'] = invoice_number

                self[self._sequence_field] = format.format(**format_values)
                return
        super()._set_next_sequence()

    # TODO Esto se deprecaria si la secuencia solo viene de  result de afip
    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        if self._name == 'account.move' and \
            self.journal_id.l10n_latam_use_documents and \
            self.company_id.account_fiscal_country_id.code == "AR" and \
            not self.afip_auth_code and \
            self.journal_id.afip_ws and  self.l10n_latam_document_type_id:
            number = int(
                self.journal_id.get_pyafipws_last_invoice(
                    self.l10n_latam_document_type_id
                )
            )
            res = self._get_formatted_sequence(number)
        else:
            res = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)
        return res

    @api.depends("journal_id", "afip_auth_code")
    def _compute_validation_type(self):
        for rec in self:
            if rec.journal_id.afip_ws and not rec.afip_auth_code:
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
                    "ctz": float(float_repr(rec.l10n_ar_currency_rate, 2)),
                    "tipoCodAut": "E" if rec.afip_auth_mode == "CAE" else "A",
                    "codAut": int(rec.afip_auth_code),
                }
                if (
                    len(rec.commercial_partner_id.l10n_latam_identification_type_id)
                    and rec.commercial_partner_id.vat
                ):
                    qr_dict["tipoDocRec"] = int(
                        rec.commercial_partner_id.l10n_latam_identification_type_id.l10n_ar_afip_code
                    )
                    qr_dict["nroDocRec"] = int(
                        rec.commercial_partner_id.vat.replace("-", "").replace(".", "")
                    )
                qr_data = base64.encodestring(
                    json.dumps(qr_dict, indent=None).encode("ascii")
                ).decode("ascii")
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
            and x.journal_id.afip_ws
            and not x.afip_auth_code
        )
        a_invoices, r_invoices = request_cae_invoices.do_pyafipws_request_cae()
        if len(self) == 1 and r_invoices:
            raise (UserError(r_invoices.afip_message))
        return super(AccountMove, self - r_invoices)._post(soft=soft)

    def do_pyafipws_request_cae(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE) via zeep"
        a_invoices = r_invoices = self.env['account.move']

        for inv in self:

            afip_ws = inv.journal_id.afip_ws
            if not afip_ws:
                continue

            # if no validation type and we are on electronic invoice, it means
            # that we are on a testing database without homologation
            # certificates
            if not inv.validation_type:
                msg = (
                    "Factura validada solo localmente por estar en ambiente "
                    "de homologación sin claves de homologación"
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

            # Inicio conexion zeep
            connection = inv.company_id.get_connection(afip_ws)
            try:
                client, auth, transport = connection.connect()
            except Exception as e:
                msg = _("AFIP connection error: %s") % (e,)
                inv.sudo().write({
                    "name": "/",
                    "afip_result": "R",
                    "afip_message": msg,
                    "afip_xml_request": "",
                    "afip_xml_response": "",
                })
                inv._cr.commit()
                r_invoices += inv
                continue

            # Preparo los datos (mismo mapeo, sin pyafipws)
            invoice_info = inv.map_invoice_info(afip_ws)
            if isinstance(invoice_info, str):
                # map devolvió mensaje "not implemented"
                inv.sudo().write({
                    "name": "/",
                    "afip_result": "R",
                    "afip_message": invoice_info,
                    "afip_xml_request": "",
                    "afip_xml_response": "",
                })
                inv._cr.commit()
                r_invoices += inv
                continue

            cae, vto, resultado, msg = inv._zeep_request_cae(client, auth, transport, afip_ws, invoice_info)
            xml_request = getattr(transport, "xml_request", "") or ""
            xml_response = getattr(transport, "xml_response", "") or ""
            if not cae or resultado != "A":
                r_invoices += inv
                vals = {
                        "name": '/',
                        "afip_result": 'R' if resultado != "O" else "O",
                        "afip_message": msg,
                        "afip_xml_request": xml_request,
                        "afip_xml_response": xml_response,
                }
                inv.sudo().write(vals)
                inv._cr.commit()
                continue

            _logger.info("CAE solicitado con exito. CAE: %s. Resultado %s" % (cae, resultado))
            vals = {
                    "afip_auth_mode": "CAE",
                    "afip_auth_code": cae,
                    "afip_auth_code_due": vto,
                    "afip_result": resultado,
                    "afip_message": msg,
                    "afip_xml_request": xml_request,
                    "afip_xml_response": xml_response,
            }
            inv.sudo().write(vals)
            inv._cr.commit()
            a_invoices += inv
        return (a_invoices, r_invoices)

    def _zeep_request_cae(self, client, auth, transport, afip_ws, invoice_info):
        """Llama al WS correspondiente vía zeep. Devuelve (cae, vto, resultado, msg)."""
        self.ensure_one()
        # Preflight obligatorio trasladado de pyafipws a zeep
        self._zeep_preflight(invoice_info, afip_ws)
        if afip_ws == "wsfe":
            return self._zeep_wsfe_authorize(client, auth, invoice_info)
        elif afip_ws == "wsfex":
            return self._zeep_wsfex_authorize(client, auth, invoice_info)
        elif afip_ws == "wsbfe":
            return self._zeep_wsbfe_authorize(client, auth, invoice_info)
        elif afip_ws == "wsmtxca":
            raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))
        else:
            raise UserError(_("AFIP WS %s not implemented") % afip_ws)

    def _zeep_wsfe_authorize(self, client, auth, invoice_info):
        request_data = self.zeep_wsfe_request(client, invoice_info)
        try:
            client.create_message(client.service, "FECAESolicitar", auth, request_data)
        except Exception as error:
            raise UserError(repr(error))
        response = client.service.FECAESolicitar(auth, request_data)
        errors = obs = events = ""
        return_codes = []
        cae = vto = resultado = False
        if getattr(response, "FeDetResp", None):
            result = response.FeDetResp.FECAEDetResponse[0]
            if getattr(result, "Observaciones", None):
                obs = "".join(["\n* Code %s: %s" % (ob.Code, ob.Msg) for ob in result.Observaciones.Obs])
                return_codes += [str(ob.Code) for ob in result.Observaciones.Obs]
            if result.Resultado == "A":
                cae = result.CAE and str(result.CAE) or ""
                vto = datetime.strptime(result.CAEFchVto, "%Y%m%d").date()
                resultado = result.Resultado
        if getattr(response, "Errors", None):
            errors = "".join(["\n* Code %s: %s" % (e.Code, e.Msg) for e in response.Errors.Err])
            return_codes += [str(e.Code) for e in response.Errors.Err]
        if getattr(response, "Events", None):
            events = "".join(["\n* Code %s: %s" % (e.Code, e.Msg) for e in response.Events.Evt])
        msg = "\n".join([x for x in [obs, errors, events] if x])
        if not cae:
            return False, False, (resultado or "R"), msg or _("Rejected without CAE")
        if obs and resultado == "A":
            resultado = "O"
        return cae, vto, resultado, msg

    def _zeep_wsfex_authorize(self, client, auth, invoice_info):
        last_id = client.service.FEXGetLast_ID(auth).FEXResultGet.Id
        request_data = self.zeep_wsfex_request(client, last_id + 1, invoice_info)
        try:
            client.create_message(client.service, "FEXAuthorize", auth, request_data)
        except Exception as error:
            raise UserError(repr(error))
        response = client.service.FEXAuthorize(auth, request_data)
        errors = ""
        if response.FEXErr.ErrCode != 0 or response.FEXErr.ErrMsg != "OK":
            errors = "\n* Code %s: %s" % (response.FEXErr.ErrCode, response.FEXErr.ErrMsg)
        result = response.FEXResultAuth
        if not result or result.Resultado != "A":
            msg = errors or (result.Motivos_Obs if result else "") or _("Rejected")
            return False, False, "R", msg
        vto = datetime.strptime(result.Fch_venc_Cae, "%Y%m%d").date()
        obs = ("\n* %s" % result.Motivos_Obs) if getattr(result, "Motivos_Obs", None) else ""
        return result.Cae, vto, ("O" if obs else result.Resultado), (errors + obs).strip()

    def _zeep_wsbfe_authorize(self, client, auth, invoice_info):
        last_id = client.service.BFEGetLast_ID(auth).BFEResultGet.Id
        request_data = self.zeep_wsbfe_request(client, last_id + 1, invoice_info)
        try:
            client.create_message(client.service, "BFEAuthorize", auth, request_data)
        except Exception as error:
            raise UserError(repr(error))
        response = client.service.BFEAuthorize(auth, request_data)
        errors = ""
        if response.BFEErr.ErrCode != 0 or response.BFEErr.ErrMsg != "OK":
            errors = "\n* Code %s: %s" % (response.BFEErr.ErrCode, response.BFEErr.ErrMsg)
        result = response.BFEResultAuth
        if not result or result.Resultado != "A":
            msg = errors or getattr(result, "Obs", "") or _("Rejected")
            return False, False, "R", msg
        vto = datetime.strptime(result.Fch_venc_Cae, "%Y%m%d").date()
        obs = getattr(result, "Obs", "") or ""
        return result.Cae, vto, ("O" if obs else result.Resultado), (errors + ("\n* %s" % obs if obs else "")).strip()

    def get_pyafipws_currency_rate(self):
        self.ensure_one()
        afipws_get_currency_rate = self.pyafipws_get_currency_rate()
        # TODO: crear cotizacion?
        self._set_afip_rate()
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _(
                    "Actual afip rate is %s" % afipws_get_currency_rate
                ),
                "type": "success",
                "sticky": True,  # True/False will display for few seconds if false
            },
        }
        return notification
