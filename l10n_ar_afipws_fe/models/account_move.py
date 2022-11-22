##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools import float_repr
from odoo.addons.l10n_ar_afipws_fe.afip_utils import get_invoice_number_from_response
import base64

base64.encodestring = base64.encodebytes
import json
import logging
import sys
import traceback
from datetime import datetime

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    afip_auth_mode = fields.Selection(
        [("CAE", "CAE"), ("CAI", "CAI"), ("CAEA", "CAEA")],
        string="AFIP authorization mode",
        copy=False,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    afip_auth_code = fields.Char(
        copy=False,
        string="CAE/CAI/CAEA Code",
        readonly=True,
        size=24,
        states={"draft": [("readonly", False)]},
    )
    afip_auth_code_due = fields.Date(
        copy=False,
        readonly=True,
        string="CAE/CAI/CAEA due Date",
        states={"draft": [("readonly", False)]},
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
        readonly=True,
        states={"draft": [("readonly", False)]},
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


    @api.depends('journal_id', 'l10n_latam_document_type_id')
    def _compute_highest_name(self):
        manual_records = self.filtered(lambda move: move.journal_id.afip_ws in ['wsfe', 'wsfex', 'wsbfe'])
        manual_records.highest_name = ''
        super(AccountMove, self - manual_records)._compute_highest_name()


    def cron_asynchronous_post(self):
        queue_limit = self.env['ir.config_parameter'].sudo().get_param('l10n_ar_afipws_fe.queue_limit', 20)
        queue = self.search([
            ('asynchronous_post', '=', True),'|',
            ('afip_result', '=', False),
            ('afip_result', '=', ''),
        ], limit=queue_limit)
        if queue:
            queue._post()

    def _get_starting_sequence(self):
        """ If use documents then will create a new starting sequence using the document type code prefix and the
        journal document number with a 8 padding number """
        if self.journal_id.l10n_latam_use_documents and self.company_id.account_fiscal_country_id.code == "AR" and self.journal_id.afip_ws:
            if self.l10n_latam_document_type_id :
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
    # def _get_last_sequence(self, relaxed=False, with_prefix=None, lock=True):
    #     if self._name == 'account.move' and \
    #         self.journal_id.l10n_latam_use_documents and \
    #         self.company_id.account_fiscal_country_id.code == "AR" and \
    #         not self.afip_auth_code and \
    #         self.journal_id.afip_ws and  self.l10n_latam_document_type_id:
    #         number = int(
    #             self.journal_id.get_pyafipws_last_invoice(
    #                 self.l10n_latam_document_type_id
    #             )
    #         )
    #         res = self._get_formatted_sequence(number)
    #     else:
    #         res = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix, lock=lock)
    #     return res



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
        a_invoices , r_invoices = request_cae_invoices.do_pyafipws_request_cae()
        if len(self) == 1 and r_invoices:
            raise (UserError(r_invoices.afip_message))
        return super(AccountMove, self - r_invoices)._post(soft=soft)

    def do_pyafipws_request_cae(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
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

            # Inicio conexion
            ws = inv.company_id.get_connection(afip_ws).connect()

            # Preparo los datos
            invoice_info = inv.map_invoice_info(afip_ws)

            # Esto no es necesario ahora ya que el numero se obtiene desde el result
            # document_number = inv._get_formatted_sequence(int(invoice_info["ws_next_invoice_number"]))
            # doc_code_prefix = inv.l10n_latam_document_type_id.doc_code_prefix
            # if doc_code_prefix and document_number:
            #     document_number = document_number.split(" ", 1)[-1]
            # inv.l10n_latam_document_number = document_number

            # Creo la factura en el ambito de pyafipws
            inv.pyafipws_create_invoice(ws, invoice_info)

            # Agrego informacion a la factura dentro de pyafipws
            inv.pyafipws_add_info(ws, afip_ws, invoice_info)

            # Request the authorization! (call the AFIP webservice method)
            vto = None
            msg = False
            try:
                # Pido autorizacion
                inv.pyafipws_request_autorization(ws, afip_ws)
            except Exception as e:
                msg = e
            except Exception:
                if ws.Excepcion:
                    # get the exception already parsed by the helper
                    msg = ws.Excepcion
                else:
                    # avoid encoding problem when raising error
                    msg = traceback.format_exception_only(sys.exc_type, sys.exc_value)[
                        0
                    ]
            if msg:
                _logger.error(
                    _("AFIP Validation Error. %s" % msg)
                    + " XML Request: %s XML Response: %s"
                    % (ws.XmlRequest, ws.XmlResponse)
                )

            msg = "\n".join([ws.Obs or "", ws.ErrMsg or ""])
            if not ws.CAE or ws.Resultado != "A":
                    r_invoices += inv

                    vals = {
                            "name":'/',
                            "afip_result": 'R',
                            "afip_message": msg,
                            "afip_xml_request": ws.XmlRequest or '',
                            "afip_xml_response": ws.XmlResponse or '',
                    }
                    inv.sudo().write(vals)
                    inv._cr.commit()
                    continue

            if hasattr(ws, "Vencimiento"):
                vto = datetime.strptime(ws.Vencimiento, "%Y%m%d").date()
            if hasattr(ws, "FchVencCAE"):
                vto = datetime.strptime(ws.FchVencCAE, "%Y%m%d").date()

            _logger.info(
                "CAE solicitado con exito. CAE: %s. Resultado %s"
                % (ws.CAE, ws.Resultado)
            )
            vals = {
                    "afip_auth_mode": "CAE",
                    "afip_auth_code": ws.CAE,
                    "afip_auth_code_due": vto,
                    "afip_result": ws.Resultado,
                    "afip_message": msg,
                    "afip_xml_request": ws.XmlRequest,
                    "afip_xml_response": ws.XmlResponse,
            }

            inv.sudo().write(vals)
            inv._cr.commit()
            # si obtuvimos el cae hacemos el commit porque estoya no se puede
            # volver atras
            a_invoices += inv
        return (a_invoices, r_invoices)
