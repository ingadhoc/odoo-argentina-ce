##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import logging
import os
from datetime import timedelta
from xml.etree import ElementTree

import dateutil.parser
import pytz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from .fiscal_ws_connection import build_client, call_service

_logger = logging.getLogger(__name__)

ARCA_TZ = pytz.timezone("America/Argentina/Buenos_Aires")
TICKET_HOURS = 12


def _to_arca_time(value):
    return value.astimezone(ARCA_TZ).replace(tzinfo=None)


def _to_utc(value):
    return value.astimezone(ARCA_TZ).astimezone(pytz.utc).replace(tzinfo=None)


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ar_fiscal_alias_ids = fields.One2many(
        "l10n_ar.fiscal.certificate.alias",
        "company_id",
        bypass_search_access=True,
    )
    l10n_ar_fiscal_connection_ids = fields.One2many(
        "l10n_ar.fiscal.ws.connection",
        "company_id",
        bypass_search_access=True,
    )
    l10n_ar_fce_transmission_type = fields.Selection(
        [
            ("SCA", "SCA - Transferencia al sistema de circulación abierta"),
            ("ADC", "ADC - Agente de depósito colectivo"),
        ],
        "FCE: opción de transmisión",
        help="Requerido al informar comprobantes del tipo FCE MiPyME",
    )
    l10n_ar_fiscal_payment_foreign_currency = fields.Selection(
        [("S", "Yes"), ("N", "No"), ("account", "Account's Currency Dependant")],
        string="Default Policy for Payment in Foreign Currency",
        default="account",
    )

    @api.model
    def _get_environment_type(self):
        """Homologation or production.

        The system parameter wins; without it, a server_mode other than
        production means homologation.
        """
        parameter = self.env["ir.config_parameter"].sudo().get_param("l10n_ar_fiscal_ws.env_type")
        if parameter in ("production", "homologation"):
            return parameter
        server_mode = config.get("server_mode")
        return "production" if not server_mode or server_mode == "production" else "homologation"

    def _get_key_and_certificate(self, environment_type):
        """Confirmed certificate of the company, or the pair set in the odoo conf file."""
        self.ensure_one()
        certificate = self.env["l10n_ar.fiscal.certificate"].search(
            [
                ("alias_id.company_id", "=", self.id),
                ("alias_id.type", "=", environment_type),
                ("state", "=", "confirmed"),
            ]
        )
        if len(certificate) > 1:
            raise UserError(
                _(
                    'Hay más de un certificado de "%s" confirmado. Dejá confirmado uno solo.',
                    environment_type,
                )
            )
        if certificate:
            _logger.info("Using the certificate stored in the database")
            return certificate.alias_id.key, certificate.crt

        prefix = "l10n_ar_fiscal_prod" if environment_type == "production" else "l10n_ar_fiscal_homo"
        pkey_path = config.get("%s_pkey_file" % prefix)
        cert_path = config.get("%s_cert_file" % prefix)
        if pkey_path and cert_path and os.path.isfile(pkey_path) and os.path.isfile(cert_path):
            with open(pkey_path) as pkey_file, open(cert_path) as cert_file:
                _logger.info("Using the certificate set in the odoo conf file")
                return pkey_file.read(), cert_file.read()

        raise UserError(
            _(
                'No hay certificado de "%(environment)s" confirmado en la compañía %(company)s.',
                environment=environment_type,
                company=self.name,
            )
        )

    def _get_fiscal_ws_connection(self, code):
        """Valid access ticket for a service, asking for a new one when needed."""
        self.ensure_one()
        environment_type = self._get_environment_type()
        now = fields.Datetime.now()
        connection = self.l10n_ar_fiscal_connection_ids.search(
            [
                ("company_id", "=", self.id),
                ("fiscal_ws_id.code", "=", code),
                ("type", "=", environment_type),
                ("generation_time", "<=", now),
                ("expiration_time", ">", now),
            ],
            limit=1,
        )
        return connection or self._create_fiscal_ws_connection(code, environment_type)

    def _create_fiscal_ws_connection(self, code, environment_type):
        self.ensure_one()
        _logger.info("Asking for a new %s ticket (%s) for %s", code, environment_type, self.name)
        pkey, cert = self._get_key_and_certificate(environment_type)
        signed_request, unique_id = self._sign_login_ticket_request(code, pkey, cert)

        login_url = self.env["l10n_ar.fiscal.ws"]._get_url("LoginCms", environment_type)
        client, transport = build_client(self.env, login_url)
        # through call_service so a refusal of the authority —an expired certificate,
        # a ticket still valid— reaches the user as its own message, not as a zeep fault
        response, _xml = call_service(client, transport, "loginCms", {"in0": signed_request})
        values = self._parse_login_ticket_response(response)
        values.update(
            {
                "unique_id": unique_id,
                "company_id": self.id,
                "type": environment_type,
                "fiscal_ws_id": self.env["l10n_ar.fiscal.ws"].search([("code", "=", code)], limit=1).id,
            }
        )
        # El ticket se guarda en su propia transacción. La autoridad no entrega otro
        # hasta que este vence, así que si el posteo de la factura termina en rollback
        # —un rechazo— el ticket tiene que sobrevivir igual; y con un cursor propio ese
        # rollback sigue deshaciendo el asiento, que es lo que _post da por sentado.
        with self.env.registry.cursor() as ticket_cr:
            ticket_id = self.env(cr=ticket_cr)["l10n_ar.fiscal.ws.connection"].create(values).id
        return self.env["l10n_ar.fiscal.ws.connection"].browse(ticket_id)

    def _sign_login_ticket_request(self, code, pkey, cert):
        """Build the login ticket request and sign it in PKCS7, as WSAA expects."""
        self.ensure_one()
        now = _to_arca_time(fields.Datetime.now())
        unique_id = str(int(now.timestamp()))
        request = str(
            self.env["ir.ui.view"]._render_template(
                "l10n_ar_fiscal_ws.login_ticket_request",
                {
                    "unique_id": unique_id,
                    "generation_time": now,
                    "expiration_time": now + timedelta(hours=TICKET_HOURS),
                    "service": code,
                },
            )
        ).strip()
        signed = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(request.encode("utf-8"))
            .add_signer(
                x509.load_pem_x509_certificate(cert.encode("utf-8")),
                serialization.load_pem_private_key(pkey.encode("utf-8"), password=None),
                hashes.SHA256(),
            )
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.NoCapabilities])
        )
        return base64.b64encode(signed).decode("utf-8"), unique_id

    def _parse_login_ticket_response(self, response):
        tree = ElementTree.ElementTree(ElementTree.fromstring(response))
        return {
            "token": tree.find(".//token").text,
            "sign": tree.find(".//sign").text,
            "generation_time": _to_utc(dateutil.parser.isoparse(tree.find(".//generationTime").text)),
            "expiration_time": _to_utc(dateutil.parser.isoparse(tree.find(".//expirationTime").text)),
        }
