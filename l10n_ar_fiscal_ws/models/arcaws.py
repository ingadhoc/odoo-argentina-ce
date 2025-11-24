##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import ormcache

_logger = logging.getLogger(__name__)


class ArcaWs(models.Model):
    _name = "arcaws"
    _description = "Arca webservice URLs"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    production_url = fields.Char(required=True)
    homologation_url = fields.Char(required=True)
    view_id = fields.Many2one("ir.ui.view")
    dummy_method = fields.Char(default="dummy")
    active = fields.Boolean(default=True)

    _arcaws_unique_code = models.Constraint(
        "unique (code)",
        "A WS code must be unique",
    )

    @api.model
    @ormcache("code", "env_type", cache="stable")
    def get_arca_url(self, code, env_type):
        """Get ARCA URL for a given service code and environment type
        (production or homologation)
        """
        url_record = self.search([("code", "=", code)], limit=1)
        if not url_record:
            raise ValidationError(_("No ARCA URL found for service '%s'.") % code)
        if env_type == "production":
            return url_record.production_url
        else:
            return url_record.homologation_url

    def action_dummie(self):
        self.ensure_one()
        _logger.info("Dummie action called")
        company = self.env.company
        connection = company.arca_get_connection(self.code)
        raise UserError(f"Dummie action called for connection {connection.call_arca_service(self.dummy_method, {})}")
