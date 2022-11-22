##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    ##########################
    # CREAR FACTURA en pyafipws
    ##########################

    def pyafipws_create_invoice(self, ws, invoice_info):
        self.ensure_one()
        afip_ws = self.journal_id.afip_ws
        if not afip_ws:
            return
        if hasattr(self, "%s_pyafipws_create_invoice" % afip_ws):
            return getattr(self, "%s_pyafipws_create_invoice" % afip_ws)(
                ws, invoice_info
            )
        else:
            return _("AFIP WS %s not implemented") % afip_ws

    def wsfe_pyafipws_create_invoice(self, ws, invoice_info):
        ws.CrearFactura(
            invoice_info["concepto"],
            invoice_info["tipo_doc"],
            invoice_info["nro_doc"],
            invoice_info["doc_afip_code"],
            invoice_info["pos_number"],
            invoice_info["cbt_desde"],
            invoice_info["cbt_hasta"],
            invoice_info["imp_total"],
            invoice_info["imp_tot_conc"],
            invoice_info["imp_neto"],
            invoice_info["imp_iva"],
            invoice_info["imp_trib"],
            invoice_info["imp_op_ex"],
            invoice_info["fecha_cbte"],
            invoice_info["fecha_venc_pago"],
            invoice_info["fecha_serv_desde"],
            invoice_info["fecha_serv_hasta"],
            invoice_info["moneda_id"],
            invoice_info["moneda_ctz"],
        )

    def wsmtxca_pyafipws_create_invoice(self, ws, invoice_info):
        ws.CrearFactura(
            invoice_info["concepto"],
            invoice_info["tipo_doc"],
            invoice_info["nro_doc"],
            invoice_info["doc_afip_code"],
            invoice_info["pos_number"],
            invoice_info["cbt_desde"],
            invoice_info["cbt_hasta"],
            invoice_info["imp_total"],
            invoice_info["imp_tot_conc"],
            invoice_info["imp_neto"],
            invoice_info["imp_subtotal"],
            invoice_info["imp_trib"],
            invoice_info["imp_op_ex"],
            invoice_info["fecha_cbte"],
            invoice_info["fecha_venc_pago"],
            invoice_info["fecha_serv_desde"],
            invoice_info["fecha_serv_hasta"],
            invoice_info["moneda_id"],
            invoice_info["moneda_ctz"],
            invoice_info["obs_generales"],
        )

    def wsfex_pyafipws_create_invoice(self, ws, invoice_info):
        ws.CrearFactura(
            invoice_info["doc_afip_code"],
            invoice_info["pos_number"],
            invoice_info["cbte_nro"],
            invoice_info["fecha_cbte"],
            invoice_info["imp_total"],
            invoice_info["tipo_expo"],
            invoice_info["permiso_existente"],
            invoice_info["pais_dst_cmp"],
            invoice_info["nombre_cliente"],
            invoice_info["cuit_pais_cliente"],
            invoice_info["domicilio_cliente"],
            invoice_info["id_impositivo"],
            invoice_info["moneda_id"],
            invoice_info["moneda_ctz"],
            invoice_info["obs_comerciales"],
            invoice_info["obs_generales"],
            invoice_info["forma_pago"],
            invoice_info["incoterms"],
            invoice_info["idioma_cbte"],
            invoice_info["incoterms_ds"],
            invoice_info["fecha_pago"],
        )

    def wsbfe_pyafipws_create_invoice(self, ws, invoice_info):

        ws.CrearFactura(
            invoice_info["tipo_doc"],
            invoice_info["nro_doc"],
            invoice_info["zona"],
            invoice_info["doc_afip_code"],
            invoice_info["pos_number"],
            invoice_info["cbte_nro"],
            invoice_info["fecha_cbte"],
            invoice_info["imp_total"],
            invoice_info["imp_neto"],
            invoice_info["imp_iva"],
            invoice_info["imp_tot_conc"],
            invoice_info["impto_liq_rni"],
            invoice_info["imp_op_ex"],
            invoice_info["imp_perc"],
            invoice_info["imp_iibb"],
            invoice_info["imp_perc_mun"],
            invoice_info["imp_internos"],
            invoice_info["moneda_id"],
            invoice_info["moneda_ctz"],
            invoice_info["fecha_venc_pago"],
        )

    ##########################
    # Agrego informacion complemetaria a la factura
    # Ya creada en pyafipws
    ##########################

    def pyafipws_add_info(self, ws, afip_ws, invoice_info):
        self.ensure_one()
        if hasattr(self, "%s_invoice_add_info" % afip_ws):
            return getattr(self, "%s_invoice_add_info" % afip_ws)(ws, invoice_info)
        else:
            return _("AFIP WS %s not implemented") % afip_ws

    def pyafipws_add_tax(self, ws):
        vat_items = self._get_vat()
        for item in vat_items:
            ws.AgregarIva(item['Id'], "%.2f" % item['BaseImp'], "%.2f" % item['Importe'])

        not_vat_taxes = self.line_ids.filtered(
            lambda x: x.tax_line_id
            and x.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
        )
        for tax in not_vat_taxes:
            ws.AgregarTributo(
                tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code,
                tax.tax_line_id.tax_group_id.name,
                "%.2f"
                % sum(
                    self.invoice_line_ids.filtered(
                        lambda x: x.tax_ids.filtered(
                            lambda y: y.tax_group_id.l10n_ar_tribute_afip_code
                            == tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
                        )
                    ).mapped("price_subtotal")
                ),
                # "%.2f" % abs(tax.base_amount),
                # TODO pasar la alicuota
                # como no tenemos la alicuota pasamos cero, en v9
                # podremos pasar la alicuota
                0,
                "%.2f" % tax.price_subtotal,
            )

    def wsfe_invoice_add_info(self, ws, invoice_info):
        if invoice_info["mipyme_fce"]:
            # agregamos cbu para factura de credito electronica
            ws.AgregarOpcional(opcional_id=2101, valor=self.partner_bank_id.acc_number)
            # agregamos tipo de transmision si esta definido
            transmission_type = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("l10n_ar_afipws_fe.fce_transmission", "")
            )
            if transmission_type:
                ws.AgregarOpcional(opcional_id=27, valor=transmission_type)
        elif int(invoice_info["doc_afip_code"]) in [202, 203, 207, 208, 212, 213]:
            valor = self.afip_fce_es_anulacion and "S" or "N"
            ws.AgregarOpcional(opcional_id=22, valor=valor)

        if invoice_info["CbteAsoc"]:
            doc_number_parts = self._l10n_ar_get_document_number_parts(
                invoice_info["CbteAsoc"].l10n_latam_document_number,
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
            )
            ws.AgregarCmpAsoc(
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
                doc_number_parts["point_of_sale"],
                doc_number_parts["invoice_number"],
                self.company_id.vat,
                invoice_info["CbteAsoc"].invoice_date.strftime("%Y%m%d"),
            )
        if  invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            ws.AgregarPeriodoComprobantesAsociados(invoice_info["afip_associated_period_from"],invoice_info["afip_associated_period_to"])
        self.pyafipws_add_tax(ws)

    def wsbfe_invoice_add_info(self, ws, invoice_info):
        if invoice_info["mipyme_fce"]:
            # agregamos cbu para factura de credito electronica
            ws.AgregarOpcional(opcional_id=2101, valor=self.partner_bank_id.acc_number)
            # agregamos tipo de transmision si esta definido
            transmission_type = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("l10n_ar_afipws_fe.fce_transmission", "")
            )
            if transmission_type:
                ws.AgregarOpcional(opcional_id=27, valor=transmission_type)
        elif int(invoice_info["doc_afip_code"]) in [202, 203, 207, 208, 212, 213]:
            valor = self.afip_fce_es_anulacion and "S" or "N"
            ws.AgregarOpcional(opcional_id=22, valor=valor)

        if invoice_info["CbteAsoc"]:
            doc_number_parts = self._l10n_ar_get_document_number_parts(
                invoice_info["CbteAsoc"].l10n_latam_document_number,
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
            )
            ws.AgregarCmpAsoc(
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
                doc_number_parts["point_of_sale"],
                doc_number_parts["invoice_number"],
                self.company_id.vat,
                invoice_info["CbteAsoc"].invoice_date.strftime("%Y%m%d"),
            )
        for line in invoice_info["line"]:
            ws.AgregarItem(
                line["codigo"],
                line["sec"],
                line["ds"],
                line["qty"],
                line["umed"],
                line["precio"],
                line["bonif"],
                line["iva_id"],
                line["importe"] + line["imp_iva"],
            )

    def wsfex_invoice_add_info(self, ws, invoice_info):

        if invoice_info["CbteAsoc"]:
            doc_number_parts = self._l10n_ar_get_document_number_parts(
                invoice_info["CbteAsoc"].l10n_latam_document_number,
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
            )
            ws.AgregarCmpAsoc(
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
                doc_number_parts["point_of_sale"],
                doc_number_parts["invoice_number"],
                self.company_id.vat,
            )

        for line in invoice_info["line"]:
            ws.AgregarItem(
                line["codigo"],
                line["ds"],
                line["qty"],
                line["umed"],
                line["precio"],
                "%.2f" % line["importe"],
                line["bonif"],
            )

    def wsmtxca_invoice_add_info(self, ws, invoice_info):

        if invoice_info["CbteAsoc"]:
            doc_number_parts = self._l10n_ar_get_document_number_parts(
                invoice_info["CbteAsoc"].l10n_latam_document_number,
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
            )
            ws.AgregarCmpAsoc(
                invoice_info["CbteAsoc"].l10n_latam_document_type_id.code,
                doc_number_parts["point_of_sale"],
                doc_number_parts["invoice_number"],
                self.company_id.vat,
                invoice_info["CbteAsoc"].invoice_date.strftime("%Y-%m-%d"),
            )
        self.pyafipws_add_tax(ws)

    ##########################
    # Autorizo en afip la factura
    ##########################

    def pyafipws_request_autorization(self, ws, afip_ws):
        self.ensure_one()

        if hasattr(self, "%s_request_autorization" % afip_ws):
            return getattr(self, "%s_request_autorization" % afip_ws)(ws)
        else:
            return _("AFIP WS %s not implemented") % afip_ws

    def wsfe_request_autorization(self, ws):
        ws.CAESolicitar()

    def wsmtxca_request_autorization(self, ws):
        ws.AutorizarComprobante()

    def wsfex_request_autorization(self, ws):
        ws.Authorize(self.id)

    def wsbfe_request_autorization(self, ws):
        ws.Authorize(self.id)

    ##########################
    # Mapeo datos del la factura
    ##########################

    def map_invoice_info(self, afip_ws):
        self.ensure_one()
        _logger.info("%s_map_invoice_info" % afip_ws)
        if hasattr(self, "%s_map_invoice_info" % afip_ws):
            return getattr(self, "%s_map_invoice_info" % afip_ws)()
        else:
            return _("AFIP WS %s not implemented") % afip_ws

    def base_map_invoice_info(self):
        journal = self.journal_id
        invoice_info = {}

        invoice_info["commercial_partner"] = self.commercial_partner_id
        invoice_info["country"] = invoice_info["commercial_partner"].country_id
        invoice_info["journal"] = self.journal_id
        invoice_info["pos_number"] = journal.l10n_ar_afip_pos_number
        invoice_info["doc_afip_code"] = self.l10n_latam_document_type_id.code
        invoice_info["ws_next_invoice_number"] = (
            int(
                self.journal_id.get_pyafipws_last_invoice(
                    self.l10n_latam_document_type_id
                )
            )
            + 1
        )

        invoice_info["partner_id_code"] = invoice_info[
            "commercial_partner"
        ].l10n_latam_identification_type_id.l10n_ar_afip_code
        invoice_info["tipo_doc"] = invoice_info["partner_id_code"] or "99"
        invoice_info["nro_doc"] = (
            invoice_info["partner_id_code"]
            and invoice_info["commercial_partner"].vat
            or "0"
        )
        invoice_info["cbt_desde"] = invoice_info["cbt_hasta"] = invoice_info[
            "cbte_nro"
        ] = invoice_info["ws_next_invoice_number"]
        invoice_info["concepto"] = invoice_info["tipo_expo"] = int(
            self.l10n_ar_afip_concept
        )

        invoice_info["fecha_cbte"] = self.invoice_date or fields.Date.today()
        invoice_info["mipyme_fce"] = int(invoice_info["doc_afip_code"]) in [
            201,
            206,
            211,
        ]
        invoice_info["fecha_venc_pago"] = None

        # due date only for concept "services" and mipyme_fce
        if (
            invoice_info["concepto"] != 1
            and int(invoice_info["doc_afip_code"]) not in [202, 203, 207, 208, 212, 213]
            or invoice_info["mipyme_fce"]
        ):
            invoice_info["fecha_venc_pago"] = self.invoice_date_due or self.invoice_date
        invoice_info["fecha_serv_desde"] = invoice_info["fecha_serv_hasta"] = None

        # fecha de servicio solo si no es 1
        if int(invoice_info["concepto"]) != 1:
            invoice_info["fecha_serv_desde"] = self.l10n_ar_afip_service_start
            invoice_info["fecha_serv_hasta"] = self.l10n_ar_afip_service_end

        amounts = self._l10n_ar_get_amounts()
        invoice_info["amounts"] = amounts
        # invoice amount totals:
        invoice_info["imp_total"] = str("%.2f" % self.amount_total)
        # ImpTotConc es el iva no gravado
        invoice_info["imp_tot_conc"] = str("%.2f" % amounts["vat_untaxed_base_amount"])
        # tal vez haya una mejor forma, la idea es que para facturas c
        # no se pasa iva. Probamos hacer que vat_taxable_amount
        # incorpore a los imp cod 0, pero en ese caso termina reportando
        # iva y no lo queremos
        if self.l10n_latam_document_type_id.l10n_ar_letter == "C":
            invoice_info["imp_neto"] = str("%.2f" % self.amount_untaxed)
        else:
            invoice_info["imp_neto"] = str("%.2f" % amounts["vat_taxable_amount"])

        invoice_info["imp_iva"] = str("%.2f" % amounts["vat_amount"])
        invoice_info["imp_trib"] = str("%.2f" % amounts["not_vat_taxes_amount"])
        invoice_info["imp_op_ex"] = str("%.2f" % amounts["vat_exempt_base_amount"])
        invoice_info["moneda_id"] = self.currency_id.l10n_ar_afip_code
        invoice_info["moneda_ctz"] = self.l10n_ar_currency_rate or 1
        invoice_info["CbteAsoc"] = self.get_related_invoices_data()

        invoice_info["afip_associated_period_from"] = self.afip_associated_period_from
        invoice_info["afip_associated_period_to"] = self.afip_associated_period_to
        return invoice_info

    def wsfe_map_invoice_info(self):
        invoice_info = self.base_map_invoice_info()
        invoice_info["fecha_cbte"] = invoice_info["fecha_cbte"].strftime("%Y%m%d")
        if invoice_info["fecha_venc_pago"]:
            invoice_info["fecha_venc_pago"] = invoice_info["fecha_venc_pago"].strftime(
                "%Y%m%d"
            )
        if invoice_info["fecha_serv_desde"]:
            invoice_info["fecha_serv_desde"] = invoice_info[
                "fecha_serv_desde"
            ].strftime("%Y%m%d")
        if invoice_info["fecha_serv_hasta"]:
            invoice_info["fecha_serv_hasta"] = invoice_info[
                "fecha_serv_hasta"
            ].strftime("%Y%m%d")
        if  invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")

        return invoice_info

    def wsbfe_map_invoice_info(self):
        invoice_info = self.base_map_invoice_info()
        invoice_info["fecha_cbte"] = invoice_info["fecha_cbte"].strftime("%Y%m%d")
        if invoice_info["fecha_venc_pago"]:
            invoice_info["fecha_venc_pago"] = invoice_info["fecha_venc_pago"].strftime(
                "%Y%m%d"
            )
        if invoice_info["fecha_serv_desde"]:
            invoice_info["fecha_serv_desde"] = invoice_info[
                "fecha_serv_desde"
            ].strftime("%Y%m%d")
        if invoice_info["fecha_serv_hasta"]:
            invoice_info["fecha_serv_hasta"] = invoice_info[
                "fecha_serv_hasta"
            ].strftime("%Y%m%d")

        if  invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")


        invoice_info["zona"] = 1  # Nacional (la unica devuelta por afip)
        # los responsables no inscriptos no se usan mas
        invoice_info["impto_liq_rni"] = 0.0
        invoice_info["imp_iibb"] = invoice_info["amounts"]["iibb_perc_amount"]
        invoice_info["imp_perc_mun"] = invoice_info["amounts"]["mun_perc_amount"]
        invoice_info["imp_internos"] = (
            invoice_info["amounts"]["intern_tax_amount"]
            + invoice_info["amounts"]["other_taxes_amount"]
        )
        invoice_info["imp_perc"] = (
            invoice_info["amounts"]["vat_perc_amount"]
            + invoice_info["amounts"]["profits_perc_amount"]
            + invoice_info["amounts"]["other_perc_amount"]
        )
        invoice_info["lines"] = self.invoice_map_info_lines()

        return invoice_info

    def wsfex_map_invoice_info(self):
        invoice_info = self.base_map_invoice_info()
        country = invoice_info["country"]
        if not country:
            raise UserError(
                _(
                    'For WS "%s" country is required on partner'
                    % (self.journal_id.afip_ws)
                )
            )
        elif not country.code:
            raise UserError(
                _(
                    'For WS "%s" country code is mandatory'
                    "Country: %s" % (self.journal_id.afip_ws, country.name)
                )
            )
        elif not country.l10n_ar_afip_code:
            raise UserError(
                _(
                    'For WS "%s" country afip code is mandatory'
                    "Country: %s" % (self.journal_id.afip_ws, country.name)
                )
            )
        if  invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")

        if self.invoice_incoterm_id:
            invoice_info["incoterms"] = self.invoice_incoterm_id.code
            incoterms_ds = self.invoice_incoterm_id.name
            # máximo de 20 caracteres admite
            invoice_info["incoterms_ds"] = incoterms_ds and incoterms_ds[:20]
        else:
            invoice_info["incoterms"] = invoice_info["incoterms_ds"] = None
            # por lo que verificamos, se pide permiso existente solo
            # si es tipo expo 1 y es factura (codigo 19), para todo el
            # resto pasamos cadena vacia
            if (
                int(invoice_info["doc_afip_code"]) == 19
                and invoice_info["tipo_expo"] == 1
            ):
                # TODO investigar si hay que pasar si ("S")
                invoice_info["permiso_existente"] = "N"
            else:
                invoice_info["permiso_existente"] = ""
            invoice_info["obs_generales"] = self.narration

            if self.invoice_payment_term_id:
                invoice_info["forma_pago"] = self.invoice_payment_term_id.name
                invoice_info["obs_comerciales"] = self.invoice_payment_term_id.name
            else:
                invoice_info["forma_pago"] = invoice_info["obs_comerciales"] = None

            # 1671 Report fecha_pago with format YYYMMDD
            # 1672 Is required only doc_type 19. concept (2,4)
            # 1673 If doc_type != 19 should not be reported.
            # 1674 doc_type 19 concept (2,4). date should be >= invoice
            # date
            invoice_info["fecha_pago"] = (
                datetime.strftime(self.invoice_date_due, "%Y%m%d")
                if int(invoice_info["doc_afip_code"]) == 19
                and invoice_info["tipo_expo"] in [2, 4]
                and self.invoice_date_due
                else ""
            )

            # invoice language: spanish / español
            invoice_info["idioma_cbte"] = 1

            # TODO tal vez podemos unificar este criterio con el del
            # citi que pide el cuit al partner
            # customer data (foreign trade):
            invoice_info["nombre_cliente"] = self.commercial_partner.name
            # se debe informar cuit pais o id_impositivo
            if invoice_info["nro_doc"]:
                invoice_info["id_impositivo"] = invoice_info["nro_doc"]
                invoice_info["cuit_pais_cliente"] = None
            elif invoice_info["country"].code != "AR" and invoice_info["nro_doc"]:
                invoice_info["id_impositivo"] = None
                if self.commercial_partner.is_company:
                    invoice_info["cuit_pais_cliente"] = invoice_info[
                        "country"
                    ].cuit_juridica
                else:
                    invoice_info["cuit_pais_cliente"] = invoice_info[
                        "country"
                    ].cuit_fisica
                if not invoice_info["cuit_pais_cliente"]:
                    raise UserError(
                        _(
                            "No vat defined for the partner and also no CUIT "
                            "set on country"
                        )
                    )

                invoice_info["domicilio_cliente"] = " - ".join(
                    [
                        self.commercial_partner.name or "",
                        self.commercial_partner.street or "",
                        self.commercial_partner.street2 or "",
                        self.commercial_partner.zip or "",
                        self.commercial_partner.city or "",
                    ]
                )
                invoice_info[
                    "pais_dst_cmp"
                ] = self.commercial_partner.country_id.l10n_ar_afip_code
        invoice_info["lines"] = self.invoice_map_info_lines()

        return invoice_info

    def wsmtxca_map_invoice_info(self):
        invoice_info = self.base_map_invoice_info()
        invoice_info["fecha_cbte"] = invoice_info["fecha_cbte"].strftime("%Y%m%d")
        if invoice_info["fecha_venc_pago"]:
            invoice_info["fecha_venc_pago"] = invoice_info["fecha_venc_pago"].strftime(
                "%Y%m%d"
            )
        if invoice_info["fecha_serv_desde"]:
            invoice_info["fecha_serv_desde"] = invoice_info[
                "fecha_serv_desde"
            ].strftime("%Y%m%d")
        if invoice_info["fecha_serv_hasta"]:
            invoice_info["fecha_serv_hasta"] = invoice_info[
                "fecha_serv_hasta"
            ].strftime("%Y%m%d")
        invoice_info["obs_generales"] = self.comment
        invoice_info["lines"] = self.invoice_map_info_lines()
        return invoice_info

    def invoice_map_info_lines(self):
        lines = []
        for line in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            line_temp = {}
            line_temp["codigo"] = line.product_id.default_code
            # unidad de referencia del producto si se comercializa
            # en una unidad distinta a la de consumo
            # uom is not mandatory, if no UOM we use "unit"
            if not line.product_uom_id:
                line_temp["umed"] = "7"
            elif not line.product_uom_id.l10n_ar_afip_code:
                raise UserError(
                    _("Not afip code con producto UOM %s" % (line.product_uom_id.name))
                )
            else:
                line_temp["umed"] = line.product_uom_id.l10n_ar_afip_code
            # cod_mtx = line.uom_id.l10n_ar_afip_code
            line_temp["ds"] = line.name
            line_temp["qty"] = line.quantity
            line_temp["precio"] = line.price_unit
            line_temp["importe"] = line.price_subtotal
            # calculamos bonificacion haciendo teorico menos importe
            line_temp["bonif"] = (
                line.discount
                and str(
                    "%.2f"
                    % (line_temp["precio"] * line_temp["qty"] - line_temp["importe"])
                )
                or None
            )
            line_temp["iva_id"] = line.vat_tax_id.tax_group_id.l10n_ar_vat_afip_code
            vat_taxes_amounts = line.vat_tax_id.compute_all(
                line.price_unit,
                self.currency_id,
                line.quantity,
                product=line.product_id,
                partner=self.partner_id,
            )
            line_temp["imp_iva"] = sum(
                [x["amount"] for x in vat_taxes_amounts["taxes"]]
            )
            lines.append(line_temp)

            return lines
