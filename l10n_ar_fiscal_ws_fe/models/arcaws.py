##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import logging

from odoo import _, models

base64.encodestring = base64.encodebytes

_logger = logging.getLogger(__name__)


class Arcaws(models.Model):
    _inherit = "arcaws"

    def map_invoice_info(self, invoice):
        self.ensure_one()
        _logger.info("%s_map_invoice_info" % self.code)
        if hasattr(self.env["account.move"], "%s_map_invoice_info" % self.code):
            return getattr(invoice, "%s_map_invoice_info" % self.code)()
        else:
            return _("AFIP WS %s not implemented") % self.code
