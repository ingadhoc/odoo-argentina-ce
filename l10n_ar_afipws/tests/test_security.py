##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAfipwsSecurity(TestArCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alias = cls.env["afipws.certificate_alias"].create(
            {
                "company_id": cls.company_ri.id,
                "country_id": cls.env.ref("base.ar").id,
                "city": "Rosario",
                "company_cuit": cls.company_ri.vat,
                "type": "homologation",
            }
        )
        cls.alias.generate_key()
        cls.env["afipws.certificate"].create({"alias_id": cls.alias.id, "crt": "certificate", "state": "confirmed"})
        cls.invoicing_user = new_test_user(
            cls.env,
            login="afipws_invoicing",
            groups="account.group_account_invoice",
            company_id=cls.company_ri.id,
            company_ids=[cls.company_ri.id],
        )
        cls.company = cls.company_ri.with_user(cls.invoicing_user)

    def _ticket_values(self, company):
        return {"company_id": company.id, "type": "homologation", "afip_ws": "ws_sr_padron_a5"}

    def test_an_invoicing_user_cannot_read_the_private_key(self):
        with self.assertRaises(AccessError):
            self.alias.with_user(self.invoicing_user).read(["key"])

    def test_the_key_and_the_connection_cannot_be_called_through_rpc(self):
        with self.assertRaises(AccessError):
            get_public_method(self.company, "get_key_and_certificate")
        with self.assertRaises(AccessError):
            get_public_method(self.env["afipws.connection"], "connect")

    def test_an_invoicing_user_uses_the_ticket_without_reading_it(self):
        key, _cert = self.company.get_key_and_certificate("homologation")
        self.assertEqual(key, self.alias.key)

        now = datetime.now(timezone.utc)
        login_answer = {
            "uniqueid": "1",
            "generationtime": now.isoformat(),
            "expirationtime": (now + timedelta(hours=12)).isoformat(),
            "token": "token",
            "sign": "sign",
        }
        with patch.object(type(self.company), "authenticate", return_value=login_answer):
            connection = self.company._create_connection("ws_sr_padron_a5", "homologation")
        with self.assertRaises(AccessError):
            connection.read(["token", "sign"])

        service = SimpleNamespace(Conectar=lambda *args: None)
        with patch.object(type(connection), "_get_ws", return_value=service):
            ws = connection.connect()
        self.assertEqual((ws.Token, ws.Sign), ("token", "sign"))

    def test_an_invoicing_user_cannot_create_or_change_tickets(self):
        connections = self.env["afipws.connection"].with_user(self.invoicing_user)
        with self.assertRaises(AccessError):
            connections.create(self._ticket_values(self.company_ri))
        connection = connections.sudo().create(self._ticket_values(self.company_ri))
        with self.assertRaises(AccessError):
            connection.with_user(self.invoicing_user).write({"token": "forged"})

    def test_a_portal_user_cannot_read_tickets(self):
        portal_user = new_test_user(self.env, login="afipws_portal", groups="base.group_portal")
        self.env["afipws.connection"].create(self._ticket_values(self.company_ri))
        with self.assertRaises(AccessError):
            self.env["afipws.connection"].with_user(portal_user).search([])

    def test_a_user_does_not_see_the_tickets_of_another_company(self):
        connections = self.env["afipws.connection"]
        own, other = connections.create(
            [self._ticket_values(company) for company in (self.company_ri, self.company_mono)]
        )
        visible = connections.with_user(self.invoicing_user).search([("id", "in", (own | other).ids)])
        self.assertEqual(visible, own)
