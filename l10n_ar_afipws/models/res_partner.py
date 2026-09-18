##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields, models, _
from odoo.exceptions import UserError
import logging
import zeep.helpers

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
        # census es dict zeep serializado (ex pyafipws object)
        def _get(key, default=False):
            if isinstance(census, dict):
                return census.get(key, default)
            return getattr(census, key, default)

        imp_iva = _get("imp_iva")
        if imp_iva == "S":
            imp_iva = "AC"
        elif imp_iva == "N":
            imp_iva = "NI"

        vals = {
            "name": _get("denominacion"),
            "street": _get("direccion"),
            "city": _get("localidad"),
            "zip": _get("cod_postal"),
            "imp_iva_padron": imp_iva,
            "last_update_census": fields.Date.today(),
        }

        impuestos = _get("impuestos", []) or []
        monotributo = _get("monotributo")
        provincia = _get("provincia")
        localidad = _get("localidad")

        ganancias_inscripto = [10, 11]
        ganancias_exento = [12]
        if set(ganancias_inscripto) & set(impuestos):
            vals["imp_ganancias_padron"] = "AC"
        elif set(ganancias_exento) & set(impuestos):
            vals["imp_ganancias_padron"] = "EX"
        elif monotributo == "S":
            vals["imp_ganancias_padron"] = "NC"
        else:
            _logger.info(
                "We couldn't get impuesto a las ganancias from padron, you"
                "must set it manually"
            )

        if provincia:
            caba_codes = ["C", "CABA", "ABA"]
            if not localidad:
                state = self.env["res.country.state"].search(
                    [("code", "in", caba_codes), ("country_id.code", "=", "AR")],
                    limit=1,
                )
            else:
                state = self.env["res.country.state"].search(
                    [
                        ("name", "ilike", provincia),
                        ("code", "not in", caba_codes),
                        ("country_id.code", "=", "AR"),
                    ],
                    limit=1,
                )
            if state:
                vals["state_id"] = state.id

        if imp_iva == "NI" and monotributo == "S":
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

    # Mapeo categoría IVA AFIP -> código l10n_ar (port trixocom padron.py)
    CATEGORIA_IVA_CODIGO = {
        "RESPONSABLE INSCRIPTO": "1",
        "IVA RESPONSABLE INSCRIPTO": "1",
        "EXENTO": "4",
        "IVA SUJETO EXENTO": "4",
        "CONSUMIDOR FINAL": "5",
        "MONOTRIBUTO": "6",
        "RESPONSABLE MONOTRIBUTO": "6",
        "MONOTRIBUTO SOCIAL": "13",
        "MONOTRIBUTISTA SOCIAL": "13",
        "MONOTRIBUTO TRABAJADOR INDEPENDIENTE PROMOVIDO": "16",
        "NO ALCANZADO": "15",
        "IVA NO ALCANZADO": "15",
    }

    def _zeep_parse_padron_a5(self, ret):
        """Convierte respuesta zeep A5 a dict compatible con parce_census_vals.

        Acepta `getPersona_v2` (trixocom) y `getPersona` legacy: detecta
        `datosGenerales/datosMonotributo/datosRegimenGeneral` o fallback plano.
        NOTA delegación AFIP: el TA debe ser del servicio
        `ws_sr_constancia_inscripcion` para A5; `ws_sr_padron_a13` es un
        trámite separado (delegar uno NO autoriza el otro).
        """
        data = ret.get("datosGenerales", {}) or {}
        data_mt = ret.get("datosMonotributo", {}) or {}
        data_rg = ret.get("datosRegimenGeneral", {}) or {}
        impuestos_mt = data_mt.get("impuesto", []) or []
        impuestos_rg = data_rg.get("impuesto", []) or []
        if isinstance(impuestos_mt, dict):
            impuestos_mt = [impuestos_mt]
        if isinstance(impuestos_rg, dict):
            impuestos_rg = [impuestos_rg]
        impuestos = [i.get("idImpuesto") for i in (impuestos_mt + impuestos_rg) if i.get("idImpuesto")]
        # IVA: misma lógica que pyafipws analizar_datos
        if 32 in impuestos:
            imp_iva = "EX"
        elif 33 in impuestos:
            imp_iva = "NI"
        elif 34 in impuestos:
            imp_iva = "NA"
        else:
            imp_iva = "S" if 30 in impuestos else "N"
        cat_mt = data_mt.get("categoriaMonotributo", {}) or {}
        monotributo = "S" if cat_mt else "N"
        # Inferencia categoría IVA (port trixocom): MT > IVA(30) > EX(32) > NA(33)
        if monotributo == "S":
            categoria_iva, categoria_iva_codigo = "MONOTRIBUTO", "6"
        elif 30 in impuestos:
            categoria_iva, categoria_iva_codigo = "RESPONSABLE INSCRIPTO", "1"
        elif 32 in impuestos:
            categoria_iva, categoria_iva_codigo = "IVA SUJETO EXENTO", "4"
        elif 33 in impuestos:
            categoria_iva, categoria_iva_codigo = "IVA NO ALCANZADO", "15"
        else:
            categoria_iva, categoria_iva_codigo = None, None
        domicilio = data.get("domicilioFiscal", {}) or {}
        id_prov = domicilio.get("idProvincia")
        try:
            id_prov = int(id_prov) if id_prov is not None else None
        except Exception:
            id_prov = None
        from .afipws_zeep import PROVINCIAS

        return {
            "denominacion": data.get("razonSocial") or ", ".join([
                data.get("apellido", ""), data.get("nombre", "")]),
            "direccion": domicilio.get("direccion", ""),
            "localidad": domicilio.get("localidad", ""),
            "provincia": PROVINCIAS.get(id_prov, ""),
            "cod_postal": domicilio.get("codPostal"),
            "imp_iva": imp_iva,
            "impuestos": impuestos,
            "monotributo": monotributo,
            "categoria_iva": categoria_iva,
            "categoria_iva_codigo": categoria_iva_codigo,
        }

    def get_data_from_padron_afip(self):
        self.ensure_one()
        cuit = self.ensure_vat()

        company = self.env.user.company_id
        env_type = company._get_environment_type()
        try:
            company.get_key_and_certificate(company._get_environment_type())
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
        connection = company.get_connection("ws_sr_constancia_inscripcion")
        error_msg = _(
            "No pudimos actualizar desde padron afip al partner %s (%s).\n"
            "Recomendamos verificar manualmente en la página de AFIP.\n"
            "Obtuvimos este error: %s"
        )
        try:
            client, auth, transport = connection.connect()
            cuit_rep = company.partner_id.ensure_vat()
            # A5 expone getPersona_v2; fallback a getPersona si el WSDL no lo trae
            method = getattr(client.service, "getPersona_v2", None) or getattr(
                client.service, "getPersona", None)
            if method is None:
                raise UserError(error_msg % (self.name, cuit, "WSDL sin getPersona"))
            response = method(
                sign=auth["Sign"], token=auth["Token"],
                cuitRepresentada=cuit_rep, idPersona=cuit,
            )
            ret = zeep.helpers.serialize_object(response, dict).get("personaReturn", {})
            errores = []
            for key in ("errorConstancia", "errorMonotributo", "errorRegimenGeneral"):
                err = ret.get(key)
                if err:
                    if isinstance(err, dict):
                        errores.append(err.get("error", str(err)))
                    elif isinstance(err, list):
                        errores += [e.get("error", str(e)) if isinstance(e, dict) else str(e) for e in err]
            datos = ret.get("datosGenerales", {}) if isinstance(ret, dict) else {}
            denominacion = (datos.get("razonSocial") or "") if isinstance(datos, dict) else ""
            if not denominacion or denominacion.strip() in ("", ","):
                # fallback apellido/nombre
                apellido = datos.get("apellido", "") if isinstance(datos, dict) else ""
                nombre = datos.get("nombre", "") if isinstance(datos, dict) else ""
                denominacion = ", ".join([apellido, nombre])
            if not denominacion or denominacion.strip() in ("", ",", ", "):
                raise UserError(error_msg % (self.name, cuit, "; ".join(errores) or "La afip no devolvió nombre"))
            census = self._zeep_parse_padron_a5(ret)
        except UserError:
            raise
        except Exception as e:
            raise UserError(error_msg % (self.name, cuit, e))

        vals = self.parce_census_vals(census)
        return vals

    def l10n_ar_afipws_fe_min_ammount(self):
        for record in self:
            if record.l10n_ar_vat:
                connection = self.env.user.company_id.get_connection("wsfecred")
                client, auth, transport = connection.connect()
                cuit_rep = self.env.user.company_id.partner_id.ensure_vat()
                response = client.service.consultarMontoObligadoRecepcion(
                    authRequest={
                        "token": auth["Token"], "sign": auth["Sign"],
                        "cuitRepresentada": cuit_rep,
                    },
                    cuitConsultada=record.l10n_ar_vat,
                )
                ret = zeep.helpers.serialize_object(response, dict).get(
                    "consultarMontoObligadoRecepcionReturn", {})
                record.mipyme_required = True if ret.get("obligado") == "S" else False
                record.mipyme_from_amount = float(ret.get("montoDesde") or 0.0)
