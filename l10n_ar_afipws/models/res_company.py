##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
import logging
from odoo.exceptions import UserError
import dateutil.parser
import pytz
import odoo.tools as tools
import os

from .afipws_zeep import login_cms_zeep, normalize_env

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):

    _inherit = "res.company"

    alias_ids = fields.One2many(
        "afipws.certificate_alias",
        "company_id",
        "Aliases",
        auto_join=True,
    )
    connection_ids = fields.One2many(
        "afipws.connection",
        "company_id",
        "Connections",
        auto_join=True,
    )

    @api.model
    def _get_environment_type(self):
        """
        Function to define homologation/production environment
        First it search for a paramter "afip.ws.env.type" if exists and:
        * is production --> production
        * is homologation --> homologation
        Else
        Search for 'server_mode' parameter on conf file. If that parameter is:
        * 'test' or 'develop' -->  homologation
        * other or no parameter -->  production
        """
        parameter_env_type = (
            self.env["ir.config_parameter"].sudo().get_param("afip.ws.env.type")
        )
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
        certificate = self.env["afipws.certificate"].search(
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
        # not certificate on bd, we search on odo conf file
        else:
            msg = _("Not confirmed certificate for %s on company %s") % (
                environment_type,
                self.name,
            )
            pkey_path = False
            cert_path = False
            if environment_type == "production":
                pkey_path = tools.config.get("afip_prod_pkey_file")
                cert_path = tools.config.get("afip_prod_cert_file")
            else:
                pkey_path = tools.config.get("afip_homo_pkey_file")
                cert_path = tools.config.get("afip_homo_cert_file")
            if pkey_path and cert_path:
                try:
                    if os.path.isfile(pkey_path) and os.path.isfile(cert_path):
                        with open(pkey_path, "r") as pkey_file:
                            pkey = pkey_file.read()
                        with open(cert_path, "r") as cert_file:
                            cert = cert_file.read()
                    msg = "Could not find %s or %s files" % (pkey_path, cert_path)
                except Exception:
                    msg = "Could not read %s or %s files" % (pkey_path, cert_path)
                else:
                    _logger.info("Using odoo conf certificates")
        if not pkey or not cert:
            raise UserError(msg)
        return (pkey, cert)

    def get_connection(self, afip_ws):
        self.ensure_one()
        _logger.info(
            "Getting connection for company %s and ws %s" % (self.name, afip_ws)
        )
        now = fields.Datetime.now()
        environment_type = self._get_environment_type()

        # Margen de seguridad trixocom: renovar si al TA le quedan < 10 min
        from datetime import timedelta
        from .afipws_zeep import TA_RENEWAL_MARGIN_MINUTES

        connection = self.connection_ids.search(
            [
                ("type", "=", environment_type),
                ("generationtime", "<=", now),
                ("expirationtime", ">", now + timedelta(minutes=TA_RENEWAL_MARGIN_MINUTES)),
                ("afip_ws", "=", afip_ws),
                ("company_id", "=", self.id),
            ],
            limit=1,
        )
        if not connection:
            connection = self._create_connection(afip_ws, environment_type)
        return connection

    def _create_connection(self, afip_ws, environment_type):
        """
        This function should be called from get_connection. Not to be used
        directly. Migrado a zeep (sin cache en disco, reuso en DB 12h).
        """
        self.ensure_one()
        _logger.info(
            "Creating connection for company %s, environment type %s and ws "
            "%s" % (self.name, environment_type, afip_ws)
        )
        pkey, cert = self.get_key_and_certificate(environment_type)
        auth_data = self.authenticate(afip_ws, cert, pkey)
        auth_data.update(
            {
                "company_id": self.id,
                "afip_ws": afip_ws,
                "type": normalize_env(environment_type),
            }
        )

        auth_data["generationtime"] = (
            dateutil.parser.parse(str(auth_data["generationtime"]))
            .astimezone(pytz.utc)
            .replace(tzinfo=None)
            if isinstance(auth_data["generationtime"], str)
            else auth_data["generationtime"]
        )
        auth_data["expirationtime"] = (
            dateutil.parser.parse(str(auth_data["expirationtime"]))
            .astimezone(pytz.utc)
            .replace(tzinfo=None)
            if isinstance(auth_data["expirationtime"], str)
            else auth_data["expirationtime"]
        )

        _logger.info("Successful Connection to AFIP.")
        return self.connection_ids.create(auth_data)

    @api.model
    def authenticate(
        self,
        service,
        certificate,
        private_key,
        force=False,
        cache="",
        wsdl="",
        proxy="",
    ):
        """
        Login WSAA vía zeep (reemplaza pyafipws.wsaa.WSAA).
        Mantiene firma para compatibilidad; cache/wsdl/proxy se ignoran
        (el reuso es en DB via get_connection).
        """
        environment_type = self._get_environment_type()
        try:
            return login_cms_zeep(
                service, private_key, certificate, environment_type, ttl=60 * 60 * 12
            )
        except Exception as error:
            raise UserError(
                _("Could not connect. This is what we received: %s") % (error,)
            )
