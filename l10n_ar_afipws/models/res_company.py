##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import hashlib
import logging
import os
import time

import dateutil.parser
import odoo.tools as tools
import pytz
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import wsaa_client

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
        parameter_env_type = self.env["ir.config_parameter"].sudo().get_param("afip.ws.env.type")
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
        return (pkey, cert)

    def get_connection(self, afip_ws):
        self.ensure_one()
        _logger.info("Getting connection for company %s and ws %s" % (self.name, afip_ws))
        now = fields.Datetime.now()
        environment_type = self._get_environment_type()

        connection = self.connection_ids.search(
            [
                ("type", "=", environment_type),
                ("generationtime", "<=", now),
                ("expirationtime", ">", now),
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
        directyl
        TODO ver si podemos usar metodos de pyafipws para esto
        """
        self.ensure_one()
        _logger.info(
            "Creating connection for company %s, environment type %s and ws "
            "%s" % (self.name, environment_type, afip_ws)
        )
        login_url = self.env["afipws.connection"].get_afip_login_url(environment_type)
        pkey, cert = self.get_key_and_certificate(environment_type)
        # Ya no necesitamos reemplazar el formato de la clave porque crypto_utils
        # soporta tanto PKCS#8 (BEGIN PRIVATE KEY) como PKCS#1 (BEGIN RSA PRIVATE KEY)
        auth_data = self.authenticate(afip_ws, cert, pkey, wsdl=login_url)
        auth_data.update(
            {
                "company_id": self.id,
                "afip_ws": afip_ws,
                "type": environment_type,
            }
        )

        auth_data["generationtime"] = (
            dateutil.parser.parse(auth_data["generationtime"]).astimezone(pytz.utc).replace(tzinfo=None)
        )
        auth_data["expirationtime"] = (
            dateutil.parser.parse(auth_data["expirationtime"]).astimezone(pytz.utc).replace(tzinfo=None)
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
        Call AFIP Authentication webservice to get token & sign using zeep.
        Reemplaza pyafipws.wsaa.WSAA con wsaa_client.WSAAClient
        """
        # Determinar ambiente según WSDL
        if wsdl:
            environment = "production" if "wsaa.afip.gov.ar" in wsdl else "homologation"
        else:
            environment = "homologation"  # Por defecto homologación

        # TTL por defecto: 12 horas (más seguro que 5 horas)
        DEFAULT_TTL = 60 * 60 * 12

        # Hash para cache
        fn = "%s.json" % hashlib.md5((service + certificate + private_key).encode("utf-8")).hexdigest()
        if cache:
            cache_dir = cache
        else:
            # Usar directorio de cache por defecto
            cache_dir = os.path.join(os.path.expanduser("~"), ".afipws_cache")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

        fn = os.path.join(cache_dir, fn)

        try:
            # Verificar si existe cache válido y no se fuerza renovación
            if not force and os.path.exists(fn) and os.path.getmtime(fn) + (DEFAULT_TTL) >= time.time():
                # Leer credenciales del cache
                _logger.info(f"Usando credenciales en cache: {fn}")
                with open(fn) as f:
                    import json

                    cached_data = json.load(f)
                    return cached_data

            # Cache expirado, forzado o no existe, autenticar con WSAA
            _logger.info(f"Autenticando con WSAA ({environment})...")

            # Crear cliente WSAA
            client = wsaa_client.WSAAClient(environment=environment, timeout=30)

            # Autenticar
            result = client.authenticate(
                service=service, certificate_pem=certificate, private_key_pem=private_key, ttl=DEFAULT_TTL
            )

            # Parsear tiempos
            generationTime = result.get("generation_time", "")
            expirationTime = result.get("expiration_time", "")
            uniqueId = result.get("unique_id", "")

            # Convertir datetime a string si es necesario
            if hasattr(generationTime, "isoformat"):
                generationTime = generationTime.isoformat()
            if hasattr(expirationTime, "isoformat"):
                expirationTime = expirationTime.isoformat()

            auth_data = {
                "uniqueid": uniqueId,
                "generationtime": generationTime,
                "expirationtime": expirationTime,
                "token": result["token"],
                "sign": result["sign"],
            }

            # Guardar en cache
            with open(fn, "w") as f:
                import json

                json.dump(auth_data, f)

            _logger.info("Autenticación exitosa, credenciales guardadas en cache")
            return auth_data

        except Exception as e:
            _logger.error(f"Error en autenticación WSAA: {e}")
            import traceback

            traceback.print_exc()
            raise UserError(_("Could not authenticate with AFIP WSAA.\\n\\nError: %s") % str(e))
