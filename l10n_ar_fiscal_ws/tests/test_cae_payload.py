##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.tests import tagged

from .common import TestFiscalWsCommon


@tagged("post_install", "-at_install")
class TestCaePayload(TestFiscalWsCommon):
    """What each service is asked to authorize, built from the invoice without calling it."""

    def test_wsfe_payload(self):
        """The domestic service takes the amounts of the voucher, with no lines."""
        invoice = self._new_invoice(self.journal_wsfe)
        self._number_it(invoice)
        payload = self._build_cae_request(invoice)
        voucher = payload["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]

        with self.subTest("el encabezado lleva el punto de venta y el tipo de comprobante"):
            header = payload["FeCAEReq"]["FeCabReq"]
            self.assertEqual(header["CantReg"], 1)
            self.assertEqual(header["PtoVta"], int(self.journal_wsfe.l10n_ar_afip_pos_number))
            self.assertEqual(header["CbteTipo"], int(invoice.l10n_latam_document_type_id.code))

        with self.subTest("el comprobante informa el mismo número que lleva la factura"):
            parts = invoice._l10n_ar_get_document_number_parts(
                invoice.l10n_latam_document_number, invoice.l10n_latam_document_type_id.code
            )
            self.assertEqual(voucher["CbteDesde"], parts["invoice_number"])
            self.assertEqual(voucher["CbteHasta"], parts["invoice_number"])

        with self.subTest("la fecha va en el formato que pide el servicio"):
            self.assertEqual(voucher["CbteFch"], self.today.strftime("%Y%m%d"))

        with self.subTest("los importes cierran contra el total"):
            self.assert_payload_amounts_add_up("wsfe", voucher)

        with self.subTest("en pesos no se informa cotización"):
            self.assertEqual(voucher["MonId"], "PES")
            self.assertNotIn("MonCotiz", voucher)

        self.assert_invoice_is_sound(invoice)

    def test_wsbfe_payload(self):
        """The fiscal bond service takes the amounts and the lines."""
        invoice = self._new_invoice(self.journal_wsbfe)
        invoice.invoice_line_ids.product_id.l10n_ar_ncm_code = "1234.56"
        self._number_it(invoice)
        voucher = self._build_cae_request(invoice)["Cmp"]

        with self.subTest("el pedido lleva el id que el servicio exige"):
            self.assertEqual(voucher["Id"], 1)

        with self.subTest("la zona es la única que informa ARCA"):
            self.assertEqual(voucher["Zona"], 1)

        with self.subTest("la fecha va en el formato que pide el servicio"):
            self.assertEqual(voucher["Fecha_cbte"], self.today.strftime("%Y%m%d"))

        with self.subTest("los importes cierran contra el total"):
            self.assert_payload_amounts_add_up("wsbfe", voucher)

        with self.subTest("cada línea viaja con su código NCM y su código de IVA"):
            items = voucher["Items"]["Item"]
            self.assertEqual(len(items), len(invoice.invoice_line_ids))
            self.assertEqual(items[0]["Pro_codigo_ncm"], "1234.56")
            self.assertTrue(items[0]["Iva_id"])

        with self.subTest("los ítems suman el total del comprobante"):
            self.assert_items_add_up_to_total(voucher, "Imp_total")

        self.assert_invoice_is_sound(invoice)

    def test_wsfex_payload(self):
        """The export service takes the customer abroad and the lines, and no VAT."""
        invoice = self._new_invoice(
            self.journal_wsfex,
            partner=self.partner_export,
            invoice_line_ids=[self._prepare_invoice_line(price_unit=100, tax_ids=self.tax_iva_exento)],
        )
        self._number_it(invoice)
        voucher = self._build_cae_request(invoice)["Cmp"]

        with self.subTest("el comprobante identifica al cliente del exterior"):
            self.assertEqual(voucher["Cliente"], self.partner_export.name)
            self.assertEqual(voucher["Dst_cmp"], int(self.partner_export.country_id.l10n_ar_afip_code))
            self.assertIn(self.partner_export.city, voucher["Domicilio_cliente"])

        with self.subTest("el idioma del comprobante es castellano"):
            self.assertEqual(voucher["Idioma_cbte"], 1)

        with self.subTest("los ítems suman el total del comprobante"):
            self.assert_items_add_up_to_total(voucher, "Pro_total_item")

        self.assert_invoice_is_sound(invoice)

    def test_the_period_replaces_the_related_document(self):
        """The authority takes one or the other: a note pointing at an invoice reports no period."""
        note = self._new_invoice(self.journal_wsfe, move_type="out_refund")
        note.write({"l10n_ar_fiscal_period_from": self.today, "l10n_ar_fiscal_period_to": self.today})
        self._number_it(note)

        with self.subTest("una nota sin comprobante asociado informa el período"):
            voucher = self._build_cae_request(note)["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
            self.assertEqual(voucher["PeriodoAsoc"]["FchDesde"], self.today.strftime("%Y%m%d"))

        with self.subTest("si apunta a un comprobante, el período no viaja"):
            note.reversed_entry_id = self._number_it(self._new_invoice(self.journal_wsfe), number=41)
            voucher = self._build_cae_request(note)["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
            self.assertNotIn("PeriodoAsoc", voucher)
