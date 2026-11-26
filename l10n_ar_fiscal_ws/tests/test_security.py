##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from unittest.mock import patch

from odoo import fields
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

RES_COMPANY = "odoo.addons.l10n_ar_fiscal_ws.models.res_company"


@tagged("post_install", "-at_install")
class TestFiscalWsSecurity(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alias = cls.env["l10n_ar.fiscal.certificate.alias"].create(
            {
                "company_id": cls.company_ri.id,
                "country_id": cls.env.ref("base.ar").id,
                "city": "Rosario",
                "company_cuit": cls.company_ri.vat,
                "type": "homologation",
            }
        )
        cls.alias.generate_key()
        cls.env["l10n_ar.fiscal.certificate"].create(
            {"alias_id": cls.alias.id, "crt": "certificate", "state": "confirmed"}
        )
        cls.invoicing_user = new_test_user(
            cls.env,
            login="fiscal_ws_invoicing",
            groups="account.group_account_invoice",
            company_id=cls.company_ri.id,
            company_ids=[cls.company_ri.id],
        )
        cls.company = cls.company_ri.with_user(cls.invoicing_user)

    def test_an_invoicing_user_cannot_read_the_private_key(self):
        with self.assertRaises(AccessError):
            self.alias.with_user(self.invoicing_user).read(["key"])

    def test_an_invoicing_user_uses_the_ticket_without_reading_it(self):
        key, _cert = self.company._get_key_and_certificate("homologation")
        self.assertEqual(key, self.alias.key)

        now = fields.Datetime.now()
        login_answer = {
            "token": "token",
            "sign": "sign",
            "generation_time": now,
            "expiration_time": fields.Datetime.add(now, hours=12),
        }
        # the ticket is saved through its own cursor, which has to see this test's data
        with (
            self.enter_registry_test_mode(),
            patch.object(type(self.company), "_sign_login_ticket_request", return_value=("signed", "1")),
            patch.object(type(self.company), "_parse_login_ticket_response", return_value=login_answer),
            patch(f"{RES_COMPANY}.build_client", return_value=(None, None)),
            patch(f"{RES_COMPANY}.call_service", return_value=("response", {})),
        ):
            connection = self.company._create_fiscal_ws_connection("wsfe", "homologation")
        self.assertEqual(connection._auth_payload("plain")["token"], "token")
        with self.assertRaises(AccessError):
            connection.read(["token", "sign"])

    def test_an_invoicing_user_cannot_create_or_change_tickets(self):
        connections = self.env["l10n_ar.fiscal.ws.connection"].with_user(self.invoicing_user)
        values = {
            "company_id": self.company_ri.id,
            "fiscal_ws_id": self.env["l10n_ar.fiscal.ws"].search([("code", "=", "wsfe")], limit=1).id,
            "type": "homologation",
        }
        with self.assertRaises(AccessError):
            connections.create(values)
        connection = connections.sudo().create(values)
        with self.assertRaises(AccessError):
            connection.with_user(self.invoicing_user).write({"token": "forged"})

    def test_a_user_does_not_see_the_tickets_of_another_company(self):
        connections = self.env["l10n_ar.fiscal.ws.connection"]
        fiscal_ws = self.env["l10n_ar.fiscal.ws"].search([("code", "=", "wsfe")], limit=1)
        own, other = connections.create(
            [
                {"company_id": company.id, "fiscal_ws_id": fiscal_ws.id, "type": "homologation"}
                for company in (self.company_ri, self.company_mono)
            ]
        )
        visible = connections.with_user(self.invoicing_user).search([("id", "in", (own | other).ids)])
        self.assertEqual(visible, own)
