##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

from odoo.addons.l10n_ar_afipws.models.afipws_zeep import normalize_env

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
        """Deprecado: pyafipws eliminado. Usar _get_client/connect (zeep)."""
        raise UserError(
            _("pyafipws was removed, use zeep connect() for ws %s") % (afip_ws,)
        )

    @api.model
    def get_afip_ws_url(self, afip_ws, environment_type):
        afip_ws_url = super(AfipwsConnection, self).get_afip_ws_url(
            afip_ws, environment_type
        )
        if afip_ws_url:
            return afip_ws_url
        env = normalize_env(environment_type)
        prod = env == "production"
        if afip_ws == "wsfe":
            afip_ws_url = (
                "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
                if prod
                else "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
            )
        elif afip_ws == "wsfex":
            afip_ws_url = (
                "https://servicios1.afip.gov.ar/wsfexv1/service.asmx?WSDL"
                if prod
                else "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx?WSDL"
            )
        elif afip_ws == "wsbfe":
            afip_ws_url = (
                "https://servicios1.afip.gov.ar/wsbfev1/service.asmx?WSDL"
                if prod
                else "https://wswhomo.afip.gov.ar/wsbfev1/service.asmx?WSDL"
            )
        elif afip_ws == "wsmtxca":
            raise UserError(_("AFIP WS %s Not implemented yet") % afip_ws)
        elif afip_ws == "wscdc":
            afip_ws_url = (
                "https://servicios1.afip.gov.ar/WSCDC/service.asmx?WSDL"
                if prod
                else "https://wswhomo.afip.gov.ar/WSCDC/service.asmx?WSDL"
            )
        return afip_ws_url
