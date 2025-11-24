##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import logging
import os
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

import dateutil.parser
import odoo.tools as tools
import pytz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from zeep import Client

_logger = logging.getLogger(__name__)

ARCA_TZ = pytz.timezone("America/Argentina/Buenos_Aires")


def unlocate_datetime(dt: datetime) -> datetime:
    return dt.astimezone(ARCA_TZ).replace(tzinfo=None)


def relocate_datetime(dt: datetime) -> datetime:
    return dt.astimezone(ARCA_TZ).astimezone(pytz.timezone("UTC")).replace(tzinfo=None)


class ResCompany(models.Model):
    _inherit = "res.company"

    alias_ids = fields.One2many(
        "arcaws.certificate_alias",
        "company_id",
        bypass_search_access=True,
    )
    connection_ids = fields.One2many(
        "arcaws.connection",
        "company_id",
        bypass_search_access=True,
    )

    @api.model
    def _get_environment_type(self):
        """
        Function to define homologation/production environment
        First it search for a paramter "arcaws.env.type" if exists and:
        * is production --> production
        * is homologation --> homologation
        Else
        Search for 'server_mode' parameter on conf file. If that parameter is:
        * 'test' or 'develop' -->  homologation
        * other or no parameter -->  production
        """
        parameter_env_type = self.env["ir.config_parameter"].sudo().get_param("arcaws.env.type")
        if parameter_env_type == "production":
            environment_type = "production"
        elif parameter_env_type == "homologation":
            environment_type = "homologation"
        else:
            server_mode = tools.config.get("server_mode")
            if not server_mode or server_mode == "production":
                environment_type = "production"
            else:
                environment_type = "homologation"
        _logger.info("Running arg electronic invoice on %s mode" % environment_type)
        return environment_type

    def get_key_and_certificate(self, environment_type):
        """
        Funcion que busca para el environment_type definido,
        una clave y un certificado en los siguientes lugares y segun estas
        prioridades:
        * en el conf del server de odoo
        * en registros de esta misma clase
        """
        self.ensure_one()
        pkey = False
        cert = False
        msg = False
        certificate = self.env["arcaws.certificate"].search(
            [
                ("alias_id.company_id", "=", self.id),
                ("alias_id.type", "=", environment_type),
                ("state", "=", "confirmed"),
            ]
        )
        # to avoid confusion on the user, if more than one certificate found,
        # we ask to keep the one he whants to use
        if len(certificate) > 1:
            raise UserError(
                _(
                    'Tiene más de un certificado de "%s" confirmado. Por favor '
                    'deje un solo certificado de "%s" confirmado.'
                )
                % (environment_type, environment_type)
            )
        if certificate:
            pkey = certificate.alias_id.key
            cert = certificate.crt
            _logger.info("Using DB certificates")
        # not certificate on bd, we searpytzch on odo conf file
        else:
            msg = _("Not confirmed certificate for %s on company %s") % (
                environment_type,
                self.name,
            )
            pkey_path = False
            cert_path = False
            if environment_type == "production":
                pkey_path = tools.config.get("arca_prod_pkey_file")
                cert_path = tools.config.get("arca_prod_cert_file")
            else:
                pkey_path = tools.config.get("arca_homo_pkey_file")
                cert_path = tools.config.get("arca_homo_cert_file")
            if pkey_path and cert_path:
                try:
                    if os.path.isfile(pkey_path) and os.path.isfile(cert_path):
                        with open(pkey_path) as pkey_file:
                            pkey = pkey_file.read()
                        with open(cert_path) as cert_file:
                            cert = cert_file.read()
                    msg = "Could not find %s or %s files" % (pkey_path, cert_path)
                except Exception:
                    msg = "Could not read %s or %s files" % (pkey_path, cert_path)
                else:
                    _logger.info("Using odoo conf certificates")
        if not pkey or not cert:
            raise UserError(msg)
        cert = x509.load_pem_x509_certificate(cert.encode("utf-8"))
        pkey = serialization.load_pem_private_key(pkey.encode("utf-8"), password=None)
        return (pkey, cert)

    def arca_get_connection(self, arcaws):
        self.ensure_one()
        _logger.info("Getting connection for company %s and ws %s" % (self.name, arcaws))
        now = fields.Datetime.now()
        environment_type = self._get_environment_type()

        connection = self.connection_ids.search(
            [
                ("type", "=", environment_type),
                ("generationtime", "<=", now),
                ("expirationtime", ">", now),
                ("arcaws.code", "=", arcaws),
                ("company_id", "=", self.id),
            ],
            limit=1,
        )
        if not connection:
            connection = self._arca_create_connection(arcaws, environment_type)
        return connection

    def _arca_render_data(self, template_name, qcontext):
        return str(self.env["ir.ui.view"]._render_template(template_name, qcontext)).strip()

    def _arca_create_connection(self, arcaws, environment_type):
        self.ensure_one()
        _logger.info(
            "Creating connection for company %s, environment type %s and ws "
            "%s" % (self.name, environment_type, arcaws)
        )

        login_url = self.env["arcaws"].get_arca_url("LoginCms", environment_type)
        pkey, cert = self.get_key_and_certificate(environment_type)

        now = unlocate_datetime(fields.Datetime.now())
        uniqueid = str(int(now.timestamp()))
        generationtime = now
        expirationtime = now + timedelta(hours=12)
        arca_login_ticket_request = self._arca_render_data(
            "l10n_ar_fiscal_ws.arca_login_ticket_request",
            {
                "unique_id": uniqueid,
                "generation_time": generationtime,
                "expiration_time": expirationtime,
                "service": arcaws,
            },
        )
        signed_data = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(arca_login_ticket_request.encode("utf-8"))
            .add_signer(cert, pkey, hashes.SHA256())
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.NoCapabilities])
        )

        sign_tra = base64.b64encode(signed_data).decode("utf-8")

        client = Client(login_url)
        response = getattr(client.service, "loginCms")(sign_tra)
        _logger.info("Successful Connection to ARCA.")
        auth_data = self._arca_parse_login(response)
        auth_data.update(
            {
                "uniqueid": uniqueid,
                "type": environment_type,
                "arcaws": self.env["arcaws"].search([("code", "=", arcaws)], limit=1).id,
                "company_id": self.id,
            }
        )
        connection = self.env["arcaws.connection"].create(auth_data)
        self.env.cr.commit()  # pylint: disable=invalid-commit
        return connection

    def _arca_parse_login(self, response):
        tree = ET.ElementTree(ET.fromstring(response))
        generation: str = tree.find(".//generationTime").text
        expires: str = tree.find(".//expirationTime").text
        token: str = tree.find(".//token").text
        sign: str = tree.find(".//sign").text
        return {
            "token": token,
            "sign": sign,
            "generationtime": relocate_datetime(dateutil.parser.isoparse(generation)),
            "expirationtime": relocate_datetime(dateutil.parser.isoparse(expires)),
        }
