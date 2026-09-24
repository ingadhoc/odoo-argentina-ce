##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    mipyme_required = fields.Boolean(
        string="Must credit invoice",
    )
    mipyme_from_amount = fields.Float(
        string="Credit invoice from amount",
    )
    last_update_census = fields.Date(string="Last update census")

    # Tax ids of the census service, needed to infer the responsibility type
    CENSUS_VAT_TAX = 30
    CENSUS_VAT_EXEMPT_TAX = 32
    CABA_STATE_CODES = ["C", "CABA", "ABA"]

    def _l10n_ar_census_values(self, response):
        """Values of a contact, read from the census answer. Meant to be extended."""
        self.ensure_one()
        general = response.datosGenerales
        address = general.domicilioFiscal
        values = {
            "name": general.razonSocial or " ".join(filter(None, [general.apellido, general.nombre])),
            "last_update_census": fields.Date.context_today(self),
        }
        if address:
            values.update({"street": address.direccion, "city": address.localidad, "zip": address.codPostal})
            state = self._l10n_ar_census_state(address)
            if state:
                values["state_id"] = state.id

        responsibility = self._l10n_ar_census_responsibility(response)
        if responsibility:
            values["l10n_ar_afip_responsibility_type_id"] = responsibility.id
        else:
            _logger.info("The census did not say the responsibility of %s, set it by hand", self.display_name)
        return values

    def _l10n_ar_census_state(self, address):
        if not address.descripcionProvincia:
            # without province the address belongs to the city of Buenos Aires
            return self.env["res.country.state"].search(
                [("code", "in", self.CABA_STATE_CODES), ("country_id.code", "=", "AR")], limit=1
            )
        return self.env["res.country.state"].search(
            [
                ("name", "ilike", address.descripcionProvincia),
                ("code", "not in", self.CABA_STATE_CODES),
                ("country_id.code", "=", "AR"),
            ],
            limit=1,
        )

    def _l10n_ar_census_responsibility(self, response):
        if response.datosMonotributo:
            return self.env.ref("l10n_ar.res_RM")
        taxes = getattr(response.datosRegimenGeneral, "impuesto", None) or []
        active_taxes = {tax.idImpuesto for tax in taxes if tax.estadoImpuesto == "ACTIVO"}
        if self.CENSUS_VAT_TAX in active_taxes:
            return self.env.ref("l10n_ar.res_IVARI")
        if self.CENSUS_VAT_EXEMPT_TAX in active_taxes:
            return self.env.ref("l10n_ar.res_IVAE")
        return self.env["l10n_ar.afip.responsibility.type"]

    def l10n_ar_get_data_from_census(self):
        """Values of this contact according to the census service."""
        self.ensure_one()
        self.ensure_vat()
        mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping("ws_sr_padron_a5", "person")
        response, _xml = mapping.call(self)
        census = getattr(response, "datosGenerales", None)
        if not census or not census.apellido and not census.razonSocial:
            raise UserError(
                _("El padrón no devolvió datos para %(name)s (%(vat)s).", name=self.name, vat=self.l10n_ar_vat)
            )
        return self._l10n_ar_census_values(response)

    def l10n_ar_update_mipyme_status(self):
        """Whether this contact must be invoiced with a credit invoice, and from which amount."""
        for record in self.filtered("l10n_ar_vat"):
            mapping = self.env["l10n_ar.fiscal.ws.mapping"]._get_mapping("wsfecred", "obliged_amount")
            response, _xml = mapping.call(record, {"date": fields.Date.context_today(record)})
            record.mipyme_required = response.obligado == "S"
            record.mipyme_from_amount = float(response.montoDesde or 0)
