##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError

_logger = logging.getLogger(__name__)


class AfipwsConnection(models.Model):
    _inherit = "afipws.connection"

    # TODO use _get_afip_ws_selection to add values to this selection
    afip_ws = fields.Selection(
        selection_add=[
            ("wsfe", "Mercado interno -sin detalle- RG2485 (WSFEv1)"),
            ("wsmtxca", "Mercado interno -con detalle- RG2904 (WSMTXCA)"),
            ("wsfex", "Exportación -con detalle- RG2758 (WSFEXv1)"),
            ("wsbfe", "Bono Fiscal -con detalle- RG2557 (WSBFE)"),
            ("wscdc", "Constatación de Comprobantes (WSCDC)"),
        ],
        ondelete={
            "wsfe": "set default",
            "wsmtxca": "set default",
            "wsfex": "set default",
            "wsbfe": "set default",
            "wscdc": "set default",
        },
    )

    @api.model
    def _get_ws(self, afip_ws):
        """
        Method to be inherited
        """
        ws = super(AfipwsConnection, self)._get_ws(afip_ws)
        if afip_ws == "wsfe":
            # Usar nuevo cliente zeep en lugar de pyafipws
            _logger.info("Usando WSFEv1Client con zeep (nuevo)")
            # El adaptador se inicializará en connect() con las credenciales
            ws = None  # Se creará en connect()
        elif afip_ws == "wsfex":
            try:
                from pyafipws.wsfexv1 import WSFEXv1

                ws = WSFEXv1()
            except ImportError:
                raise UserError(_("pyafipws not installed. WSFEXv1 not available yet in zeep migration."))
        elif afip_ws == "wsmtxca":
            try:
                from pyafipws.wsmtx import WSMTXCA

                ws = WSMTXCA()
            except ImportError:
                raise UserError(_("pyafipws not installed. WSMTXCA not available yet in zeep migration."))
        elif afip_ws == "wscdc":
            try:
                from pyafipws.wscdc import WSCDC

                ws = WSCDC()
            except ImportError:
                raise UserError(_("pyafipws not installed. WSCDC not available yet in zeep migration."))
        elif afip_ws == "wsbfe":
            try:
                from pyafipws.wsbfev1 import WSBFEv1

                ws = WSBFEv1()
            except ImportError:
                raise UserError(_("pyafipws not installed. WSBFEv1 not available yet in zeep migration."))
        return ws

    @api.model
    def get_afip_ws_url(self, afip_ws, environment_type):
        afip_ws_url = super(AfipwsConnection, self).get_afip_ws_url(afip_ws, environment_type)
        if afip_ws_url:
            return afip_ws_url
        elif afip_ws == "wsfe":
            if environment_type == "production":
                afip_ws_url = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
            else:
                afip_ws_url = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
        elif afip_ws == "wsfex":
            if environment_type == "production":
                afip_ws_url = "https://servicios1.afip.gov.ar/wsfexv1/service.asmx?WSDL"
            else:
                afip_ws_url = "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx?WSDL"
        elif afip_ws == "wsbfe":
            if environment_type == "production":
                afip_ws_url = "https://servicios1.afip.gov.ar/wsbfev1/service.asmx?WSDL"
            else:
                afip_ws_url = "https://wswhomo.afip.gov.ar/wsbfev1/service.asmx?WSDL"
        elif afip_ws == "wsmtxca":
            raise UserError(_("AFIP WS %s Not implemented yet") % afip_ws)
            # if environment_type == 'production':
            #     afip_ws_url = (
            #         'https://serviciosjava.afip.gob.ar/wsmtxca/services/'
            #         'MTXCAService')
            # else:
            #     afip_ws_url = (
            #         'https://fwshomo.afip.gov.ar/wsmtxca/services/'
            #         'MTXCAService')
        elif afip_ws == "wscdc":
            if environment_type == "production":
                afip_ws_url = "https://servicios1.afip.gov.ar/WSCDC/service.asmx?WSDL"
            else:
                afip_ws_url = "https://wswhomo.afip.gov.ar/WSCDC/service.asmx?WSDL"
        return afip_ws_url

    def connect(self):
        """Override connect para manejar WSFEv1 con zeep.

        Sobrescribe el método base para implementar la conexión específica
        al servicio de facturación electrónica usando zeep.

        Esta implementación:
        - Usa self.type (campo del módulo base) para determinar ambiente
        - Maneja errores de conexión de forma robusta
        - Registra logs detallados para debugging
        - Mantiene compatibilidad con la interfaz pyafipws existente

        Returns:
            WSFEv1Adapter: Adaptador conectado a WSFEv1

        Raises:
            UserError: Si no se puede establecer la conexión
            RedirectWarning: Si el servicio AFIP no está disponible
        """
        self.ensure_one()

        # Si es WSFEv1, usar el nuevo cliente zeep
        if self.afip_ws == "wsfe":
            _logger.info("Conectando a WSFEv1 con zeep - connection id %s, ambiente: %s", self.id, self.type)

            try:
                from ..lib.wsfev1_adapter import WSFEv1Adapter

                # Obtener credenciales
                cuit = self.company_id.partner_id.ensure_vat()
                token = self.token
                sign = self.sign

                # Determinar ambiente usando el campo correcto del módulo base
                # ✅ CORRECTO: Usa self.type definido en l10n_ar_afipws
                environment = "production" if self.type == "production" else "homologation"

                # Crear adaptador con el nuevo cliente zeep
                ws = WSFEv1Adapter(cuit, token, sign, environment)

                # Configurar atributos de compatibilidad con interfaz pyafipws
                ws.Cuit = cuit
                ws.Token = token
                ws.Sign = sign
                ws.Obs = ""
                ws.Errores = []

                _logger.info('WSFEv1 conectado exitosamente - CUIT: "%s", ambiente: %s', cuit, environment)
                return ws

            except ImportError as e:
                _logger.error("Error importando WSFEv1Adapter: %s", str(e), exc_info=True)
                raise UserError(
                    _(
                        "No se pudo cargar el adaptador WSFEv1.\n\n"
                        "Error: %s\n\n"
                        "Verifique que el módulo esté correctamente instalado."
                    )
                    % str(e)
                )

            except Exception as e:
                _logger.error("Error al conectar con AFIP WSFEv1 (%s): %s", self.type, str(e), exc_info=True)

                # Detectar errores de conectividad AFIP
                error_repr = repr(e)
                if any(
                    err in error_repr
                    for err in [
                        "ExpatError",
                        "mismatched tag",
                        "Conexión reinicializada",
                        "Connection reset",
                        "Timeout",
                    ]
                ):
                    action = self.env.ref("l10n_ar_afipws.action_afip_padron")
                    msg = _(
                        "Parece que el servicio de AFIP no está disponible.\n\n"
                        "Por favor intente nuevamente más tarde."
                    )
                    raise RedirectWarning(msg, action.id, _("Ir a configuración AFIP"))

                # Error genérico
                raise UserError(
                    _(
                        "Error al conectar con el servicio de Factura Electrónica de AFIP.\n\n"
                        "Ambiente: %s\n"
                        "Error: %s\n\n"
                        "Verifique:\n"
                        "- Conexión a internet\n"
                        "- Estado de los servicios AFIP\n"
                        "- Certificados y tokens válidos"
                    )
                    % (self.type, str(e))
                )

        # Para otros servicios, usar el método original con pyafipws
        return super(AfipwsConnection, self).connect()
