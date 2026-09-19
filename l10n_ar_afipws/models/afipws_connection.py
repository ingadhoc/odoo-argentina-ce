##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError, RedirectWarning
import logging

from .afipws_zeep import (
    get_afip_ws_url as _zeep_ws_url,
    get_wsaa_wsdl,
    make_zeep_client,
    normalize_env,
)

_logger = logging.getLogger(__name__)


class AfipwsConnection(models.Model):

    _name = "afipws.connection"
    _description = "AFIP WS Connection"
    _rec_name = "afip_ws"
    _order = "expirationtime desc"

    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        index=True,
        auto_join=True,
    )
    uniqueid = fields.Char(
        "Unique ID",
        readonly=True,
    )
    token = fields.Text(
        "Token",
        readonly=True,
    )
    sign = fields.Text(
        "Sign",
        readonly=True,
    )
    generationtime = fields.Datetime("Generation Time", readonly=True)
    expirationtime = fields.Datetime("Expiration Time", readonly=True)
    afip_login_url = fields.Char(
        "AFIP Login URL",
        compute="_compute_afip_urls",
    )
    afip_ws_url = fields.Char(
        "AFIP WS URL",
        compute="_compute_afip_urls",
    )
    type = fields.Selection(
        [("production", "Production"), ("homologation", "Homologation")],
        "Type",
        required=True,
    )
    afip_ws = fields.Selection(
        [
            ("ws_sr_padron_a4", "Servicio de Consulta de Padrón Alcance 4"),
            ("ws_sr_constancia_inscripcion", "Constancia de Inscripción"),
            ("ws_sr_padron_a10", "Servicio de Consulta de Padrón Alcance 10"),
            ("ws_sr_padron_a100", "Servicio de Consulta de Padrón Alcance 100"),
            ("wsfecred", "Servicio de Consulta para facturas de credito"),
        ],
        "AFIP WS",
        required=True,
        default="ws_sr_constancia_inscripcion",
    )

    @api.depends("type", "afip_ws")
    def _compute_afip_urls(self):
        for rec in self:
            rec.afip_login_url = rec.get_afip_login_url(rec.type)
            afip_ws_url = rec.get_afip_ws_url(rec.afip_ws, rec.type)
            if rec.afip_ws and not afip_ws_url:
                raise UserError(_("Webservice %s not supported") % rec.afip_ws)
            rec.afip_ws_url = afip_ws_url

    @api.model
    def get_afip_login_url(self, environment_type):
        return get_wsaa_wsdl(normalize_env(environment_type)).replace("?WSDL", "")

    @api.model
    def get_afip_ws_url(self, afip_ws, environment_type):
        """Function to be inherited on each module that add a new webservice."""
        _logger.info("Getting URL for afip ws %s on %s" % (afip_ws, environment_type))
        return _zeep_ws_url(afip_ws, normalize_env(environment_type))

    def check_afip_ws(self, afip_ws):
        self.ensure_one()
        if self.afip_ws != afip_ws:
            raise UserError(
                _(
                    "This method is for %s connections and you call it from an"
                    " %s connection"
                )
                % (afip_ws, self.afip_ws)
            )

    def _get_client(self, return_transport=False):
        """Cliente zeep + auth dict (port tipo ref 15, mismos nombres)."""
        self.ensure_one()
        wsdl = self.afip_ws_url
        if not wsdl:
            raise UserError(_("Webservice %s not supported") % self.afip_ws)
        auth = {
            "Token": self.token,
            "Sign": self.sign,
            "Cuit": self.company_id.partner_id.ensure_vat(),
        }
        try:
            client, transport = make_zeep_client(wsdl, log_xml=True)
        except Exception as error:
            self._process_connection_error(error, self.type, self.afip_ws)
        if return_transport:
            return client, auth, transport
        return client, auth

    @api.model
    def _process_connection_error(self, error, env_type, afip_ws):
        """Mensajes útiles de conexión (ref 15 + catálogo trixocom, PR-seguro).

        El catálogo `afipws_errors` aporta code/hint; los mensajes legacy se
        mantienen como fallback para no cambiar UX en códigos no catalogados.
        """
        from .afipws_errors import get_wsaa_hint

        error_name = error.args[0] if getattr(error, "args", ()) else repr(error)
        error_msg = _("There was a problem with the connection to the %s webservice: %s") % (
            afip_ws,
            error_name,
        )
        _desc, hint_msg = get_wsaa_hint(str(error_name))
        if not hint_msg:
            certificate_expired = _("It seems like the certificate has expired. Please renew your AFIP certificate")
            token_in_use = "El CEE ya posee un TA valido para el acceso al WSN solicitado"
            hints = {
                "Computador no autorizado a acceder al servicio": _(
                    "The certificate is not authorized (delegated) to work with this web service"
                ),
                "ns1:cms.sign.invalid: Firma inválida o algoritmo no soportado": certificate_expired,
                "ns1:cms.cert.expired: Certificado expirado": certificate_expired,
                "500 Server Error: Internal Server": _("Webservice is down"),
                token_in_use: _(
                    "Are you invoicing from another computer or system? "
                    "You will need to wait 12 hours to generate a new token."
                ),
                "No se puede decodificar el BASE64": _("The certificate and private key do not match"),
            }
            for item, value in hints.items():
                if item in str(error_name):
                    hint_msg = value
                    break
            if token_in_use in str(error_name) and normalize_env(env_type) in ("homologation", "testing"):
                hint_msg = _(
                    "The testing certificate is being used by another person, wait 10 minutes "
                    "and try again or use another demo certificate."
                )
        if hint_msg:
            error_msg += "\n\nHINT: " + str(hint_msg)
        else:
            error_msg += "\n\n" + _("Please report this error to your Odoo provider")
        raise UserError(error_msg)

    def connect(self):
        """Compat: devuelve (client, auth, transport) zeep.

        El nombre se mantiene para no romper llamadas internas/externas;
        el objeto pyafipws anterior se elimina (ver PR: migración a zeep).
        """
        self.ensure_one()
        _logger.info(
            "Getting zeep connection to ws %s (connection id %s)",
            self.afip_ws,
            self.id,
        )
        try:
            return self._get_client(return_transport=True)
        except UserError:
            raise
        except Exception as error:
            if "mismatched tag" in repr(error) or "ExpatError" in repr(error):
                try:
                    action = self.env.ref("l10n_ar_afipws.action_afip_padron")
                    action_id = action.id
                except Exception:
                    action_id = False
                msg = _(
                    "It seems like AFIP service is not available.\nPlease try again later or try manually"
                )
                raise RedirectWarning(msg, action_id, _("Go and find data manually"))
            raise UserError(
                _("There was a connection problem to AFIP. Error\n\n%s") % repr(error)
            )

    @api.model
    def _get_ws(self, afip_ws):
        """Deprecado: pyafipws eliminado. Usar _get_client/connect (zeep)."""
        raise UserError(
            _("pyafipws was removed, use zeep connect() for ws %s") % (afip_ws,)
        )
