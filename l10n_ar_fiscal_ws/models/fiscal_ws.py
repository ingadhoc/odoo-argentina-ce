##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import ormcache

from .exceptions import serialize_answer

_logger = logging.getLogger(__name__)


class L10nArFiscalWs(models.Model):
    _name = "l10n_ar.fiscal.ws"
    _description = "Argentinian Fiscal Web Service"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Service name as the tax authority names it, e.g. wsfe.")
    production_url = fields.Char(required=True)
    homologation_url = fields.Char(required=True)
    connection_ids = fields.One2many("l10n_ar.fiscal.ws.connection", "fiscal_ws_id")
    mapping_ids = fields.One2many("l10n_ar.fiscal.ws.mapping", "fiscal_ws_id")
    has_dummy = fields.Boolean(compute="_compute_has_dummy")
    active = fields.Boolean(default=True)

    _unique_code = models.Constraint("unique (code)", "The web service code must be unique")

    def _compute_has_dummy(self):
        for rec in self:
            rec.has_dummy = bool(rec.mapping_ids.filtered(lambda m: m.code == "dummy"))

    def action_check_service(self):
        """Ask the service whether it is up. Needs no certificate."""
        self.ensure_one()
        mapping = self.mapping_ids.filtered(lambda m: m.code == "dummy")[:1]
        if not mapping:
            raise UserError(_("El servicio %s no tiene definido el método de prueba.", self.name))
        answer, _xml = mapping.call(self)
        return {
            "type": "ir.actions.client",
            "tag": "l10n_ar_fiscal_ws.service_answer",
            "params": {
                "title": _("%s: estado del servicio", self.name),
                "message": serialize_answer(answer),
            },
        }

    @api.model
    @ormcache("code", "environment_type", cache="stable")
    def _get_url(self, code, environment_type):
        """URL of a service for the given environment, cached by (code, environment)."""
        service = self.search([("code", "=", code)], limit=1)
        if not service:
            raise ValidationError(_("There is no fiscal web service with code '%s'.") % code)
        if environment_type == "production":
            return service.production_url
        return service.homologation_url
