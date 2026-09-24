##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Properties that hold after any operation of this module.

Every test calls these on top of what its own scenario asserts: the specific
assert says the value is right, these say nothing broke around it.
"""

# How each service names the amounts of the voucher it is asked to authorize
AMOUNT_FIELDS = {
    "wsfe": {
        "total": "ImpTotal",
        "parts": ["ImpNeto", "ImpIVA", "ImpTotConc", "ImpOpEx", "ImpTrib"],
    },
    "wsbfe": {
        "total": "Imp_total",
        "parts": [
            "Imp_neto",
            "Impto_liq",
            "Impto_liq_rni",
            "Imp_tot_conc",
            "Imp_op_ex",
            "Imp_perc",
            "Imp_iibb",
            "Imp_perc_mun",
            "Imp_internos",
        ],
    },
}


class FiscalWsInvariants:
    def assert_invoice_is_sound(self, invoice):
        """Run every invariant that applies to an invoice, whatever was done to it."""
        self.assert_authorization_is_complete(invoice)

    def assert_authorization_is_complete(self, invoice):
        """An authorization is the mode and the code together: one without the other
        leaves the invoice unusable, and the form asks for a code it does not have."""
        self.assertEqual(
            bool(invoice.l10n_ar_fiscal_auth_mode),
            bool(invoice.l10n_ar_fiscal_auth_code),
            "La factura %s quedó con modo de autorización '%s' y código '%s'"
            % (invoice.name, invoice.l10n_ar_fiscal_auth_mode, invoice.l10n_ar_fiscal_auth_code),
        )

    def assert_number_matches_authorization(self, invoice, authorized_number):
        """The authority authorizes one number: the invoice has to carry that one and
        no other, or the numbering of the point of sale silently drifts."""
        parts = invoice._l10n_ar_get_document_number_parts(
            invoice.l10n_latam_document_number, invoice.l10n_latam_document_type_id.code
        )
        self.assertEqual(
            parts["invoice_number"],
            int(authorized_number),
            "La factura %s lleva el número %s y ARCA autorizó el %s"
            % (invoice.name, parts["invoice_number"], authorized_number),
        )

    def assert_payload_amounts_add_up(self, ws_code, voucher):
        """The authority rejects a voucher whose total is not the sum of its parts."""
        fields = AMOUNT_FIELDS[ws_code]
        parts = sum(float(voucher.get(name) or 0) for name in fields["parts"])
        self.assertAlmostEqual(
            float(voucher[fields["total"]]),
            parts,
            places=2,
            msg="El total informado a %s no es la suma de sus partes" % ws_code,
        )

    def assert_items_add_up_to_total(self, voucher, item_total_field):
        """On the services that send the lines, the lines have to explain the total."""
        items = voucher["Items"]["Item"]
        added = sum(float(item[item_total_field] or 0) for item in items)
        self.assertAlmostEqual(
            float(voucher["Imp_total"]),
            added,
            places=2,
            msg="Los ítems no suman el total del comprobante",
        )
