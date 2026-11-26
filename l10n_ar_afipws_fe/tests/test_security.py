##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo.addons.l10n_ar.tests.common import TestArCommon
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAfipwsFeSecurity(TestArCommon):
    def test_an_invoicing_user_cannot_read_the_sent_request(self):
        """The request sent to the tax authority carries the token and the sign."""
        user = new_test_user(
            self.env,
            login="afipws_fe_invoicing",
            groups="account.group_account_invoice",
            company_id=self.company_ri.id,
        )
        move = self.env["account.move"].create({"move_type": "entry"})
        with self.assertRaises(AccessError):
            move.with_user(user).read(["afip_xml_request"])
