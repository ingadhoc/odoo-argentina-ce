##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import json
import logging
import re
import traceback
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_repr

from ..afip_utils import get_invoice_number_from_response

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
    asynchronous_post = fields.Boolean()

    l10n_ar_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No")], compute="_compute_l10n_ar_payment_foreign_currency", store=True, readonly=False
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
    #     manual_records = self.filtered(lambda move: move.journal_id.afip_ws in ['wsfe', 'wsfex', 'wsbfe'])
    #     manual_records.highest_name = ''
    #     super(AccountMove, self - manual_records)._compute_highest_name()

    def cron_asynchronous_post(self):
        queue_limit = self.env["ir.config_parameter"].sudo().get_param("l10n_ar_afipws_fe.queue_limit", 20)
        queue = self.search(
            [
                ("asynchronous_post", "=", True),
                "|",
                ("afip_result", "=", False),
                ("afip_result", "=", ""),
            ],
            limit=queue_limit,
        )
        if queue:
            queue._post()

    def _get_starting_sequence(self):
        """If use documents then will create a new starting sequence using the document type code prefix and the
        journal document number with a 8 padding number"""
        if (
            self.journal_id.l10n_latam_use_documents
            and self.company_id.account_fiscal_country_id.code == "AR"
            and self.journal_id.afip_ws
        ):
            if self.l10n_latam_document_type_id:
                number = int(self.journal_id.get_pyafipws_last_invoice(self.l10n_latam_document_type_id))
                return self._get_formatted_sequence(number)
        return super()._get_starting_sequence()

    def _set_next_sequence(self):
        self.ensure_one()
        if self.afip_auth_code and self.journal_id.afip_ws and self.afip_xml_response:
            invoice_number = get_invoice_number_from_response(self.afip_xml_response, self.journal_id.afip_ws)
            if invoice_number:
                last_sequence = self._get_formatted_sequence(invoice_number)
                format, format_values = self._get_sequence_format_param(last_sequence)
                format_values["year"] = self[self._sequence_date_field].year % (10 ** format_values["year_length"])
                format_values["month"] = self[self._sequence_date_field].month
                format_values["seq"] = invoice_number

                self[self._sequence_field] = format.format(**format_values)
                return
        super()._set_next_sequence()

    # TODO Esto se deprecaria si la secuencia solo viene de  result de afip
    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        if (
            self._name == "account.move"
            and self.journal_id.l10n_latam_use_documents
            and self.company_id.account_fiscal_country_id.code == "AR"
            and not self.afip_auth_code
            and self.journal_id.afip_ws
            and self.l10n_latam_document_type_id
        ):
            number = int(self.journal_id.get_pyafipws_last_invoice(self.l10n_latam_document_type_id))
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

    @api.depends(
        "afip_auth_code",
        "afip_auth_mode",
        "l10n_latam_document_number",
        "l10n_latam_document_type_id",
    )
    def _compute_qr_code(self):
        for rec in self:
            rec.afip_qr_code = False
            if rec.afip_auth_mode not in ("CAE", "CAEA") or not rec.afip_auth_code:
                continue
            doc_number = rec.l10n_latam_document_number
            doc_type_code = rec.l10n_latam_document_type_id.code
            if not doc_number or not doc_type_code or "-" not in str(doc_number):
                continue
            number_parts = rec._l10n_ar_get_document_number_parts(doc_number, doc_type_code)
            rate = rec.invoice_currency_rate or 1.0
            qr_dict = {
                "ver": 1,
                "fecha": str(rec.invoice_date),
                "cuit": int(rec.company_id.partner_id.l10n_ar_vat or 0),
                "ptoVta": number_parts["point_of_sale"],
                "tipoCmp": int(doc_type_code),
                "nroCmp": number_parts["invoice_number"],
                "importe": float(float_repr(rec.amount_total, 2)),
                "moneda": rec.currency_id.l10n_ar_afip_code,
                "ctz": float(float_repr(1 / rate if rate else 1.0, 2)),
                "tipoCodAut": "E" if rec.afip_auth_mode == "CAE" else "A",
                "codAut": int(rec.afip_auth_code),
            }
            tipo_doc, nro_doc = rec._pyafipws_get_receptor_doc()
            qr_dict["tipoDocRec"] = int(tipo_doc)
            qr_dict["nroDocRec"] = int(nro_doc or 0)
            qr_data = base64.encodebytes(json.dumps(qr_dict, indent=None).encode("ascii")).decode("ascii")
            qr_data = str(qr_data).replace("\n", "")
            rec.afip_qr_code = "https://www.afip.gob.ar/fe/qr/?p=%s" % qr_data

    def _pyafipws_get_receptor_doc(self):
        """Return AFIP DocTipo / DocNro for the commercial partner.

        Anonymous final consumer (SIGD, AFIP 99, no VAT) must be reported as
        DocTipo 99 and DocNro 0. That is the usual POS case.
        """
        self.ensure_one()
        partner = self.commercial_partner_id
        ident_code = partner.l10n_latam_identification_type_id.l10n_ar_afip_code or ""
        vat_digits = "".join(ch for ch in (partner.vat or "") if ch.isdigit())
        final_consumer = self.env.ref("l10n_ar.res_CF", raise_if_not_found=False)
        is_final_consumer = bool(final_consumer) and partner.l10n_ar_afip_responsibility_type_id == final_consumer
        if ident_code == "99" or (is_final_consumer and not vat_digits):
            return "99", "0"
        if ident_code:
            return ident_code, vat_digits or "0"
        return "99", "0"

    def _pyafipws_parse_document_number(self):
        """Return point of sale / invoice number, or False if not available.

        ``l10n_latam_document_number`` is False while the move name is still
        ``/``. Core ``_l10n_ar_get_document_number_parts()`` then crashes with
        ``'bool' object has no attribute 'split'``. POS credit notes hit this
        on the original invoice (CbteAsoc).
        """
        self.ensure_one()
        doc_code = self.l10n_latam_document_type_id.code
        prefix = self.l10n_latam_document_type_id.doc_code_prefix or ""
        candidates = [self.l10n_latam_document_number]
        if self.name and self.name != "/":
            candidates.append(self.name)
        for raw in candidates:
            if not raw:
                continue
            text = str(raw).strip()
            if prefix and text.startswith(prefix):
                text = text[len(prefix) :].strip()
            elif " " in text:
                text = text.split(" ", 1)[-1]
            if doc_code and "-" in text:
                try:
                    return self._l10n_ar_get_document_number_parts(text, doc_code)
                except (AttributeError, TypeError, ValueError):
                    pass
            match = re.search(r"(\d{1,5})-(\d{1,8})", str(raw))
            if match:
                return {
                    "point_of_sale": int(match.group(1)),
                    "invoice_number": int(match.group(2)),
                }
        return False

    def _pyafipws_related_invoice_from_pos(self):
        """Find the original electronic invoice of a POS refund order."""
        self.ensure_one()
        if "pos_order_ids" not in self._fields:
            return self.browse()
        refund_orders = self.pos_order_ids
        origin_orders = self.env["pos.order"]
        if "refunded_order_id" in refund_orders._fields:
            origin_orders |= refund_orders.refunded_order_id
        if "refunded_order_ids" in refund_orders._fields:
            origin_orders |= refund_orders.refunded_order_ids
        if not origin_orders:
            origin_orders = refund_orders.lines.refunded_orderline_id.order_id
        invoices = origin_orders.mapped("account_move")
        if not invoices and origin_orders:
            invoices = self.env["account.move"].search(
                [
                    ("pos_order_ids", "in", origin_orders.ids),
                    ("move_type", "=", "out_invoice"),
                    ("afip_auth_code", "!=", False),
                ],
                limit=1,
            )
        return invoices.filtered(
            lambda move: move.is_invoice()
            and move.move_type == "out_invoice"
            and move.afip_auth_code
            and move.company_id.country_id.code == "AR"
        )[:1]

    def _pyafipws_add_cmp_asoc(self, ws, related, date_format=None):
        """Attach CbteAsoc without calling split() on a missing document number."""
        self.ensure_one()
        if not related:
            return
        related = related[:1]
        parts = related._pyafipws_parse_document_number()
        if not parts:
            raise UserError(
                _(
                    "The credit note must reference the original electronic "
                    "invoice (point of sale and number). Related invoice %s "
                    "has no AFIP document number."
                )
                % related.display_name
            )
        cuit = related.company_id.partner_id.l10n_ar_vat or related.company_id.vat or ""
        cuit = "".join(ch for ch in str(cuit) if ch.isdigit())
        fecha = related.invoice_date.strftime(date_format) if date_format and related.invoice_date else None
        ws.AgregarCmpAsoc(
            related.l10n_latam_document_type_id.code,
            parts["point_of_sale"],
            parts["invoice_number"],
            cuit or None,
            fecha,
        )

    def get_related_invoices_data(self):
        """
        List related invoice information to fill CbtesAsoc.

        POS refunds should already set ``reversed_entry_id`` from the original
        order invoice. If that link is missing, recover it from the POS order.
        """
        self.ensure_one()
        internal_type = self.l10n_latam_document_type_id.internal_type
        if internal_type == "debit_note":
            return self.debit_origin_id
        if internal_type != "credit_note":
            return self.browse()

        candidates = self.reversed_entry_id
        if "pos_refunded_invoice_ids" in self._fields:
            candidates |= self.pos_refunded_invoice_ids
        candidates |= self._pyafipws_related_invoice_from_pos()
        candidates = candidates.filtered(
            lambda move: move.is_invoice()
            and move.move_type == "out_invoice"
            and move.company_id.country_id.code == "AR"
        )
        with_cae = candidates.filtered(lambda move: move.afip_auth_code)
        pool = with_cae or candidates
        with_number = pool.filtered(lambda move: move._pyafipws_parse_document_number())
        return (with_number or pool)[:1]

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
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        a_invoices = r_invoices = self.env["account.move"]

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
                # sudo: local dummy CAE when homologation certs are missing.
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
                if getattr(ws, "Excepcion", None):
                    msg = ws.Excepcion
                else:
                    msg = traceback.format_exception_only(type(e), e)[0]
            if msg:
                _logger.error(
                    _("AFIP Validation Error. %s") % msg
                    + " XML Request: %s XML Response: %s" % (ws.XmlRequest, ws.XmlResponse)
                )

            msg = "\n".join([ws.Obs or "", ws.ErrMsg or ""])
            if not ws.CAE or ws.Resultado != "A":
                r_invoices += inv

                vals = {
                    "name": "/",
                    "afip_result": "R",
                    "afip_message": msg,
                    "afip_xml_request": ws.XmlRequest or "",
                    "afip_xml_response": ws.XmlResponse or "",
                }
                # sudo: persist AFIP rejection XML even if the user cannot write
                # technical fields; the invoice stays draft.
                inv.sudo().write(vals)
                # Commit so a later rollback cannot drop the AFIP response.
                inv._cr.commit()
                continue

            if hasattr(ws, "Vencimiento"):
                vto = datetime.strptime(ws.Vencimiento, "%Y%m%d").date()
            if hasattr(ws, "FchVencCAE"):
                vto = datetime.strptime(ws.FchVencCAE, "%Y%m%d").date()

            _logger.info("CAE solicitado con exito. CAE: %s. Resultado %s" % (ws.CAE, ws.Resultado))
            vals = {
                "afip_auth_mode": "CAE",
                "afip_auth_code": ws.CAE,
                "afip_auth_code_due": vto,
                "afip_result": ws.Resultado,
                "afip_message": msg,
                "afip_xml_request": ws.XmlRequest,
                "afip_xml_response": ws.XmlResponse,
            }

            # sudo: store CAE returned by AFIP; this cannot be rolled back.
            inv.sudo().write(vals)
            inv._cr.commit()
            a_invoices += inv
        return (a_invoices, r_invoices)

    def _l10n_ar_is_transparency_document(self):
        """Return True for Factura/ND/NC B (AFIP codes 6/7/8), RG 5614/2024.

        Some Odoo 19 ``l10n_ar`` builds omit this helper while the invoice
        report and POS tickets already call it (typically on Factura B from
        POS to Consumidor Final).
        """
        self.ensure_one()
        parent_fn = getattr(super(), "_l10n_ar_is_transparency_document", None)
        if parent_fn:
            return parent_fn()
        return self.l10n_latam_document_type_id.code in ("6", "7", "8")

    @api.model
    def _l10n_ar_is_tax_group_other_national_ind_tax(self, tax_group):
        parent_fn = getattr(super(), "_l10n_ar_is_tax_group_other_national_ind_tax", None)
        if parent_fn:
            return parent_fn(tax_group)
        return tax_group.l10n_ar_tribute_afip_code in ("01", "04")

    @api.model
    def _l10n_ar_is_tax_group_vat(self, tax_group):
        parent_fn = getattr(super(), "_l10n_ar_is_tax_group_vat", None)
        if parent_fn:
            return parent_fn(tax_group)
        return bool(tax_group.l10n_ar_vat_afip_code)

    @api.model
    def _l10n_ar_is_tax_group_iibb_perception(self, tax_group):
        parent_fn = getattr(super(), "_l10n_ar_is_tax_group_iibb_perception", None)
        if parent_fn:
            return parent_fn(tax_group)
        return tax_group.l10n_ar_tribute_afip_code == "07"

    def get_pyafipws_currency_rate(self):
        self.ensure_one()
        afip_ws = self.journal_id.afip_ws
        ws = self.company_id.get_connection(afip_ws).connect()
        afipws_get_currency_rate = self.pyafipws_get_currency_rate(ws)
        # TODO: crear cotizacion?
        self.invoice_currency_rate = 1 / float(afipws_get_currency_rate)
        self.message_post(body=_("AFIP currency rate: %s") % afipws_get_currency_rate)
