##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

import logging

from odoo import fields, models
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

    # Separo esto para poder heredar de otros
    # modulos y extender los datos
    def parce_census_vals(self, census):
        # porque imp_iva activo puede ser S o AC
        imp_iva = census.imp_iva
        if imp_iva == "S":
            imp_iva = "AC"
        elif imp_iva == "N":
            # por ej. monotributista devuelve N
            imp_iva = "NI"

        vals = {
            "name": census.denominacion,
            "street": census.direccion,
            "city": census.localidad,
            "zip": census.cod_postal,
            "imp_iva_padron": imp_iva,
            "last_update_census": fields.Date.today(),
        }

        # padron.idProvincia

        ganancias_inscripto = [10, 11]
        ganancias_exento = [12]
        if set(ganancias_inscripto) & set(census.impuestos):
            vals["imp_ganancias_padron"] = "AC"
        elif set(ganancias_exento) & set(census.impuestos):
            vals["imp_ganancias_padron"] = "EX"
        elif census.monotributo == "S":
            vals["imp_ganancias_padron"] = "NC"
        else:
            _logger.info("We couldn't get impuesto a las ganancias from padron, you" "must set it manually")

        if census.provincia:
            # depending on the database, caba can have one of this codes
            caba_codes = ["C", "CABA", "ABA"]
            # if not localidad then it should be CABA.
            if not census.localidad:
                state = self.env["res.country.state"].search(
                    [("code", "in", caba_codes), ("country_id.code", "=", "AR")],
                    limit=1,
                )
            # If localidad cant be caba
            else:
                state = self.env["res.country.state"].search(
                    [
                        ("name", "ilike", census.provincia),
                        ("code", "not in", caba_codes),
                        ("country_id.code", "=", "AR"),
                    ],
                    limit=1,
                )
            if state:
                vals["state_id"] = state.id

        if imp_iva == "NI" and census.monotributo == "S":
            vals["l10n_ar_arca_responsibility_type_id"] = self.env.ref("l10n_ar.res_RM").id
        elif imp_iva == "AC":
            vals["l10n_ar_arca_responsibility_type_id"] = self.env.ref("l10n_ar.res_IVARI").id
        elif imp_iva == "EX":
            vals["l10n_ar_arca_responsibility_type_id"] = self.env.ref("l10n_ar.res_IVAE").id
        else:
            _logger.info("We couldn't infer the ARCA responsability from padron, you" "must set it manually.")

        return vals

    def get_data_from_padron_arca(self):
        self.ensure_one()
        cuit = self.ensure_vat()

        company = self.env.company

        # consultamos a5 ya que extiende a4 y tiene validez de constancia
        padron = company.arca_get_connection("ws_sr_padron_a5")
        # try:
        res = padron.call_arca_service("getPersona_v2", {"idPersona": cuit}, auth="plain")
        raise UserError(res)
        # except Exception as e:
        # error_msg = _(
        #     "No pudimos actualizar desde padron arca al partner %s (%s).\n"
        #     "Recomendamos verificar manualmente en la página de ARCA.\n"
        #     "Obtuvimos este error: %s"
        # )
        #     raise UserError(error_msg % (self.name, cuit, e))

        # if not res.get("denominacion") or res.get("denominacion") == ", ":
        #     raise UserError(error_msg % (self.name, cuit, "La arca no devolvió nombre"))
        # vals = self.parce_census_vals(res)
        # return vals

    def l10n_ar_fiscal_ws_fe_min_ammount(self):
        for record in self:
            if record.l10n_ar_vat:
                ws = self.env.company.arca_get_connection("wsfecred")
                res = ws.call_arca_service(
                    "ConsultarMontoObligadoRecepcion",
                    {"cuitConsultada": record.l10n_ar_vat, "fechaEmision": fields.Date.today()},
                )
                return res
                # record.mipyme_required = True if ws.Resultado == "S" else False
                # record.mipyme_from_amount = float(res)
