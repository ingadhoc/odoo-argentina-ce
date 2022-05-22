##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import re


class AccountVatLedger(models.Model):

    _name = "account.vat.ledger"
    _description = "Account VAT Ledger"
    _inherit = ["mail.thread"]
    _order = "date_from desc"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
        default=lambda self: self.env["res.company"]._company_default_get(
            "account.vat.ledger"
        ),
    )
    type = fields.Selection(
        [("sale", "Sale"), ("purchase", "Purchase")], "Type", required=True
    )
    date_from = fields.Date(
        string="Start Date",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    journal_ids = fields.Many2many(
        "account.journal",
        "account_vat_ledger_journal_rel",
        "vat_ledger_id",
        "journal_id",
        string="Journals",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    first_page = fields.Integer(
        "First Page",
        required=True,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    last_page = fields.Integer(
        "Last Page",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    presented_ledger = fields.Binary(
        "Presented Ledger",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    presented_ledger_name = fields.Char()
    state = fields.Selection(
        [("draft", "Draft"), ("presented", "Presented"), ("cancel", "Cancel")],
        "State",
        required=True,
        default="draft",
    )
    note = fields.Html("Notes")
    # Computed fields
    name = fields.Char("Titile", compute="_compute_name")
    reference = fields.Char(
        "Reference",
    )
    invoice_ids = fields.Many2many(
        "account.ar.vat.line", string="Invoices", compute="_compute_invoices"
    )
    # txt for citi / libro iva fields
    REGINFO_CV_ALICUOTAS = fields.Text(
        "REGINFO_CV_ALICUOTAS",
        readonly=True,
    )
    REGINFO_CV_COMPRAS_IMPORTACIONES = fields.Text(
        "REGINFO_CV_COMPRAS_IMPORTACIONES",
        readonly=True,
    )
    REGINFO_CV_CBTE = fields.Text(
        "REGINFO_CV_CBTE",
        readonly=True,
    )
    REGINFO_CV_CABECERA = fields.Text(
        "REGINFO_CV_CABECERA",
        readonly=True,
    )
    vouchers_file = fields.Binary(compute="_compute_files", readonly=True)
    vouchers_filename = fields.Char(
        compute="_compute_files",
    )
    aliquots_file = fields.Binary(
        compute="_compute_files",
    )
    aliquots_filename = fields.Char(
        compute="_compute_files",
    )
    import_aliquots_file = fields.Binary(
        compute="_compute_files",
    )
    import_aliquots_filename = fields.Char(
        compute="_compute_files",
    )
    prorate_tax_credit = fields.Boolean()
    prorate_type = fields.Selection(
        [("global", "Global"), ("by_voucher", "By Voucher")],
    )
    tax_credit_computable_amount = fields.Float(
        "Credit Computable Amount",
    )
    sequence = fields.Integer(
        default=0,
        required=True,
        help="Se deberá indicar si la presentación es Original (00) o "
        "Rectificativa y su orden",
    )

    @api.depends("journal_ids", "date_from", "date_to")
    def _compute_invoices(self):
        for rec in self:
            rec.invoice_ids = rec.env["account.ar.vat.line"].search(
                [
                    ("state", "!=", "draft"),
                    # ('number', '!=', False),
                    # ('internal_number', '!=', False),
                    ("journal_id", "in", rec.journal_ids.ids),
                    ("date", ">=", rec.date_from),
                    ("date", "<=", rec.date_to),
                ]
            )

    @api.depends(
        "type",
        "reference",
    )
    def _compute_name(self):
        date_format = (
            self.env["res.lang"]
            ._lang_get(self._context.get("lang", "en_US"))
            .date_format
        )
        for rec in self:
            if rec.type == "sale":
                ledger_type = _("Sales")
            elif rec.type == "purchase":
                ledger_type = _("Purchases")
            name = _("%s VAT Ledger %s - %s") % (
                ledger_type,
                rec.date_from
                and fields.Date.from_string(rec.date_from).strftime(date_format)
                or "",
                rec.date_to
                and fields.Date.from_string(rec.date_to).strftime(date_format)
                or "",
            )
            if rec.reference:
                name = "%s - %s" % (name, rec.reference)
            rec.name = name

    @api.onchange("company_id")
    def change_company(self):
        if self.type == "sale":
            domain = [("type", "=", "sale")]
        elif self.type == "purchase":
            domain = [("type", "=", "purchase")]
        domain += [
            ("l10n_latam_use_documents", "=", True),
            ("company_id", "=", self.company_id.id),
        ]
        journals = self.env["account.journal"].search(domain)
        self.journal_ids = journals

    def action_present(self):
        self.state = "presented"

    def action_cancel(self):
        self.state = "cancel"

    def action_to_draft(self):
        self.state = "draft"

    def action_print(self):
        self.ensure_one()
        return self.env.ref("l10n_ar_reports.account_vat_ledger_xlsx").report_action(
            self
        )

    # txt for citi / libro iva digital methods

    def format_amount(self, amount, padding=15, decimals=2):
        if amount < 0:
            template = "-{:0>%dd}" % (padding - 1)
        else:
            template = "{:0>%dd}" % (padding)
        return template.format(int(round(abs(amount) * 10**decimals, decimals)))

    @api.depends(
        "REGINFO_CV_CBTE",
        "REGINFO_CV_ALICUOTAS",
        "type",
        # 'period_id.name'
    )
    def _compute_files(self):
        self.ensure_one()
        # segun vimos aca la afip espera "ISO-8859-1" en vez de utf-8
        # http://www.planillasutiles.com.ar/2015/08/
        # como-descargar-los-archivos-de.html
        if self.REGINFO_CV_ALICUOTAS:
            self.aliquots_filename = _("Alicuots_%s_%s.txt") % (
                self.type,
                self.date_to,
                # self.period_id.name
            )
            self.aliquots_file = base64.encodestring(
                self.REGINFO_CV_ALICUOTAS.encode("ISO-8859-1")
            )
        else:
            self.aliquots_file = False
            self.aliquots_filename = False
        if self.REGINFO_CV_COMPRAS_IMPORTACIONES:
            self.import_aliquots_filename = _("Import_Alicuots_%s_%s.txt") % (
                self.type,
                self.date_to,
                # self.period_id.name
            )
            self.import_aliquots_file = base64.encodestring(
                self.REGINFO_CV_COMPRAS_IMPORTACIONES.encode("ISO-8859-1")
            )
        else:
            self.import_aliquots_file = False
            self.import_aliquots_filename = False
        if self.REGINFO_CV_CBTE:
            self.vouchers_filename = _("Vouchers_%s_%s.txt") % (
                self.type,
                self.date_to,
                # self.period_id.name
            )
            self.vouchers_file = base64.encodestring(
                self.REGINFO_CV_CBTE.encode("ISO-8859-1")
            )
        else:
            self.vouchers_file = False
            self.vouchers_filename = False

    def compute_txt_data(self):
        alicuotas = self._get_REGINFO_CV_ALICUOTAS()
        # sacamos todas las lineas y las juntamos
        lines = []
        for k, v in alicuotas.items():
            lines += v
        self.REGINFO_CV_ALICUOTAS = "\r\n".join(lines)

        impo_alicuotas = {}
        if self.type == "purchase":
            impo_alicuotas = self._get_REGINFO_CV_ALICUOTAS(impo=True)
            # sacamos todas las lineas y las juntamos
            lines = []
            for k, v in impo_alicuotas.items():
                lines += v
            self.REGINFO_CV_COMPRAS_IMPORTACIONES = "\r\n".join(lines)
        alicuotas.update(impo_alicuotas)
        self._get_REGINFO_CV_CBTE(alicuotas)

    @api.model
    def _get_partner_document_code_and_number(self, partner):
        """Para un partner devolver codigo de identificación y numero de identificación con el formato esperado
        por los txt"""
        # se exige cuit para todo menos consumidor final
        if partner.l10n_ar_afip_responsibility_type_id.code == "5":
            doc_code = "{:0>2d}".format(
                int(partner.l10n_latam_identification_type_id.l10n_ar_afip_code)
            )
            doc_number = partner.vat or ""
            # limpiamos letras que no son soportadas
            doc_number = re.sub("[^0-9]", "", doc_number)
        elif partner.l10n_ar_afip_responsibility_type_id.code == "9":
            commercial_partner = partner.commercial_partner_id
            doc_number = (
                partner.l10n_ar_vat
                or commercial_partner.country_id.l10n_ar_legal_entity_vat
                if commercial_partner.is_company
                else commercial_partner.country_id.l10n_ar_natural_vat
            )
            doc_code = "80"
        else:
            doc_number = partner.ensure_vat()
            doc_code = "80"
        return doc_code, doc_number.rjust(20, "0")

    @api.model
    def _get_pos_and_invoice_invoice_number(self, invoice):
        res = invoice._l10n_ar_get_document_number_parts(
            invoice.l10n_latam_document_number, invoice.l10n_latam_document_type_id.code
        )
        return "{:0>20d}".format(res["invoice_number"]), "{:0>5d}".format(
            res["point_of_sale"]
        )

    def _get_txt_invoices(self):
        self.ensure_one()
        return self.env["account.move"].search(
            [
                ("id", "in", self.invoice_ids.mapped("move_id").ids),
                ("l10n_latam_document_type_id.code", "!=", False),
            ],
            order="invoice_date asc, name asc, id asc",
        )

    def _get_REGINFO_CV_CBTE(self, alicuotas):
        self.ensure_one()
        res = []
        invoices = self._get_txt_invoices()
        for inv in invoices:
            # si no existe la factura en alicuotas es porque no tienen ninguna
            cant_alicuotas = len(alicuotas.get(inv))

            currency_rate = inv.l10n_ar_currency_rate
            currency_code = inv.currency_id.l10n_ar_afip_code

            invoice_number, pos_number = self._get_pos_and_invoice_invoice_number(inv)
            doc_code, doc_number = self._get_partner_document_code_and_number(
                inv.partner_id
            )

            amounts = inv._l10n_ar_get_amounts(company_currency=True)
            amount_total = (1 if inv.is_inbound() else -1) * inv.amount_total_signed
            vat_amount = amounts["vat_amount"]
            vat_exempt_base_amount = amounts["vat_exempt_base_amount"]
            vat_untaxed_base_amount = amounts["vat_untaxed_base_amount"]
            other_taxes_amount = amounts["other_taxes_amount"]
            vat_perc_amount = amounts["vat_perc_amount"]
            iibb_perc_amount = amounts["iibb_perc_amount"]
            mun_perc_amount = amounts["mun_perc_amount"]
            intern_tax_amount = amounts["intern_tax_amount"]
            perc_imp_nacionales_amount = (
                amounts["profits_perc_amount"] + amounts["other_perc_amount"]
            )

            if vat_exempt_base_amount:
                # operacion con zona franca
                if inv.partner_id.l10n_ar_afip_responsibility_type_id.code == "10":
                    codigo_operacion = "Z"
                # expo al exterior
                elif inv.l10n_latam_document_type_id.l10n_ar_letter == "E":
                    codigo_operacion = "X"
                # operacion exenta
                else:
                    codigo_operacion = "E"
            # despacho de importacion
            elif inv.l10n_latam_document_type_id.code == "66":
                codigo_operacion = "E"
            # operacion no gravada
            elif vat_untaxed_base_amount:
                codigo_operacion = "N"
            else:
                codigo_operacion = " "

            row = [
                # Campo 1: Fecha de comprobante
                inv.invoice_date.strftime("%Y%m%d"),
                # Campo 2: Tipo de Comprobante.
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),
                # Campo 3: Punto de Venta
                pos_number,
                # Campo 4: Número de Comprobante
                # Si se trata de un comprobante de varias hojas, se deberá
                # informar el número de documento de la primera hoja, teniendo
                # en cuenta lo normado en el  artículo 23, inciso a), punto
                # 6., de la Resolución General N° 1.415, sus modificatorias y
                # complementarias.
                # En el supuesto de registrar de manera agrupada por totales
                # diarios, se deberá consignar el primer número de comprobante
                # del rango a considerar.
                invoice_number,
            ]

            if self.type == "sale":
                # Campo 5: Número de Comprobante Hasta.
                # En el resto de los casos se consignará el dato registrado en el campo 4
                row.append(invoice_number)
            else:
                # Campo 5: Despacho de importación
                if inv.l10n_latam_document_type_id.code == "66":
                    row.append((inv.l10n_latam_document_number).rjust(16, "0"))
                else:
                    row.append("".rjust(16, " "))

            row += [
                # Campo 6: Código de documento del comprador.
                doc_code,
                # Campo 7: Número de Identificación del comprador
                doc_number,
                # Campo 8: Apellido y Nombre del comprador.
                inv.commercial_partner_id.name.ljust(30, " ")[:30],
                # Campo 9: Importe Total de la Operación.
                self.format_amount(amount_total),
                # Campo 10: Importe total de conceptos que no integran el precio neto gravado
                self.format_amount(vat_untaxed_base_amount),
            ]

            if self.type == "sale":
                row += [
                    # Campo 11: Percepción a no categorizados
                    # la figura no categorizado / responsable no inscripto no se usa más
                    self.format_amount(0.0),
                    # Campo 12: Importe de operaciones exentas
                    self.format_amount(vat_exempt_base_amount),
                    # Campo 13: Importe de percepciones o pagos a cuenta de impuestos Nacionales
                    self.format_amount(perc_imp_nacionales_amount + vat_perc_amount),
                ]
            else:
                row += [
                    # Campo 11: Importe de operaciones exentas
                    self.format_amount(vat_exempt_base_amount),
                    # Campo 12: Importe de percepciones o pagos a cuenta del Impuesto al Valor Agregado
                    self.format_amount(vat_perc_amount),
                    # Campo 13: Importe de percepciones o pagos a cuenta otros impuestos nacionales
                    self.format_amount(perc_imp_nacionales_amount),
                ]

            row += [
                # Campo 14: Importe de percepciones de ingresos brutos
                self.format_amount(iibb_perc_amount),
                # Campo 15: Importe de percepciones de impuestos municipales
                self.format_amount(mun_perc_amount),
                # Campo 16: Importe de impuestos internos
                self.format_amount(intern_tax_amount),
                # Campo 17: Código de Moneda
                str(currency_code),
                # Campo 18: Tipo de Cambio
                # nueva modalidad de currency_rate
                self.format_amount(currency_rate, padding=10, decimals=6),
                # Campo 19: Cantidad de alícuotas de IVA
                str(cant_alicuotas),
                # Campo 20: Código de operación.
                codigo_operacion,
            ]

            if self.type == "sale":
                row += [
                    # Campo 21: Otros Tributos
                    self.format_amount(other_taxes_amount),
                    # Campo 22: vencimiento comprobante (no figura en
                    # instructivo pero si en aplicativo) para tique y factura
                    # de exportacion no se informa, tmb para algunos otros
                    # pero que tampoco tenemos implementados
                    (
                        inv.l10n_latam_document_type_id.code
                        in [
                            "19",
                            "20",
                            "21",
                            "16",
                            "55",
                            "81",
                            "82",
                            "83",
                            "110",
                            "111",
                            "112",
                            "113",
                            "114",
                            "115",
                            "116",
                            "117",
                            "118",
                            "119",
                            "120",
                            "201",
                            "202",
                            "203",
                            "206",
                            "207",
                            "208",
                            "211",
                            "212",
                            "213",
                        ]
                        and "00000000"
                        or inv.invoice_date_due.strftime("%Y%m%d")
                    ),
                ]
            else:
                # Campo 21: Crédito Fiscal Computable
                if self.prorate_tax_credit:
                    if self.prorate_type == "global":
                        row.append(self.format_amount(0))
                    else:
                        # row.append(self.format_amount(0))
                        # por ahora no implementado pero seria lo mismo que
                        # sacar si prorrateo y que el cliente entre en el txt
                        # en cada comprobante y complete cuando es en
                        # credito fiscal computable
                        raise ValidationError(
                            _(
                                "Para utilizar el prorrateo por comprobante:\n"
                                '1) Exporte los archivos sin la opción "Proratear '
                                'Crédito de Impuestos"\n2) Importe los mismos '
                                "en el aplicativo\n3) En el aplicativo de afip, "
                                "comprobante por comprobante, indique el valor "
                                'correspondiente en el campo "Crédito Fiscal '
                                'Computable"'
                            )
                        )
                else:
                    row.append(self.format_amount(vat_amount))

                liquido_type = inv.l10n_latam_document_type_id.code in [
                    "033",
                    "058",
                    "059",
                    "060",
                    "063",
                ]
                row += [
                    # Campo 22: Otros Tributos
                    self.format_amount(other_taxes_amount),
                    # TODO still not implemented on this three fields for use case with third pary commisioner
                    # Campo 23: CUIT Emisor / Corredor
                    # Se informará sólo si en el campo "Tipo de Comprobante" se consigna '033', '058', '059', '060' ó
                    # '063'. Si para éstos comprobantes no interviene un tercero en la operación, se consignará la
                    # C.U.I.T. del informante. Para el resto de los comprobantes se completará con ceros
                    self.format_amount(
                        liquido_type and inv.company_id.partner_id.ensure_vat() or 0,
                        padding=11,
                    ),
                    # Campo 24: Denominación Emisor / Corredor
                    (liquido_type and inv.company_id.name or "").ljust(30, " ")[:30],
                    # Campo 25: IVA Comisión
                    # Si el campo 23 es distinto de cero se consignará el importe del I.V.A. de la comisión
                    self.format_amount(0),
                ]
            res.append("".join(row))
        self.REGINFO_CV_CBTE = "\r\n".join(res)

    def _get_tax_row(self, invoice, base, code, tax_amount, impo=False):
        self.ensure_one()
        inv = invoice
        invoice_number, pos_number = self._get_pos_and_invoice_invoice_number(inv)
        doc_code, doc_number = self._get_partner_document_code_and_number(
            inv.commercial_partner_id
        )
        if self.type == "sale":
            row = [
                # Campo 1: Tipo de Comprobante
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),
                # Campo 2: Punto de Venta
                pos_number,
                # Campo 3: Número de Comprobante
                invoice_number,
                # Campo 4: Importe Neto Gravado
                self.format_amount(base),
                # Campo 5: Alícuota de IVA.
                str(code).rjust(4, "0"),
                # Campo 6: Impuesto Liquidado.
                self.format_amount(tax_amount),
            ]
        elif impo:
            row = [
                # Campo 1: Despacho de importación.
                (inv.l10n_latam_document_number or inv.name or "").rjust(16, "0"),
                # Campo 2: Importe Neto Gravado
                self.format_amount(base),
                # Campo 3: Alícuota de IVA
                str(code).rjust(4, "0"),
                # Campo 4: Impuesto Liquidado.
                self.format_amount(tax_amount),
            ]
        else:
            row = [
                # Campo 1: Tipo de Comprobante
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),
                # Campo 2: Punto de Venta
                pos_number,
                # Campo 3: Número de Comprobante
                invoice_number,
                # Campo 4: Código de documento del vendedor
                doc_code,
                # Campo 5: Número de identificación del vendedor
                doc_number,
                # Campo 6: Importe Neto Gravado
                self.format_amount(base),
                # Campo 7: Alícuota de IVA.
                str(code).rjust(4, "0"),
                # Campo 8: Impuesto Liquidado.
                self.format_amount(tax_amount),
            ]
        return row

    def _get_REGINFO_CV_ALICUOTAS(self, impo=False):
        """
        Devolvemos un dict para calcular la cantidad de alicuotas cuando
        hacemos los comprobantes
        """
        self.ensure_one()
        res = {}
        # only vat taxes with codes 3, 4, 5, 6, 8, 9 segun:
        # http://contadoresenred.com/regimen-de-informacion-de-compras-y-ventas-rg-3685-como-cargar-la-informacion/
        # empezamos a contar los codigos 1 (no gravado) y 2 (exento) si no hay alicuotas, sumamos una de esta con
        # 0, 0, 0 en detalle usamos mapped por si hay afip codes duplicados (ej. manual y auto)
        if impo:
            invoices = self._get_txt_invoices().filtered(
                lambda r: r.l10n_latam_document_type_id.code == "66"
            )
        else:
            invoices = self._get_txt_invoices().filtered(
                lambda r: r.l10n_latam_document_type_id.code != "66"
            )
        for inv in invoices:
            lines = []
            vat_taxes = inv._get_vat()

            # tipically this is for invoices with zero amount
            if (
                not vat_taxes
                and inv.l10n_latam_document_type_id.purchase_aliquots == "not_zero"
            ):
                lines.append("".join(self._get_tax_row(inv, 0.0, 3, 0.0, impo=impo)))

            # we group by afip_code
            for vat_tax in vat_taxes:
                lines.append(
                    "".join(
                        self._get_tax_row(
                            inv,
                            vat_tax["BaseImp"],
                            vat_tax["Id"],
                            vat_tax["Importe"],
                            impo=impo,
                        )
                    )
                )

            res[inv] = lines
        return res
