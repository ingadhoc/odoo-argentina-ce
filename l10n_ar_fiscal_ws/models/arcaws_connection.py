##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from zeep import (
    Client,
)

_logger = logging.getLogger(__name__)


class ArcawsConnection(models.Model):
    _name = "arcaws.connection"
    _description = "ARCA WS Connection"
    _rec_name = "arcaws"
    _order = "expirationtime desc"

    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        index=True,
        bypass_search_access=True,
    )
    uniqueid = fields.Char(
        "Unique ID",
        readonly=True,
    )
    token = fields.Text(
        readonly=True,
    )
    sign = fields.Text(
        readonly=True,
    )
    generationtime = fields.Datetime("Generation Time", readonly=True)
    expirationtime = fields.Datetime("Expiration Time", readonly=True)
    arca_login_url = fields.Char(
        "ARCA Login URL",
        compute="_compute_arca_urls",
    )
    arcaws_url = fields.Char(
        "ARCA WS URL",
        compute="_compute_arca_urls",
    )
    type = fields.Selection(
        [("production", "Production"), ("homologation", "Homologation")],
        required=True,
    )
    arcaws = fields.Many2one(
        "arcaws",
        # required=True,
    )

    @api.depends("type", "arcaws")
    def _compute_arca_urls(self):
        for rec in self:
            rec.arca_login_url = self.env["arcaws"].get_arca_url("LoginCms", rec.type)
            rec.arcaws_url = self.env["arcaws"].get_arca_url(rec.arcaws.code, rec.type)
   
    def _arba_get_auth_dict(self, auth_strategy=False):
        self.ensure_one()
        if auth_strategy == "plain":
            return {
                "cuitRepresentada": self.company_id.partner_id.ensure_vat(),
                "sign": self.sign,
                "token": self.token,
            }
        elif auth_strategy == "auth_request":
            return {
                "authRequest": {
                    "cuitRepresentada": self.company_id.partner_id.ensure_vat(),
                    "sign": self.sign,
                    "token": self.token,
                }
            }
        elif auth_strategy == "auth":
            return {
                "Auth": {
                    "cuitRepresentada": self.company_id.partner_id.ensure_vat(),
                    "sign": self.sign,
                    "token": self.token,
                }
            }
        return {}

    def _arba_render_data(self, template_name, qcontext):
        return str(self.env["ir.ui.view"]._render_template(template_name, qcontext)).strip()

    def call_arca_service(self, method_name, data, **kwargs):
        self.ensure_one()
        _logger.info(f"Calling ARCA service {method_name}")
        if "auth" in kwargs:
            data.update(self._arba_get_auth_dict(kwargs["auth"]))
            del kwargs["auth"]
        try:
            client = Client(self.arcaws_url)
            response = getattr(client.service, method_name)(**data, **kwargs)
        except Exception as error:
            raise UserError(f"Error calling ARCA service {method_name}: {error}")

        return response

    @api.autovacuum
    def _gc_doc_index(self):
        """ Garbage collect the expirated conection. """
        conection_ids = expirationtime = self.search(
            [('expirationtime', '<', fields.Datetime.now())],
        )
        if conection_ids:
            total_connection = len(conection_ids)
            conection_ids.unlink()
            _logger.info("GC'd %s expirated connections", total_connection)

    # def call_arca_xml(self, method_name, xml, **kwargs):
    #     self.ensure_one()
    #     _logger.info(f"Calling ARCA service {method_name}")

    #     client = Client(self.arcaws_url)
    #     response = getattr(client.service, method_name)(xml)

    #     return response
