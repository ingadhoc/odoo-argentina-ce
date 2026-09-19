##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_repr
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    ##########################
    # Builders zeep (nuevo motor, sin pyafipws)
    # Reusan map_invoice_info/base_map_invoice_info existentes
    ##########################

    def _zeep_get_vat_items(self):
        items = []
        for item in self._get_vat():
            items.append({
                "Id": item["Id"],
                "BaseImp": float_repr(item["BaseImp"], 2) if not isinstance(item.get("BaseImp"), str) else item["BaseImp"],
                "Importe": float_repr(item["Importe"], 2) if not isinstance(item.get("Importe"), str) else item["Importe"],
            })
        return items or None

    def _zeep_get_tributes(self):
        res = []
        not_vat_taxes = self.line_ids.filtered(
            lambda x: x.tax_line_id
            and x.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
        )
        for tax in not_vat_taxes:
            base = sum(
                self.invoice_line_ids.filtered(
                    lambda x: x.tax_ids.filtered(
                        lambda y: y.tax_group_id.l10n_ar_tribute_afip_code
                        == tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
                    )
                ).mapped("price_subtotal")
            )
            res.append({
                "Id": tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code,
                "Desc": tax.tax_line_id.tax_group_id.name,
                "BaseImp": float_repr(base, 2),
                "Alic": 0,
                "Importe": float_repr(tax.price_subtotal, 2),
            })
        return res or None

    def _zeep_get_optionals(self, invoice_info):
        optionals = []
        if invoice_info.get("mipyme_fce"):
            if self.partner_bank_id and self.partner_bank_id.acc_number:
                optionals.append({"Id": 2101, "Valor": self.partner_bank_id.acc_number})
            transmission_type = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("l10n_ar_afipws_fe.fce_transmission", "")
            )
            if transmission_type:
                optionals.append({"Id": 27, "Valor": transmission_type})
        elif int(invoice_info["doc_afip_code"]) in [202, 203, 207, 208, 212, 213]:
            optionals.append({"Id": 22, "Valor": self.afip_fce_es_anulacion and "S" or "N"})
        return optionals or None

    def _zeep_get_related(self, invoice_info, afip_ws):
        related = invoice_info.get("CbteAsoc")
        if not related:
            return None
        parts = self._l10n_ar_get_document_number_parts(
            related.l10n_latam_document_number,
            related.l10n_latam_document_type_id.code,
        )
        if afip_ws == "wsfe":
            vals = {
                "Tipo": related.l10n_latam_document_type_id.code,
                "PtoVta": parts["point_of_sale"],
                "Nro": parts["invoice_number"],
            }
            if self._zeep_is_mipyme(invoice_info):
                vals["Cuit"] = int(self.company_id.vat)
                if related.invoice_date:
                    vals["CbteFch"] = related.invoice_date.strftime("%Y%m%d")
            return vals
        elif afip_ws == "wsfex":
            return {
                "Cbte_tipo": related.l10n_latam_document_type_id.code,
                "Cbte_punto_vta": parts["point_of_sale"],
                "Cbte_nro": parts["invoice_number"],
                "Cbte_cuit": int(self.company_id.vat),
            }
        elif afip_ws == "wsbfe":
            return None
        return None

    def _zeep_is_mipyme(self, invoice_info):
        return int(invoice_info["doc_afip_code"]) in [201, 206, 211]

    def _zeep_preflight(self, invoice_info, afip_ws):
        """Validaciones trasladadas de pyafipws a zeep (fail-fast, obligatorios)."""
        self.ensure_one()
        # Receptor obligatorio (wsfe/wsbfe lo envían; wsfex no lo soporta pero igual se exige el dato)
        receptor = invoice_info.get("condicion_iva_receptor_id")
        if receptor in (False, None, ""):
            raise UserError(_(
                "Condición IVA del receptor es obligatoria (partner %s)."
            ) % (self.partner_id.display_name,))
        try:
            receptor_int = int(receptor)
        except (TypeError, ValueError):
            raise UserError(_(
                "Condición IVA del receptor inválida (%s). Debe ser numérica."
            ) % (receptor,))
        if receptor_int <= 0:
            raise UserError(_("Condición IVA del receptor inválida (%s).") % (receptor,))
        # Cancela misma moneda obligatorio S/N
        cancela = invoice_info.get("cancela_misma_moneda_ext")
        if cancela not in ("S", "N"):
            raise UserError(_(
                "Cancela misma moneda extranjera es obligatorio (S/N) en %s."
            ) % (self.display_name,))
        # Moneda / cotización (RG 5616)
        if not invoice_info.get("moneda_id"):
            raise UserError(_("Moneda AFIP obligatoria en %s.") % (self.display_name,))
        if invoice_info["moneda_id"] != "PES":
            try:
                ctz = float(invoice_info.get("moneda_ctz") or 0)
            except (TypeError, ValueError):
                ctz = 0
            if ctz <= 0:
                raise UserError(_(
                    "Cotización de moneda obligatoria (> 0) para %s en %s."
                ) % (invoice_info["moneda_id"], self.display_name,))
        # Cartas A/M exigen receptor identificado
        letter = self.l10n_latam_document_type_id.l10n_ar_letter
        if letter in ("A", "M") and str(invoice_info.get("tipo_doc")) != "80":
            raise UserError(_(
                "Documentos %s exigen CUIT del receptor (DocTipo 80) en %s."
            ) % (letter, self.display_name,))
        return True

    def zeep_wsfe_request(self, client, invoice_info):
        ArrayOfAlicIva = client.get_type("ns0:ArrayOfAlicIva")
        ArrayOfTributo = client.get_type("ns0:ArrayOfTributo")
        ArrayOfCbteAsoc = client.get_type("ns0:ArrayOfCbteAsoc")
        ArrayOfOpcional = client.get_type("ns0:ArrayOfOpcional")
        related = self._zeep_get_related(invoice_info, "wsfe")
        return {
            "FeCabReq": {
                "CantReg": 1,
                "PtoVta": invoice_info["pos_number"],
                "CbteTipo": invoice_info["doc_afip_code"],
            },
            "FeDetReq": [{
                "FECAEDetRequest": {
                    "Concepto": int(invoice_info["concepto"]),
                    "DocTipo": int(invoice_info["tipo_doc"] or 99),
                    "DocNro": int(invoice_info["nro_doc"] or 0),
                    "CbteDesde": invoice_info["cbt_desde"],
                    "CbteHasta": invoice_info["cbt_hasta"],
                    "CbteFch": invoice_info["fecha_cbte"],
                    "ImpTotal": invoice_info["imp_total"],
                    "ImpTotConc": invoice_info["imp_tot_conc"],
                    "ImpNeto": invoice_info["imp_neto"],
                    "ImpOpEx": invoice_info["imp_op_ex"],
                    "ImpTrib": invoice_info["imp_trib"],
                    "ImpIVA": invoice_info["imp_iva"],
                    "FchServDesde": invoice_info.get("fecha_serv_desde") or False,
                    "FchServHasta": invoice_info.get("fecha_serv_hasta") or False,
                    "FchVtoPago": invoice_info.get("fecha_venc_pago") or False,
                    "MonId": invoice_info["moneda_id"],
                    "MonCotiz": invoice_info["moneda_ctz"],
                    "CanMisMonExt": invoice_info["cancela_misma_moneda_ext"],
                    "CondicionIVAReceptorId": int(invoice_info["condicion_iva_receptor_id"]),
                    "CbtesAsoc": ArrayOfCbteAsoc([related]) if related else None,
                    "Iva": ArrayOfAlicIva(self._zeep_get_vat_items() or []) if self._zeep_get_vat_items() else None,
                    "Tributos": ArrayOfTributo(self._zeep_get_tributes() or []) if self._zeep_get_tributes() else None,
                    "Opcionales": ArrayOfOpcional(self._zeep_get_optionals(invoice_info) or []) if self._zeep_get_optionals(invoice_info) else None,
                }
            }],
        }

    def zeep_wsfex_request(self, client, last_id, invoice_info):
        ArrayOfItem = client.get_type("ns0:ArrayOfItem")
        ArrayOfCmp_asoc = client.get_type("ns0:ArrayOfCmp_asoc")
        related = self._zeep_get_related(invoice_info, "wsfex")
        items = []
        for line in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            items.append({
                "Pro_codigo": line.product_id.default_code or "",
                "Pro_ds": (line.name or "")[:4000],
                "Pro_qty": line.quantity,
                "Pro_umed": line.product_uom_id.l10n_ar_afip_code or 7,
                "Pro_precio_uni": line.price_unit,
                "Pro_total_item": float_repr(line.price_subtotal, 2),
                "Pro_bonificacion": (
                    float_repr(line.price_unit * line.quantity - line.price_subtotal, 2)
                    if line.discount
                    else 0.0
                ),
            })
        return {
            "Id": last_id,
            "Fecha_cbte": invoice_info["fecha_cbte"] if isinstance(invoice_info.get("fecha_cbte"), str) else invoice_info["fecha_cbte"].strftime("%Y%m%d"),
            "Cbte_Tipo": invoice_info["doc_afip_code"],
            "Punto_vta": invoice_info["pos_number"],
            "Cbte_nro": invoice_info["cbte_nro"],
            "Tipo_expo": int(invoice_info["concepto"]),
            "Dst_cmp": invoice_info["country"].l10n_ar_afip_code,
            "Cliente": (invoice_info["commercial_partner"].name or "")[:200],
            "Domicilio_cliente": " - ".join([
                invoice_info["commercial_partner"].name or "",
                invoice_info["commercial_partner"].street or "",
                invoice_info["commercial_partner"].street2 or "",
                invoice_info["commercial_partner"].zip or "",
                invoice_info["commercial_partner"].city or "",
            ])[:300],
            "Id_impositivo": invoice_info["nro_doc"] or "",
            "Moneda_Id": invoice_info["moneda_id"],
            "Moneda_ctz": invoice_info["moneda_ctz"],
            "CanMisMonExt": invoice_info["cancela_misma_moneda_ext"],
            "Obs_comerciales": (self.invoice_payment_term_id.name if self.invoice_payment_term_id else None),
            "Imp_total": invoice_info["imp_total"],
            "Obs": self.narration,
            "Forma_pago": (self.invoice_payment_term_id.name if self.invoice_payment_term_id else None),
            "Idioma_cbte": 1,
            "Incoterms": self.invoice_incoterm_id.code if self.invoice_incoterm_id else None,
            "Incoterms_Ds": (self.invoice_incoterm_id.name[:20] if self.invoice_incoterm_id and self.invoice_incoterm_id.name else None),
            "Permiso_existente": "N" if int(invoice_info["doc_afip_code"]) == 19 and int(invoice_info["concepto"]) == 1 else "",
            "Items": ArrayOfItem(items),
            "Cmps_asoc": ArrayOfCmp_asoc([related]) if related else None,
        }

    def zeep_wsbfe_request(self, client, last_id, invoice_info):
        ArrayOfItem = client.get_type("ns0:ArrayOfItem")
        items = []
        for line in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            if not line.product_uom_id.l10n_ar_afip_code:
                raise UserError(_("Not afip code con producto UOM %s" % (line.product_uom_id.name)))
            vat_tax = line.tax_ids.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code)
            vat_amounts = vat_tax.compute_all(
                line.price_unit, self.currency_id, line.quantity,
                product=line.product_id, partner=self.partner_id,
            ) if vat_tax else {"total_included": line.price_subtotal}
            items.append({
                "Pro_codigo_ncm": line.product_id.l10n_ar_ncm_code or "",
                "Pro_sec": "",
                "Pro_ds": (line.name or "")[:4000],
                "Pro_qty": line.quantity,
                "Pro_umed": line.product_uom_id.l10n_ar_afip_code,
                "Pro_precio_uni": line.price_unit,
                "Imp_bonif": (
                    float_repr(line.price_unit * line.quantity - line.price_subtotal, 2)
                    if line.discount else 0.0
                ),
                "Iva_id": vat_tax.tax_group_id.l10n_ar_vat_afip_code if vat_tax else 3,
                "Imp_total": vat_amounts["total_included"],
            })
        return {
            "Id": last_id,
            "Tipo_doc": int(invoice_info["tipo_doc"] or 99),
            "Nro_doc": int(invoice_info["nro_doc"] or 0),
            "Zona": 1,
            "Tipo_cbte": int(invoice_info["doc_afip_code"]),
            "Punto_vta": int(invoice_info["pos_number"]),
            "Cbte_nro": int(invoice_info["cbte_nro"]),
            "Imp_total": float(invoice_info["imp_total"]),
            "Imp_tot_conc": float(invoice_info["imp_tot_conc"]),
            "Imp_neto": float(invoice_info["imp_neto"]),
            "Impto_liq": float(invoice_info["imp_iva"]),
            "Impto_liq_rni": 0.0,
            "Imp_op_ex": float(invoice_info["imp_op_ex"]),
            "Imp_perc": float(invoice_info["amounts"]["vat_perc_amount"] + invoice_info["amounts"]["profits_perc_amount"] + invoice_info["amounts"]["other_perc_amount"]),
            "Imp_iibb": float(invoice_info["amounts"]["iibb_perc_amount"]),
            "Imp_perc_mun": float(invoice_info["amounts"]["mun_perc_amount"]),
            "Imp_internos": float(invoice_info["amounts"]["intern_tax_amount"] + invoice_info["amounts"]["other_taxes_amount"]),
            "Imp_moneda_Id": invoice_info["moneda_id"],
            "Imp_moneda_ctz": float(invoice_info["moneda_ctz"]),
            "CanMisMonExt": invoice_info["cancela_misma_moneda_ext"],
            "CondicionIVAReceptorId": int(invoice_info["condicion_iva_receptor_id"]),
            "Fecha_cbte": invoice_info["fecha_cbte"],
            "Items": ArrayOfItem(items),
        }

    ##########################
    # Compat pyafipws -> zeep (wrappers para PR fácil)
    ##########################

    def pyafipws_create_invoice(self, ws, invoice_info):
        raise UserError(_("pyafipws removed: invoice data is built with zeep_*_request builders"))

    def wsfe_pyafipws_create_invoice(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsfe_request"))

    def wsmtxca_pyafipws_create_invoice(self, ws, invoice_info):
        raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))

    def wsfex_pyafipws_create_invoice(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsfex_request"))

    def wsbfe_pyafipws_create_invoice(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsbfe_request"))

    def pyafipws_add_info(self, ws, afip_ws, invoice_info):
        raise UserError(_("pyafipws removed: info va incluida en el request zeep"))

    def pyafipws_add_tax(self, ws):
        raise UserError(_("pyafipws removed: ver _zeep_get_vat_items/_zeep_get_tributes"))

    def wsfe_invoice_add_info(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsfe_request"))

    def wsbfe_invoice_add_info(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsbfe_request"))

    def wsfex_invoice_add_info(self, ws, invoice_info):
        raise UserError(_("pyafipws removed, use zeep_wsfex_request"))

    def wsmtxca_invoice_add_info(self, ws, invoice_info):
        raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))

    def pyafipws_request_autorization(self, ws, afip_ws):
        raise UserError(_("pyafipws removed: usar flujo zeep en do_pyafipws_request_cae"))

    def wsfe_request_autorization(self, ws):
        raise UserError(_("pyafipws removed"))

    def wsmtxca_request_autorization(self, ws):
        raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))

    def wsfex_request_autorization(self, ws):
        raise UserError(_("pyafipws removed"))

    def wsbfe_request_autorization(self, ws):
        raise UserError(_("pyafipws removed"))

    ##########################
    # Mapeo datos (se mantiene, sin pyafipws)
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

        # Obligatorios AFIP (antes kwargs silenciosos de pyafipws, ahora validados con zeep).
        # cancela_misma_moneda_ext viene del toggle res.config
        # "Default Policy for Foreign Currency Payments" (S/N/account) y se
        # resuelve por factura en account.move.compute_l10n_ar_payment_foreign_currency.
        cancela = self.l10n_ar_payment_foreign_currency
        if cancela not in ("S", "N"):
            # Fallback: resolver como el compute (por si el stored quedó en False
            # o filtró "account" de compañía en borradores viejos)
            default_value = self.company_id.l10n_ar_payment_foreign_currency
            if default_value == "account":
                account = self.line_ids.account_id.filtered(
                    lambda x: x.account_type == "asset_receivable")
                cancela = "S" if account.currency_id and account.currency_id != self.company_currency_id else "N"
            else:
                cancela = default_value
        if cancela not in ("S", "N"):
            raise UserError(_(
                "Cancela misma moneda extranjera es obligatorio (S/N) en %s. "
                "Revisar en Ajustes → Contabilidad → AFIP WS "
                "“Default Policy for Foreign Currency Payments” o el campo de la factura."
            ) % (self.display_name,))
        invoice_info["cancela_misma_moneda_ext"] = cancela
        receptor_code = self.partner_id.l10n_ar_afip_responsibility_type_id.code
        if not receptor_code:
            raise UserError(_(
                "Condición IVA del receptor es obligatoria. "
                "Configurar responsabilidad AFIP en el partner %s."
            ) % (self.partner_id.display_name,))
        try:
            invoice_info["condicion_iva_receptor_id"] = int(receptor_code)
        except (TypeError, ValueError):
            raise UserError(_(
                "Condición IVA del receptor inválida (%s) en partner %s. "
                "Debe ser numérica (tabla AFIP FEParamGetCondicionIvaReceptor)."
            ) % (receptor_code, self.partner_id.display_name,))

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

        if (
            invoice_info["concepto"] != 1
            and int(invoice_info["doc_afip_code"]) not in [202, 203, 207, 208, 212, 213]
            or invoice_info["mipyme_fce"]
        ):
            invoice_info["fecha_venc_pago"] = self.invoice_date_due or self.invoice_date
        invoice_info["fecha_serv_desde"] = invoice_info["fecha_serv_hasta"] = None

        if int(invoice_info["concepto"]) != 1:
            invoice_info["fecha_serv_desde"] = self.l10n_ar_afip_service_start
            invoice_info["fecha_serv_hasta"] = self.l10n_ar_afip_service_end

        amounts = self._l10n_ar_get_amounts()
        invoice_info["amounts"] = amounts
        invoice_info["imp_total"] = str("%.2f" % self.amount_total)
        invoice_info["imp_tot_conc"] = str("%.2f" % amounts["vat_untaxed_base_amount"])
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
            invoice_info["fecha_venc_pago"] = invoice_info["fecha_venc_pago"].strftime("%Y%m%d")
        if invoice_info["fecha_serv_desde"]:
            invoice_info["fecha_serv_desde"] = invoice_info["fecha_serv_desde"].strftime("%Y%m%d")
        if invoice_info["fecha_serv_hasta"]:
            invoice_info["fecha_serv_hasta"] = invoice_info["fecha_serv_hasta"].strftime("%Y%m%d")
        if invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")
        return invoice_info

    def wsbfe_map_invoice_info(self):
        invoice_info = self.base_map_invoice_info()
        invoice_info["fecha_cbte"] = invoice_info["fecha_cbte"].strftime("%Y%m%d")
        if invoice_info["fecha_venc_pago"]:
            invoice_info["fecha_venc_pago"] = invoice_info["fecha_venc_pago"].strftime("%Y%m%d")
        if invoice_info["fecha_serv_desde"]:
            invoice_info["fecha_serv_desde"] = invoice_info["fecha_serv_desde"].strftime("%Y%m%d")
        if invoice_info["fecha_serv_hasta"]:
            invoice_info["fecha_serv_hasta"] = invoice_info["fecha_serv_hasta"].strftime("%Y%m%d")
        if invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")
        invoice_info["zona"] = 1
        invoice_info["impto_liq_rni"] = 0.0
        invoice_info["imp_iibb"] = invoice_info["amounts"]["iibb_perc_amount"]
        invoice_info["imp_perc_mun"] = invoice_info["amounts"]["mun_perc_amount"]
        invoice_info["imp_internos"] = (
            invoice_info["amounts"]["intern_tax_amount"] + invoice_info["amounts"]["other_taxes_amount"]
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
            raise UserError(_('For WS "%s" country is required on partner' % (self.journal_id.afip_ws)))
        elif not country.code:
            raise UserError(_('For WS "%s" country code is mandatory Country: %s' % (self.journal_id.afip_ws, country.name)))
        elif not country.l10n_ar_afip_code:
            raise UserError(_('For WS "%s" country afip code is mandatory Country: %s' % (self.journal_id.afip_ws, country.name)))
        if invoice_info["afip_associated_period_from"] and invoice_info["afip_associated_period_to"]:
            invoice_info["afip_associated_period_from"] = invoice_info["afip_associated_period_from"].strftime("%Y%m%d")
            invoice_info["afip_associated_period_to"] = invoice_info["afip_associated_period_to"].strftime("%Y%m%d")
        if self.invoice_incoterm_id:
            invoice_info["incoterms"] = self.invoice_incoterm_id.code
            incoterms_ds = self.invoice_incoterm_id.name
            invoice_info["incoterms_ds"] = incoterms_ds and incoterms_ds[:20]
        else:
            invoice_info["incoterms"] = invoice_info["incoterms_ds"] = None
            if int(invoice_info["doc_afip_code"]) == 19 and invoice_info["tipo_expo"] == 1:
                invoice_info["permiso_existente"] = "N"
            else:
                invoice_info["permiso_existente"] = ""
            invoice_info["obs_generales"] = self.narration
            if self.invoice_payment_term_id:
                invoice_info["forma_pago"] = self.invoice_payment_term_id.name
                invoice_info["obs_comerciales"] = self.invoice_payment_term_id.name
            else:
                invoice_info["forma_pago"] = invoice_info["obs_comerciales"] = None
            invoice_info["fecha_pago"] = (
                datetime.strftime(self.invoice_date_due, "%Y%m%d")
                if int(invoice_info["doc_afip_code"]) == 19
                and invoice_info["tipo_expo"] in [2, 4]
                and self.invoice_date_due
                else ""
            )
            invoice_info["idioma_cbte"] = 1
            invoice_info["nombre_cliente"] = self.commercial_partner.name
            if invoice_info["nro_doc"]:
                invoice_info["id_impositivo"] = invoice_info["nro_doc"]
                invoice_info["cuit_pais_cliente"] = None
            elif invoice_info["country"].code != "AR" and invoice_info["nro_doc"]:
                invoice_info["id_impositivo"] = None
                if self.commercial_partner.is_company:
                    invoice_info["cuit_pais_cliente"] = invoice_info["country"].cuit_juridica
                else:
                    invoice_info["cuit_pais_cliente"] = invoice_info["country"].cuit_fisica
                if not invoice_info["cuit_pais_cliente"]:
                    raise UserError(_("No vat defined for the partner and also no CUIT set on country"))
                invoice_info["domicilio_cliente"] = " - ".join([
                    self.commercial_partner.name or "",
                    self.commercial_partner.street or "",
                    self.commercial_partner.street2 or "",
                    self.commercial_partner.zip or "",
                    self.commercial_partner.city or "",
                ])
                invoice_info["pais_dst_cmp"] = self.commercial_partner.country_id.l10n_ar_afip_code
        invoice_info["lines"] = self.invoice_map_info_lines()
        return invoice_info

    def wsmtxca_map_invoice_info(self):
        raise UserError(_("AFIP WS wsmtxca not implemented with zeep yet"))

    def invoice_map_info_lines(self):
        lines = []
        for line in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            line_temp = {}
            line_temp["codigo"] = line.product_id.default_code
            if not line.product_uom_id:
                line_temp["umed"] = "7"
            elif not line.product_uom_id.l10n_ar_afip_code:
                raise UserError(_("Not afip code con producto UOM %s" % (line.product_uom_id.name)))
            else:
                line_temp["umed"] = line.product_uom_id.l10n_ar_afip_code
            line_temp["ds"] = line.name
            line_temp["qty"] = line.quantity
            line_temp["precio"] = line.price_unit
            line_temp["importe"] = line.price_subtotal
            line_temp["bonif"] = (
                line.discount
                and str("%.2f" % (line_temp["precio"] * line_temp["qty"] - line_temp["importe"]))
                or None
            )
            line_temp["iva_id"] = line.vat_tax_id.tax_group_id.l10n_ar_vat_afip_code
            vat_taxes_amounts = line.vat_tax_id.compute_all(
                line.price_unit, self.currency_id, line.quantity,
                product=line.product_id, partner=self.partner_id,
            )
            line_temp["imp_iva"] = sum([x["amount"] for x in vat_taxes_amounts["taxes"]])
            lines.append(line_temp)
        return lines

    def pyafipws_get_currency_rate(self, ws=None):
        self.ensure_one()
        afip_ws = self.journal_id.afip_ws
        connection = self.company_id.get_connection(afip_ws)
        client, auth, transport = connection.connect()
        if afip_ws == "wsfe":
            response = client.service.FEParamGetCotizacion(auth, self.currency_id.l10n_ar_afip_code)
            return response.ResultGet.Cotizacion
        elif afip_ws == "wsfex":
            response = client.service.FEXGetPARAM_Ctz(auth, self.currency_id.l10n_ar_afip_code)
            return response.FEXResultGet.Ctz
        return _("AFIP WS %s not implemented") % afip_ws
