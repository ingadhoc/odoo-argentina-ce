##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from odoo.tests import tagged

from .common import TestFiscalWsCommon, answer


def vat_item(code, base, amount):
    return answer(Id=code, BaseImp=base, Importe=amount)


def voucher(number, total, document_number, vat=(("5", 100.0, 21.0),), not_taxed=0.0, exempt=0.0, tributes=0.0):
    """Lo que el servicio contesta cuando tiene el comprobante."""
    return answer(
        ResultGet=answer(
            CbteDesde=number,
            CbteHasta=number,
            CbteTipo=1,
            CbteFch="20260115",
            Concepto=1,
            Resultado="A",
            EmisionTipo="CAE",
            CodAutorizacion="6123456789012%s" % (number % 10),
            FchVto="20301231",
            DocTipo="80",
            DocNro=document_number,
            ImpTotal=total,
            ImpNeto=sum(item[1] for item in vat),
            ImpTotConc=not_taxed,
            ImpOpEx=exempt,
            ImpTrib=tributes,
            ImpIVA=sum(item[2] for item in vat),
            MonId="PES",
            MonCotiz=1.0,
            Iva=answer(AlicIva=[vat_item(*item) for item in vat]) if vat else None,
        ),
        Errors=None,
    )


def not_registered():
    """Lo que el servicio contesta por un número que nunca autorizó."""
    return answer(
        ResultGet=None,
        Errors=answer(Err=[answer(Code=602, Msg="No existen datos en nuestros registros")]),
    )


@tagged("post_install", "-at_install")
class TestRecover(TestFiscalWsCommon):
    """Recuperar los comprobantes que el organismo autorizó y Odoo no llegó a registrar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account_recover = cls.company_data["default_account_revenue"]
        cls.vat_cuit = cls.res_partner_adhoc.vat

    def _service_answers(self, by_number):
        """Contesta la consulta de cada número con su fixture, sin llegar a la red."""

        def _call(journal, code, extra=None):
            if code == "invoice_query":
                return by_number.get(extra["number"], not_registered())
            if code == "last_invoice":
                return self._last_invoice_answer("wsfe", max(by_number, default=0))
            raise AssertionError("El test no previó la llamada al servicio '%s'" % code)

        return patch.object(type(self.env["account.journal"]), "_l10n_ar_call", _call)

    @contextmanager
    def _neutralized_cursor(self):
        """El posteo del comprobante que neutraliza commitea, y el cursor de test lo prohíbe."""
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.env.cr, "commit", self.env.flush_all))
            yield

    def _document_type(self, invoice):
        return invoice.l10n_latam_document_type_id

    def _new_wizard(self, document_type, number_from, number_to):
        return self.env["l10n_ar.fiscal.ws.recover"].create(
            {
                "journal_id": self.journal_wsfe.id,
                "document_type_id": document_type.id,
                "number_from": number_from,
                "number_to": number_to,
                "account_id": self.account_recover.id,
            }
        )

    def _fetch(self, document_type, by_number, number_from=42, number_to=42):
        wizard = self._new_wizard(document_type, number_from, number_to)
        with self._service_answers(by_number):
            wizard.action_fetch()
        return wizard

    # ------------------------------------------------------------------ mapeo

    def test_the_query_asks_the_service_for_one_voucher_of_this_journal(self):
        """La consulta lleva el punto de venta del diario y el número que se busca."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping("wsfe", "invoice_query")

        payload = mapping.build(self.journal_wsfe, {"document_type_code": document_type.code, "number": 42})

        self.assertEqual(
            payload["FeCompConsReq"],
            {
                "PtoVta": int(self.journal_wsfe.l10n_ar_afip_pos_number),
                "CbteTipo": int(document_type.code),
                "CbteNro": 42,
            },
        )

    def test_the_answer_is_read_into_the_authorization_and_the_amounts(self):
        """De la respuesta salen la autorización, el cliente y el desglose de IVA."""
        response = voucher(42, 121.0, self.vat_cuit, vat=(("5", 100.0, 21.0),))

        values = self.journal_wsfe._l10n_ar_build_response("invoice_query_response", response)

        self.assertEqual(values["auth_code"], "61234567890122")
        self.assertEqual(values["auth_mode"], "CAE")
        self.assertEqual(str(values["auth_code_due"]), "2030-12-31")
        self.assertEqual(str(values["date"]), "2026-01-15")
        self.assertEqual(values["document_number"], self.vat_cuit)
        self.assertEqual(float(values["total"]), 121.0)
        self.assertEqual([item.Id for item in values["vat_items"]], ["5"])

    def test_the_wizard_offers_the_document_types_of_the_journal(self):
        """Los tipos que se pueden elegir son los que este diario emite, y no más."""
        invoice = self._new_invoice(self.journal_wsfe)
        wizard = self._new_wizard(self._document_type(invoice), 1, 1)

        offered = wizard.available_document_type_ids
        self.assertIn(self._document_type(invoice), offered)
        self.assertTrue(offered, "El diario electrónico tiene tipos de comprobante")
        self.assertEqual(
            offered.filtered(lambda d: d.internal_type not in ("invoice", "debit_note", "credit_note")),
            self.env["l10n_latam.document.type"],
        )
        self.assertEqual(offered.filtered(lambda d: d.country_id.code != "AR"), offered.browse())

    def test_a_number_the_service_does_not_have_is_not_listed(self):
        """Un número que el organismo nunca autorizó no es un comprobante a recuperar."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))

        wizard = self._fetch(document_type, {42: voucher(42, 121.0, self.vat_cuit)}, 42, 44)

        self.assertEqual(wizard.line_ids.mapped("number"), [42])

    # --------------------------------------------------------------- propuesta

    def test_a_draft_with_the_same_customer_and_total_is_proposed_to_assign(self):
        """Si el borrador coincide en cliente y en total, es el comprobante que se perdió."""
        invoice = self._new_invoice(self.journal_wsfe)
        document_type = self._document_type(invoice)

        wizard = self._fetch(document_type, {42: voucher(42, invoice.amount_total, self.vat_cuit)})

        line = wizard.line_ids
        self.assertEqual(line.action, "match")
        self.assertEqual(line.move_id, invoice)
        self.assertEqual(line.partner_id, self.res_partner_adhoc)

    def test_a_draft_with_another_total_is_not_the_one(self):
        """Mismo cliente y otro importe no alcanza: se propone crearlo."""
        invoice = self._new_invoice(self.journal_wsfe)
        document_type = self._document_type(invoice)

        wizard = self._fetch(document_type, {42: voucher(42, invoice.amount_total + 1, self.vat_cuit)})

        self.assertEqual(wizard.line_ids.action, "create")
        self.assertFalse(wizard.line_ids.move_id)

    def test_an_anonymous_final_consumer_goes_to_the_contact_of_the_localization(self):
        """Sin identificación utilizable no hay a quién buscar: va al consumidor final."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))

        wizard = self._fetch(document_type, {42: voucher(42, 121.0, "0")})

        self.assertEqual(wizard.line_ids.partner_id, self.env.ref("l10n_ar.par_cfa"))
        self.assertEqual(wizard.line_ids.action, "create")

    def test_a_voucher_with_other_tributes_is_not_created(self):
        """Las percepciones no se pueden reconstruir solas: queda para resolver a mano."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))

        wizard = self._fetch(document_type, {42: voucher(42, 221.0, self.vat_cuit, tributes=100.0)})

        self.assertEqual(wizard.line_ids.action, "skip")
        self.assertIn("tributos", wizard.line_ids.note)

    def test_a_voucher_already_in_odoo_is_left_alone(self):
        """Lo que ya está registrado no se vuelve a recuperar."""
        invoice = self._number_it(self._new_invoice(self.journal_wsfe), number=42)
        document_type = self._document_type(invoice)

        wizard = self._fetch(document_type, {42: voucher(42, invoice.amount_total, self.vat_cuit)})

        self.assertEqual(wizard.line_ids.action, "skip")
        self.assertIn(invoice.name, wizard.line_ids.note)

    # ---------------------------------------------------------------- aplicar

    def test_assigning_posts_the_draft_with_the_number_and_the_authorization(self):
        """Asignar le pone al borrador el número y el CAE que ya tiene el organismo.

        Y no le pide nada al servicio: el módulo solo autoriza lo que no tiene CAE.
        """
        invoice = self._new_invoice(self.journal_wsfe)
        document_type = self._document_type(invoice)
        wizard = self._fetch(document_type, {42: voucher(42, invoice.amount_total, self.vat_cuit)})

        with self._service_answers({}):
            wizard.action_apply()

        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.l10n_ar_fiscal_auth_code, "61234567890122")
        self.assertEqual(invoice.l10n_ar_fiscal_auth_mode, "CAE")
        self.assertEqual(
            invoice.l10n_latam_document_number,
            "%05d-00000042" % int(self.journal_wsfe.l10n_ar_afip_pos_number),
        )

    def test_creating_builds_one_line_per_aliquot(self):
        """El comprobante creado reproduce el desglose que informó el organismo."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))
        answers = {42: voucher(42, 1226.0, self.vat_cuit, vat=(("5", 100.0, 21.0), ("4", 1000.0, 105.0)))}
        wizard = self._fetch(document_type, answers)

        with self._service_answers({}):
            wizard.action_apply()

        created = self.env["account.move"].search(
            [("journal_id", "=", self.journal_wsfe.id), ("l10n_ar_fiscal_auth_code", "=", "61234567890122")]
        )
        self.assertEqual(created.state, "posted")
        self.assertEqual(created.amount_total, 1226.0)
        self.assertEqual(sorted(created.invoice_line_ids.mapped("price_unit")), [100.0, 1000.0])
        self.assertEqual(
            sorted(created.invoice_line_ids.tax_ids.tax_group_id.mapped("l10n_ar_vat_afip_code")),
            ["4", "5"],
        )
        self.assertEqual(created.invoice_line_ids.account_id, self.account_recover)

    def test_a_recovered_invoice_is_neutralized_with_a_credit_note(self):
        """Tildar neutralizar sobre una factura emite la nota de crédito que la deja en cero."""
        document_type = self._document_type(self._new_invoice(self.journal_wsfe))
        wizard = self._fetch(document_type, {42: voucher(42, 121.0, self.vat_cuit)})
        wizard.line_ids.reverse = True

        with self._service_answers({}), self._neutralized_cursor(), self._cae_answers(
            answer(
                FeDetResp=answer(
                    FECAEDetResponse=[
                        answer(CAE="61111111111111", CAEFchVto="20301231", Resultado="A", Observaciones=answer(Obs=[]))
                    ]
                ),
                Errors=answer(Err=[]),
            )
        ):
            wizard.action_apply()

        created = self.env["account.move"].search([("l10n_ar_fiscal_auth_code", "=", "61234567890122")])
        reverse = self.env["account.move"].search([("reversed_entry_id", "=", created.id)])
        self.assertEqual(reverse.move_type, "out_refund")
        self.assertEqual(reverse.l10n_latam_document_type_id.internal_type, "credit_note")
        self.assertEqual(reverse.state, "posted")

    def test_a_recovered_credit_note_is_neutralized_with_a_debit_note(self):
        """Sobre una nota de crédito el que la deja en cero es una nota de débito."""
        refund = self._new_invoice(self.journal_wsfe, move_type="out_refund")
        document_type = self._document_type(refund)
        self.assertEqual(document_type.internal_type, "credit_note", "El escenario necesita una nota de crédito")
        wizard = self._fetch(document_type, {42: voucher(42, refund.amount_total, self.vat_cuit)})
        wizard.line_ids.write({"action": "create", "move_id": False, "reverse": True})

        with self._service_answers({}), self._neutralized_cursor(), self._cae_answers(
            answer(
                FeDetResp=answer(
                    FECAEDetResponse=[
                        answer(CAE="61111111111111", CAEFchVto="20301231", Resultado="A", Observaciones=answer(Obs=[]))
                    ]
                ),
                Errors=answer(Err=[]),
            )
        ):
            wizard.action_apply()

        created = self.env["account.move"].search([("l10n_ar_fiscal_auth_code", "=", "61234567890122")])
        reverse = self.env["account.move"].search([("debit_origin_id", "=", created.id)])
        self.assertEqual(reverse.move_type, "out_invoice")
        self.assertEqual(reverse.l10n_latam_document_type_id.internal_type, "debit_note")
        self.assertEqual(reverse.state, "posted")
