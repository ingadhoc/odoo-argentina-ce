##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from lxml import etree
from odoo import _, api, fields, models
from odoo.tools.zeep import Client, Transport
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from zeep.cache import InMemoryCache

from .exceptions import FiscalWsError

_logger = logging.getLogger(__name__)

# Some *.afip.gov.ar servers use a DH key too small for the default cipher list
ARCA_CIPHERS = "DEFAULT:!DH"

WSDL_CACHE_TTL_PARAM = "l10n_ar_fiscal_ws.wsdl_cache_ttl"
DEFAULT_WSDL_CACHE_TTL = 300


class FiscalHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = create_urllib3_context(ciphers=ARCA_CIPHERS)
        return super().init_poolmanager(*args, **kwargs)


class FiscalTransport(Transport):
    """Transport that keeps the sent and received envelopes of its own calls.

    One transport per client, so the trace belongs to this call only. zeep's
    HistoryPlugin is shared state and mixes up calls between workers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.mount("https://", FiscalHTTPAdapter())
        self.xml_request = False
        self.xml_response = False

    def post(self, address, message, headers):
        try:
            response = super().post(address, message, headers)
        finally:
            self.xml_request = self._pretty(message)
        self.xml_response = self._pretty(response.content)
        return response

    @staticmethod
    def _pretty(content):
        try:
            return etree.tostring(etree.fromstring(content), pretty_print=True).decode("utf-8")
        except Exception:
            return False


def build_client(env, url):
    """zeep client for a service url, with the wsdl cache and the trace of its calls."""
    ttl = int(env["ir.config_parameter"].sudo().get_param(WSDL_CACHE_TTL_PARAM, DEFAULT_WSDL_CACHE_TTL))
    cache = InMemoryCache(timeout=ttl) if ttl > 0 else None
    transport = FiscalTransport(cache=cache, operation_timeout=60, timeout=60)
    try:
        return Client(url, transport=transport), transport
    except Exception as error:
        raise FiscalWsError(_("No pudimos conectarnos con %(url)s: %(error)s", url=url, error=error)) from error


def call_service(client, transport, method_name, payload):
    """Call a method and return its answer along with the exchanged xml."""
    _logger.info("Calling %s", method_name)
    try:
        response = client.service[method_name](**payload)
    except Exception as error:
        raise FiscalWsError(error) from error
    finally:
        xml = {"xml_request": transport.xml_request, "xml_response": transport.xml_response}
    return response, xml


class L10nArFiscalWsConnection(models.Model):
    _name = "l10n_ar.fiscal.ws.connection"
    _description = "Fiscal Web Service Access Ticket"
    _rec_name = "fiscal_ws_id"
    _order = "expiration_time desc"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        bypass_search_access=True,
    )
    fiscal_ws_id = fields.Many2one("l10n_ar.fiscal.ws", required=True, index=True)
    type = fields.Selection(
        [("production", "Production"), ("homologation", "Homologation")],
        required=True,
    )
    unique_id = fields.Char(readonly=True)
    token = fields.Text(readonly=True)
    sign = fields.Text(readonly=True)
    generation_time = fields.Datetime(readonly=True)
    expiration_time = fields.Datetime(readonly=True)
    service_url = fields.Char(compute="_compute_service_url")

    @api.depends("type", "fiscal_ws_id")
    def _compute_service_url(self):
        for rec in self:
            rec.service_url = self.env["l10n_ar.fiscal.ws"]._get_url(rec.fiscal_ws_id.code, rec.type)

    def _get_client(self):
        self.ensure_one()
        return build_client(self.env, self.service_url)

    def auth_payload(self, style="block"):
        """Credentials, in the shape the called method expects them."""
        self.ensure_one()
        if style == "none":
            return {}
        vat = self.company_id.partner_id.ensure_vat()
        credentials = {"token": self.token, "sign": self.sign, "cuitRepresentada": vat}
        if style == "plain":
            return credentials
        if style == "request":
            return {"authRequest": credentials}
        return {"Auth": {"Token": self.token, "Sign": self.sign, "Cuit": vat}}

    def call(self, method_name, payload):
        """Call a method of this service with the credentials of this ticket."""
        self.ensure_one()
        client, transport = self._get_client()
        return call_service(client, transport, method_name, payload)

    @api.autovacuum
    def _gc_expired_connections(self):
        expired = self.search([("expiration_time", "<", fields.Datetime.now())])
        if expired:
            _logger.info("Removing %s expired fiscal web service tickets", len(expired))
            expired.unlink()
