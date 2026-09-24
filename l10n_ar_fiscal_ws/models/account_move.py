##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_repr, float_round, html2plaintext

from .exceptions import FiscalWsError

_logger = logging.getLogger(__name__)

# Codes of the MiPyME documents, which carry extra optional data
FCE_INVOICE_CODES = [201, 206, 211]
FCE_CREDIT_DEBIT_CODES = [202, 203, 207, 208, 212, 213]
# Local authorization code used when invoicing without homologation certificates
LOCAL_AUTH_CODE = "68448767638166"


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ar_fiscal_auth_mode = fields.Selection(
        [("CAE", "CAE"), ("CAI", "CAI"), ("CAEA", "CAEA")],
        string="Authorization mode",
        copy=False,
    )
    l10n_ar_fiscal_auth_code = fields.Char("CAE/CAI/CAEA", copy=False, size=24)
    l10n_ar_fiscal_auth_code_due = fields.Date("CAE/CAI/CAEA due date", copy=False)
    l10n_ar_fiscal_result = fields.Selection(
        [("A", "Aceptado"), ("R", "Rechazado"), ("O", "Observado")],
        "Resultado",
        copy=False,
    )
    l10n_ar_fiscal_message = fields.Text("Mensaje de ARCA", copy=False)
    l10n_ar_fiscal_xml_request = fields.Text("XML enviado", copy=False, groups="base.group_system")
    l10n_ar_fiscal_xml_response = fields.Text("XML recibido", copy=False, groups="base.group_system")
    l10n_ar_fiscal_qr_code = fields.Char(compute="_compute_l10n_ar_fiscal_qr_code")
    l10n_ar_fiscal_period_from = fields.Date("Período asociado desde")
    l10n_ar_fiscal_period_to = fields.Date("Período asociado hasta")
    l10n_ar_fiscal_fce_is_cancellation = fields.Boolean(
        "FCE: ¿es anulación?",
        help="Solo en comprobantes MiPyME (FCE) de débito o crédito. Informá sí cuando el "
        "comprobante original está rechazado por el comprador.",
    )
    l10n_ar_fiscal_validation_type = fields.Char(compute="_compute_l10n_ar_fiscal_validation_type")
    l10n_ar_fiscal_document_internal_type = fields.Selection(
        related="l10n_latam_document_type_id.internal_type",
    )
    l10n_ar_fiscal_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No")],
        compute="_compute_l10n_ar_fiscal_payment_foreign_currency",
        store=True,
        readonly=False,
    )

    @api.model
    def default_get(self, fields_list):
        """OBA compatibility: modules of the ecosystem still pass the associated period
        through the context with the names of the enterprise localization
        (``default_l10n_ar_afip_asoc_period_start`` / ``_end``, from ``l10n_ar_edi_ux``).
        Those defaults would land on fields that do not exist here, so they are read
        into ours. Remove it when no module passes them any more.
        """
        res = super().default_get(fields_list)
        legacy_defaults = {
            "l10n_ar_fiscal_period_from": "default_l10n_ar_afip_asoc_period_start",
            "l10n_ar_fiscal_period_to": "default_l10n_ar_afip_asoc_period_end",
        }
        for field, legacy in legacy_defaults.items():
            if field in fields_list and not res.get(field) and self.env.context.get(legacy):
                res[field] = self.env.context[legacy]
        return res

    @api.depends("currency_id", "company_id")
    def _compute_l10n_ar_fiscal_payment_foreign_currency(self):
        for move in self:
            policy = move.company_id.l10n_ar_fiscal_payment_foreign_currency
            if policy == "account":
                account = move.line_ids.account_id.filtered(lambda x: x.account_type == "asset_receivable")
                policy = "S" if account.currency_id and account.currency_id != move.company_currency_id else "N"
            move.l10n_ar_fiscal_payment_foreign_currency = policy

    @api.depends("journal_id", "l10n_ar_fiscal_auth_code")
    def _compute_l10n_ar_fiscal_validation_type(self):
        """Empty when invoicing locally: homologation without certificates."""
        for rec in self:
            if not rec.journal_id.l10n_ar_fiscal_ws_id or rec.l10n_ar_fiscal_auth_code:
                rec.l10n_ar_fiscal_validation_type = False
                continue
            validation_type = self.env["res.company"]._get_environment_type()
            if validation_type == "homologation":
                try:
                    rec.company_id._get_key_and_certificate(validation_type)
                except UserError:
                    validation_type = False
            rec.l10n_ar_fiscal_validation_type = validation_type

    @api.depends("l10n_ar_fiscal_auth_code")
    def _compute_l10n_ar_fiscal_qr_code(self):
        for rec in self:
            if rec.l10n_ar_fiscal_auth_mode not in ("CAE", "CAEA") or not rec.l10n_ar_fiscal_auth_code:
                rec.l10n_ar_fiscal_qr_code = False
                continue
            number_parts = self._l10n_ar_get_document_number_parts(
                rec.l10n_latam_document_number, rec.l10n_latam_document_type_id.code
            )
            values = {
                "ver": 1,
                "fecha": str(rec.invoice_date),
                "cuit": int(rec.company_id.partner_id.l10n_ar_vat),
                "ptoVta": number_parts["point_of_sale"],
                "tipoCmp": int(rec.l10n_latam_document_type_id.code),
                "nroCmp": number_parts["invoice_number"],
                "importe": float(float_repr(rec.amount_total, 2)),
                "moneda": rec.currency_id.l10n_ar_afip_code,
                "ctz": float(float_repr(rec.invoice_currency_rate, 2)),
                "tipoCodAut": "E" if rec.l10n_ar_fiscal_auth_mode == "CAE" else "A",
                "codAut": int(rec.l10n_ar_fiscal_auth_code),
            }
            partner = rec.commercial_partner_id
            if partner.l10n_latam_identification_type_id and partner.vat:
                values["tipoDocRec"] = int(partner.l10n_latam_identification_type_id.l10n_ar_afip_code)
                values["nroDocRec"] = int(partner.vat.replace("-", "").replace(".", ""))
            data = base64.b64encode(json.dumps(values, indent=None).encode("ascii")).decode("ascii")
            rec.l10n_ar_fiscal_qr_code = "https://www.afip.gob.ar/fe/qr/?p=%s" % data

    # ---------------------------------------------------------------- numbering

    def _get_starting_sequence(self):
        """The number comes from the service, not from the Odoo sequence."""
        if self._l10n_ar_uses_fiscal_ws():
            return self._get_formatted_sequence(self._l10n_ar_get_next_number())
        return super()._get_starting_sequence()

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        if self._l10n_ar_uses_fiscal_ws() and not self.l10n_ar_fiscal_auth_code:
            return self._get_formatted_sequence(self._l10n_ar_get_next_number() - 1)
        return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)

    def _l10n_ar_uses_fiscal_ws(self):
        self.ensure_one()
        return bool(
            self._name == "account.move"
            and self.journal_id.l10n_latam_use_documents
            and self.journal_id.l10n_ar_fiscal_ws_id
            and self.l10n_latam_document_type_id
            and self.company_id.account_fiscal_country_id.code == "AR"
        )

    def _l10n_ar_get_next_number(self):
        """Next number for this document type, asked once per invoice."""
        self.ensure_one()
        if "l10n_ar_next_number" not in self.env.cr.precommit.data:
            self.env.cr.precommit.data["l10n_ar_next_number"] = {}
        cache = self.env.cr.precommit.data["l10n_ar_next_number"]
        key = (self.journal_id.id, self.l10n_latam_document_type_id.id)
        if key not in cache:
            cache[key] = self.journal_id._l10n_ar_get_last_invoice_number(self.l10n_latam_document_type_id) + 1
        return cache[key]

    # ------------------------------------------------------------- CAE request

    def _post(self, soft=True):
        """Post and then ask for the CAE, one invoice at a time.

        The order matters: posting first lets Odoo number the document and run
        everything it prepares on posting, and the authority is asked with that
        number. A refusal raises, and the rollback undoes the posting of that
        invoice —the number goes back— while the ones already authorized stay,
        because their CAE was committed.
        """
        to_authorize = self.filtered(
            lambda x: x.is_invoice()
            and x.move_type in ("out_invoice", "out_refund")
            and x.journal_id.l10n_ar_fiscal_ws_id
            and not x.l10n_ar_fiscal_auth_code
            and x.company_id.account_fiscal_country_id.code == "AR"
        )
        if not to_authorize:
            return super()._post(soft=soft)

        posted = super(AccountMove, self - to_authorize)._post(soft=soft)
        rejection = False
        for invoice in to_authorize:
            posted |= super(AccountMove, invoice)._post(soft=soft)
            message, values = invoice._l10n_ar_request_cae()
            if message:
                posted -= invoice
                rejection = (invoice, message, values)
                break
            # once authorized there is no way back, so it is kept even if a later one fails
            invoice.env.cr.commit()  # pylint: disable=invalid-commit

        if rejection:
            invoice, message, values = rejection
            text = self._l10n_ar_rejection_message(message, posted)
            invoice._l10n_ar_keep_rejection(values)
            raise FiscalWsError(text)
        return posted

    def _l10n_ar_keep_rejection(self, values):
        """Keep what the authority answered on an invoice it refused.

        The refusal ends in a raise, and its rollback would undo the posting —which
        is what we want, the number goes back— together with the answer. So the
        posting is undone here, on purpose, and the answer is written and committed
        on the draft invoice, which is where it is useful.
        """
        self.ensure_one()
        self.env.cr.rollback()
        self.env.invalidate_all()
        self.sudo().write(values)
        self.env.cr.commit()  # pylint: disable=invalid-commit

    def _l10n_ar_rejection_message(self, message, posted):
        """What the authority answered, saying which invoices did stay posted."""
        text = message
        authorized = posted.filtered("l10n_ar_fiscal_auth_code")
        if authorized:
            text += _(
                "\n\nEstos comprobantes ya quedaron autorizados y no se dan de baja: %s",
                ", ".join(authorized.mapped("name")),
            )
        return text

    def _l10n_ar_request_cae(self):
        """Ask the service to authorize this invoice.

        Returns the refusal and what to write about it; the refusal is not written
        here because the caller has to undo the posting first.
        """
        self.ensure_one()
        if not self.l10n_ar_fiscal_validation_type:
            self._l10n_ar_set_local_validation()
            return False, {}

        ws_code = self.journal_id.l10n_ar_fiscal_ws_id.code
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping(ws_code, "cae_request")
        try:
            response, xml = mapping.call(self)
        except FiscalWsError as error:
            return str(error), {"l10n_ar_fiscal_result": "R", "l10n_ar_fiscal_message": str(error)}

        values = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping(ws_code, "cae_response").build(response)
        values.update(
            {
                "l10n_ar_fiscal_xml_request": xml["xml_request"],
                "l10n_ar_fiscal_xml_response": xml["xml_response"],
                "l10n_ar_fiscal_message": self._l10n_ar_parse_observations(response),
            }
        )
        if values.get("l10n_ar_fiscal_result") != "A":
            # a refusal authorizes nothing: the mapping fills the authorization for every answer
            values.update(
                {
                    "l10n_ar_fiscal_result": "R",
                    "l10n_ar_fiscal_auth_mode": False,
                    "l10n_ar_fiscal_auth_code": False,
                    "l10n_ar_fiscal_auth_code_due": False,
                }
            )
            return values["l10n_ar_fiscal_message"], values
        self.sudo().write(values)
        return False, {}

    def _l10n_ar_set_local_validation(self):
        self.ensure_one()
        message = _("Factura validada solo localmente, por estar en homologación sin certificados.")
        self.sudo().write(
            {
                "l10n_ar_fiscal_auth_mode": "CAE",
                "l10n_ar_fiscal_auth_code": LOCAL_AUTH_CODE,
                "l10n_ar_fiscal_auth_code_due": self.invoice_date,
                "l10n_ar_fiscal_message": message,
            }
        )
        self.message_post(body=message)

    def _l10n_ar_parse_observations(self, response):
        """Observations of the service, as one readable text. Each service answers its own shape."""
        self.ensure_one()
        ws_code = self.journal_id.l10n_ar_fiscal_ws_id.code
        return getattr(self, "_l10n_ar_observations_" + ws_code)(response)

    def _l10n_ar_observations_wsfe(self, response):
        observations = []
        details = getattr(getattr(response, "FeDetResp", None), "FECAEDetResponse", None)
        for observation in getattr(getattr(details and details[0], "Observaciones", None), "Obs", []) or []:
            observations.append("(%s) %s" % (observation.Code, observation.Msg))
        for error in getattr(getattr(response, "Errors", None), "Err", []) or []:
            observations.append("(%s) %s" % (error.Code, error.Msg))
        return "\n".join(observations)

    def _l10n_ar_observations_wsfex(self, response):
        """The export service answers a single error, a single event and a free text of reasons."""
        return self._l10n_ar_join_observations(
            getattr(response, "FEXErr", None),
            getattr(response, "FEXEvents", None),
            getattr(getattr(response, "FEXResultAuth", None), "Motivos_Obs", None),
        )

    def _l10n_ar_observations_wsbfe(self, response):
        return self._l10n_ar_join_observations(
            getattr(response, "BFEErr", None),
            getattr(response, "BFEEvents", None),
            getattr(getattr(response, "BFEResultAuth", None), "Obs", None),
        )

    @staticmethod
    def _l10n_ar_join_observations(error, event, reasons):
        """Both detail services answer an ok as code zero, so only a non-zero code is worth reading."""
        observations = []
        if error and error.ErrCode:
            observations.append("(%s) %s" % (error.ErrCode, error.ErrMsg))
        if event and event.EventCode:
            observations.append("(%s) %s" % (event.EventCode, event.EventMsg))
        if reasons:
            observations.append(str(reasons))
        return "\n".join(observations)

    # ----------------------------------------------------------- currency rate

    def l10n_ar_action_get_currency_rate(self):
        """Ask the service for the rate of the invoice currency and apply it."""
        self.ensure_one()
        currency_code = self.currency_id.l10n_ar_afip_code
        if not currency_code:
            raise UserError(_("La moneda %s no tiene código de ARCA.", self.currency_id.name))
        response = self.journal_id._l10n_ar_call("currency_rate", {"currency_code": currency_code})
        errors = getattr(getattr(response, "Errors", None), "Err", []) or []
        if errors:
            raise FiscalWsError("\n".join("(%s) %s" % (error.Code, error.Msg) for error in errors))
        rate = float(response.ResultGet.MonCotiz)
        if not rate:
            raise UserError(_("ARCA informó una cotización en cero para %s.", self.currency_id.name))
        self.invoice_currency_rate = 1 / rate
        self.message_post(body=_("Cotización de ARCA: %s", rate))

    # --------------------------------------------------------------- providers

    def _l10n_ar_base_lines(self, extra):
        """Base lines of the invoice, computed once per call and shared by the providers."""
        if "base_lines" not in extra:
            extra["base_lines"] = self._get_rounded_base_and_tax_lines()[0]
        return extra["base_lines"]

    def _l10n_ar_fiscal_provider_invoice_number(self, extra):
        """Number Odoo already gave to the document when posting it."""
        parts = self._l10n_ar_get_document_number_parts(
            self.l10n_latam_document_number, self.l10n_latam_document_type_id.code
        )
        return parts["invoice_number"]

    def _l10n_ar_fiscal_provider_amounts(self, extra):
        """Amounts by kind of tax.

        The base lines are mandatory: without them l10n_ar returns every amount
        in zero and the authority rejects the invoice because the total does not
        match the sum.
        """
        if "amounts" not in extra:
            extra["amounts"] = self._l10n_ar_get_amounts(base_lines=self._l10n_ar_base_lines(extra))
        return extra["amounts"]

    def _l10n_ar_fiscal_provider_document_code(self, extra):
        return self.commercial_partner_id.l10n_latam_identification_type_id.l10n_ar_afip_code

    def _l10n_ar_fiscal_provider_document_number(self, extra):
        vat = self.commercial_partner_id.vat or ""
        return vat.replace("-", "").replace(".", "") or 0

    def _l10n_ar_fiscal_provider_currency_rate(self, extra):
        return 1 / self.invoice_currency_rate if self.invoice_currency_rate else 1

    def _l10n_ar_fiscal_provider_due_payment_date(self, extra):
        """Only asked for services and for MiPyME documents."""
        if self.l10n_ar_afip_concept == "1" and int(self.l10n_latam_document_type_id.code) not in FCE_INVOICE_CODES:
            return None
        return self.invoice_date_due or self.invoice_date

    def _l10n_ar_fiscal_provider_vat_items(self, extra):
        return self._get_vat(base_lines=self._l10n_ar_base_lines(extra))

    def _l10n_ar_fiscal_provider_tributes(self, extra):
        """Taxes that are not VAT, grouped by the code the tax authority uses."""

        def group_by_tribute_code(_base_line, tax_data):
            tax = (tax_data or {}).get("tax", self.env["account.tax"])
            return {"tribute_code": tax.tax_group_id.l10n_ar_tribute_afip_code}

        aggregated = self.env["account.tax"]._aggregate_base_lines_aggregated_values(
            self.env["account.tax"]._aggregate_base_lines_tax_details(
                self._l10n_ar_base_lines(extra), group_by_tribute_code
            )
        )
        tributes = []
        for grouping_key, values in aggregated.items():
            if not grouping_key["tribute_code"]:
                continue
            base = float_round(values["base_amount_currency"], precision_digits=2)
            amount = float_round(values["tax_amount_currency"], precision_digits=2)
            if not base and not amount:
                continue
            tributes.append(
                {
                    "Id": grouping_key["tribute_code"],
                    "BaseImp": base,
                    "Alic": float_round(amount / base * 100, precision_digits=2) if base else 0,
                    "Importe": amount,
                }
            )
        return tributes

    def _l10n_ar_fiscal_provider_related_invoices(self, extra):
        """Documents this one refers to, for credit and debit notes."""
        self.ensure_one()
        internal_type = self.l10n_latam_document_type_id.internal_type
        if internal_type == "credit_note":
            related = self.reversed_entry_id
        elif internal_type == "debit_note":
            related = self.debit_origin_id
        else:
            return []
        values = []
        for invoice in related:
            parts = self._l10n_ar_get_document_number_parts(
                invoice.l10n_latam_document_number, invoice.l10n_latam_document_type_id.code
            )
            values.append(
                {
                    "Tipo": invoice.l10n_latam_document_type_id.code,
                    "PtoVta": parts["point_of_sale"],
                    "Nro": parts["invoice_number"],
                    "Cuit": self.company_id.partner_id.l10n_ar_vat,
                    "CbteFch": invoice.invoice_date,
                }
            )
        return values

    def _l10n_ar_fiscal_provider_optionals(self, extra):
        """Optional data of the MiPyME documents."""
        self.ensure_one()
        code = int(self.l10n_latam_document_type_id.code)
        optionals = []
        if code in FCE_INVOICE_CODES:
            optionals.append({"Id": 27, "Valor": self.company_id.l10n_ar_fce_transmission_type})
            if self.partner_bank_id.acc_type == "cbu":
                optionals.append({"Id": 2101, "Valor": self.partner_bank_id.acc_number})
        if code in FCE_CREDIT_DEBIT_CODES:
            optionals.append({"Id": 22, "Valor": "S" if self.l10n_ar_fiscal_fce_is_cancellation else "N"})
        return optionals

    # ------------------------------------------------- providers of the detail services

    def _l10n_ar_fiscal_provider_request_id(self, extra):
        """Id of the request, which the detail services ask to be greater than the last one."""
        if "request_id" not in extra:
            response = self.journal_id._l10n_ar_call("last_id")
            values = self.journal_id._l10n_ar_build_response("last_id_response", response)
            extra["request_id"] = int(values.get("number") or 0) + 1
        return extra["request_id"]

    def _l10n_ar_fiscal_provider_line_items(self, extra):
        """One entry per invoice line: the detail services send the lines, unlike WSFE."""
        uom_digits = min(self.env["decimal.precision"].precision_get("Product Unit"), 6)
        price_digits = min(self.env["decimal.precision"].precision_get("Product Price"), 3)
        is_export = self.journal_id.l10n_ar_fiscal_ws_id.code == "wsfex"
        items = []
        for base_line in self._l10n_ar_base_lines(extra):
            line = base_line["record"]
            if not line.product_uom_id:
                # a line without a unit is reported as "units", which is what the authority expects
                uom_code = "7"
            elif not line.product_uom_id.l10n_ar_afip_code:
                raise UserError(_("La unidad de medida %s no tiene código de ARCA.", line.product_uom_id.display_name))
            else:
                uom_code = line.product_uom_id.l10n_ar_afip_code
            quantity = base_line["quantity"]
            unit_price = float_repr(line.price_unit, precision_digits=price_digits)
            taxes = base_line["tax_details"]
            if is_export and uom_code not in ("00", "97", "99"):
                # the export service asks for these codes on down payments and on negative lines
                if line._get_downpayment_lines():
                    uom_code = "97"
                elif line.price_unit < 0:
                    uom_code = "99"
            if is_export and uom_code in ("00", "97", "99"):
                quantity, unit_price = 0.0, "0.00"
            vat_tax = line.tax_ids.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code)
            items.append(
                {
                    "product_code": line.product_id.default_code or "",
                    "ncm_code": line.product_id.l10n_ar_ncm_code or "",
                    "description": line.name,
                    "quantity": float_repr(quantity, precision_digits=uom_digits),
                    "uom_code": uom_code,
                    "unit_price": unit_price,
                    "bonus": (float(unit_price) * quantity - taxes["raw_total_excluded_currency"])
                    if base_line["discount"]
                    else 0.0,
                    "vat_code": vat_tax.tax_group_id.l10n_ar_vat_afip_code,
                    "total_excluded": taxes["total_excluded_currency"] + taxes["delta_total_excluded_currency"],
                    "total_included": taxes["total_included_currency"],
                }
            )
        return items

    def _l10n_ar_fiscal_provider_customer_address(self, extra):
        partner = self.commercial_partner_id
        return " - ".join(
            part for part in (partner.name, partner.street, partner.street2, partner.zip, partner.city) if part
        )

    def _l10n_ar_fiscal_provider_vat_country(self, extra):
        """CUIT that the authority assigns to each country, for a customer abroad without its own."""
        partner = self.commercial_partner_id
        if partner.country_id.code in ("AR", False):
            return 0
        country = partner.country_id
        return (country.l10n_ar_legal_entity_vat if partner.is_company else country.l10n_ar_natural_vat) or 0

    def _l10n_ar_fiscal_provider_export_permit(self, extra):
        """Only an export invoice of goods declares it; we do not manage permit numbers yet."""
        concept = int(self.l10n_ar_afip_concept or 0)
        return "N" if int(self.l10n_latam_document_type_id.code) == 19 and concept == 1 else ""

    def _l10n_ar_fiscal_provider_incoterm_description(self, extra):
        """The service takes up to 20 characters."""
        name = self.invoice_incoterm_id.name
        return name[:20] if name else None

    def _l10n_ar_fiscal_provider_narration_text(self, extra):
        return html2plaintext(self.narration) if self.narration else None

    def _l10n_ar_fiscal_provider_export_payment_date(self, extra):
        """Asked only on an export invoice for services or for both goods and services."""
        concept = int(self.l10n_ar_afip_concept or 0)
        if int(self.l10n_latam_document_type_id.code) != 19 or concept not in (2, 4):
            return None
        return self.invoice_date_due

    def _l10n_ar_fiscal_provider_perceptions_amount(self, extra):
        """Perceptions, which the fiscal bond service asks for as a single amount."""
        amounts = self._l10n_ar_fiscal_provider_amounts(extra)
        return amounts["vat_perc_amount"] + amounts["profits_perc_amount"] + amounts["other_perc_amount"]

    def _l10n_ar_fiscal_provider_internal_taxes_amount(self, extra):
        amounts = self._l10n_ar_fiscal_provider_amounts(extra)
        return amounts["intern_tax_amount"] + amounts["other_taxes_amount"]
