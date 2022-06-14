##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

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
            _logger.info(
                "We couldn't get impuesto a las ganancias from padron, you"
                "must set it manually"
            )

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
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref(
                "l10n_ar.res_RM"
            ).id
        elif imp_iva == "AC":
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref(
                "l10n_ar.res_IVARI"
            ).id
        elif imp_iva == "EX":
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref(
                "l10n_ar.res_IVAE"
            ).id
        else:
            _logger.info(
                "We couldn't infer the AFIP responsability from padron, you"
                "must set it manually."
            )

        return vals

    def get_data_from_padron_afip(self):
        self.ensure_one()
        cuit = self.ensure_vat()

        # GET COMPANY
        # if there is certificate for user company, use that one, if not
        # use the company for the first certificate found
        company = self.env.user.company_id
        env_type = company._get_environment_type()
        try:
            certificate = company.get_key_and_certificate(
                company._get_environment_type()
            )
        except Exception:
            certificate = self.env["afipws.certificate"].search(
                [
                    ("alias_id.type", "=", env_type),
                    ("state", "=", "confirmed"),
                ],
                limit=1,
            )
            if not certificate:
                raise UserError(_("Not confirmed certificate found on database"))
            company = certificate.alias_id.company_id

        # consultamos a5 ya que extiende a4 y tiene validez de constancia
        padron = company.get_connection("ws_sr_padron_a5").connect()
        error_msg = _(
            "No pudimos actualizar desde padron afip al partner %s (%s).\n"
            "Recomendamos verificar manualmente en la página de AFIP.\n"
            "Obtuvimos este error: %s"
        )
        try:
            padron.Consultar(cuit)
        except Exception as e:
            raise UserError(error_msg % (self.name, cuit, e))

        if not padron.denominacion or padron.denominacion == ", ":
            raise UserError(error_msg % (self.name, cuit, "La afip no devolvió nombre"))
        vals = self.parce_census_vals(padron)
        return vals

    def l10n_ar_afipws_fe_min_ammount(self):
        for record in self:
            if record.l10n_ar_vat:
                ws = self.env.user.company_id.get_connection("wsfecred").connect()
                res = ws.ConsultarMontoObligadoRecepcion(record.l10n_ar_vat)
                record.mipyme_required = True if ws.Resultado == "S" else False
                record.mipyme_from_amount = float(res)
