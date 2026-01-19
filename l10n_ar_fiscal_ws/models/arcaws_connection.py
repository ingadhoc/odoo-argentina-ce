##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from lxml import etree
from odoo.exceptions import UserError
from zeep import Client
from zeep.plugins import HistoryPlugin

from odoo import api, fields, models

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

    def _arba_render_data(self, template_name, qcontext):
        return str(self.env["ir.ui.view"]._render_template(template_name, qcontext)).strip()

    def call_arca_service(self, method_name, data, **kwargs):
        self.ensure_one()
        history = HistoryPlugin()
        _logger.info(f"Calling ARCA service {method_name}")
        try:
            client = Client(self.arcaws_url, plugins=[history])
            response = getattr(client.service, method_name)(**data, **kwargs)
        except Exception as error:
            raise UserError(f"Error calling ARCA service {method_name}: {error}")
        if history.last_sent:
            envelope_req = history.last_sent["envelope"]
            response.xml_request = etree.tostring(envelope_req, pretty_print=True, encoding="unicode")
        if history.last_received:
            envelope_req = history.last_received["envelope"]
            response.xml_response = etree.tostring(envelope_req, pretty_print=True, encoding="unicode")

        return response

    @api.autovacuum
    def _gc_doc_index(self):
        """Garbage collect the expirated conection."""
        conection_ids = self.search(
            [("expirationtime", "<", fields.Datetime.now())],
        )
        if conection_ids:
            total_connection = len(conection_ids)
            conection_ids.unlink()
            _logger.info("GC'd %s expirated connections", total_connection)

    def _arca_post_xml(self, method_name, raw_xml, **kwargs):
        self.ensure_one()
        _logger.info(f"Calling ARCA service {method_name}")

        client = Client(self.arcaws_url)
        endpoint_url = client.service._binding_options["address"]
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{self.arcaws_url}/{method_name}",
        }

        response = client.transport.post_xml(address=endpoint_url, envelope=raw_xml, headers=headers)

        return response
