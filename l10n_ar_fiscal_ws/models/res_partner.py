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

        # Buscar país Argentina
        country_ar = self.env["res.country"].search([("code", "=", "AR")], limit=1)
        
        vals = {
            "name": census.denominacion,
            "street": census.direccion,
            "city": census.localidad,
            "zip": census.cod_postal,
            "last_update_census": fields.Date.today(),
        }
        
        if country_ar:
            vals["country_id"] = country_ar.id

        # Nota: Los campos imp_iva_padron e imp_ganancias_padron fueron removidos
        # La información de IVA y Ganancias ahora se maneja únicamente a través de
        # l10n_ar_afip_responsibility_type_id

        # Buscar provincia argentina por nombre
        # Usamos descripcionProvincia ya que el mapeo de idProvincia de ARCA
        # no está documentado completamente
        state = None
        
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

        # Determinar responsabilidad AFIP según imp_iva y monotributo
        _logger.info("Determinando responsabilidad AFIP - imp_iva:%s, monotributo:%s", imp_iva, census.monotributo)
        
        if imp_iva == "NI" and census.monotributo == "S":
            # Monotributista
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref("l10n_ar.res_RM").id
            _logger.info("Asignando Monotributista (RM)")
        elif imp_iva == "AC":
            # Responsable Inscripto IVA
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref("l10n_ar.res_IVARI").id
            _logger.info("Asignando Responsable Inscripto IVA (IVARI)")
        elif imp_iva == "EX":
            # IVA Exento
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref("l10n_ar.res_IVAE").id
            _logger.info("Asignando IVA Exento (IVAE)")
        elif imp_iva == "N" or imp_iva == "NI":
            # No inscripto (consumidor final o similar)
            vals["l10n_ar_afip_responsibility_type_id"] = self.env.ref("l10n_ar.res_CF").id
            _logger.info("Asignando Consumidor Final (CF)")
        else:
            _logger.warning("No se pudo inferir la responsabilidad AFIP desde padrón - imp_iva:%s, monotributo:%s", 
                          imp_iva, census.monotributo)

        _logger.info("Valores finales a actualizar: %s", vals)
        return vals

    def get_data_from_padron_arca(self):
        self.ensure_one()
        cuit = self.ensure_vat()

        company = self.env.company

        try:
            # Usamos Servicio de Constancia de Inscripción de ARCA (antes conocido como Padrón A5)
            # - Nombre oficial: ws_sr_constancia_inscripcion (según manual técnico ARCA v3.5)
            # - Método: getPersona (la versión _v2 está deprecada)
            # - Estructura: datosGenerales, datosMonotributo, datosRegimenGeneral
            # - Incluye: situación frente a IVA, Ganancias, Monotributo y domicilio fiscal
            padron = company.arca_get_connection("ws_sr_constancia_inscripcion")
            res = padron.call_arca_service("getPersona", {"idPersona": cuit}, auth="plain")

            _logger.warning("===== DEBUG ARCA CONSTANCIA INSCRIPCION RESPONSE =====")
            _logger.warning("CUIT consultado: %s", cuit)
            _logger.warning("Tipo de objeto: %s", type(res))
            _logger.warning("Atributos disponibles: %s", dir(res))
            _logger.warning("Contenido completo: %s", res)
            _logger.warning("==================================")

            # Verificar errores reportados por ARCA antes de procesar datos
            error_messages = []
            
            if hasattr(res, "errorConstancia") and res.errorConstancia:
                error_info = res.errorConstancia
                if hasattr(error_info, "error") and error_info.error:
                    error_messages.extend(error_info.error)
            
            if hasattr(res, "errorMonotributo") and res.errorMonotributo:
                error_info = res.errorMonotributo
                if hasattr(error_info, "error") and error_info.error:
                    error_messages.extend(error_info.error)
            
            if hasattr(res, "errorRegimenGeneral") and res.errorRegimenGeneral:
                error_info = res.errorRegimenGeneral
                if hasattr(error_info, "error") and error_info.error:
                    error_messages.extend(error_info.error)
            
            # Si hay errores de ARCA, mostrarlos al usuario
            if error_messages:
                error_text = "\n• ".join(error_messages)
                raise UserError(
                    _("ARCA reportó los siguientes problemas para el CUIT %s:\n\n• %s\n\n"
                      "Por favor, verifique la situación del contribuyente en:\n"
                      "https://www.arca.gob.ar/") % (cuit, error_text)
                )

            # Estructura del servicio: datosGenerales, datosMonotributo, datosRegimenGeneral
            if not hasattr(res, "datosGenerales") or not res.datosGenerales:
                raise UserError(
                    _("ARCA no devolvió datos válidos para el CUIT %s.\n"
                      "Estructura recibida: %s") % (cuit, dir(res))
                )

            datos_generales = res.datosGenerales
            datos_monotributo = getattr(res, "datosMonotributo", None)
            datos_regimen_general = getattr(res, "datosRegimenGeneral", None)

            # Construir denominación
            apellido = getattr(datos_generales, "apellido", "") or ""
            nombre = getattr(datos_generales, "nombre", "") or ""
            razon_social = getattr(datos_generales, "razonSocial", None)
            
            if razon_social:
                denominacion = razon_social
            else:
                denominacion = f"{apellido}, {nombre}".strip(", ")

            if not denominacion:
                raise UserError(
                    _("ARCA no devolvió nombre válido para el CUIT %s") % cuit
                )

            # Extraer domicilio
            domicilio_fiscal = None
            if hasattr(datos_generales, "domicilioFiscal") and datos_generales.domicilioFiscal:
                domicilio_fiscal = datos_generales.domicilioFiscal
            
            # Determinar imp_iva y monotributo desde las diferentes secciones
            imp_iva = "N"
            monotributo = "N"
            impuestos_ids = []
            
            # Verificar régimen general (IVA, Ganancias, etc.)
            if datos_regimen_general and hasattr(datos_regimen_general, "impuesto"):
                for impuesto in datos_regimen_general.impuesto:
                    id_imp = getattr(impuesto, "idImpuesto", None)
                    estado = getattr(impuesto, "estadoImpuesto", "")
                    if estado == "ACTIVO" or estado == "AC":
                        impuestos_ids.append(id_imp)
                        if id_imp == 30:  # IVA
                            imp_iva = "AC"
            
            # Verificar monotributo
            if datos_monotributo and hasattr(datos_monotributo, "categoriaMonotributo"):
                monotributo = "S"
                impuestos_ids.append(308)  # ID Monotributo
            
            # Crear objeto compatible con parce_census_vals
            class CensusConstanciaAdapter:
                pass
            
            census_adapted = CensusConstanciaAdapter()
            census_adapted.denominacion = denominacion
            census_adapted.direccion = getattr(domicilio_fiscal, "direccion", "") if domicilio_fiscal else ""
            census_adapted.localidad = getattr(domicilio_fiscal, "localidad", "") if domicilio_fiscal else ""
            census_adapted.cod_postal = getattr(domicilio_fiscal, "codPostal", "") if domicilio_fiscal else ""
            census_adapted.provincia = getattr(domicilio_fiscal, "descripcionProvincia", "") if domicilio_fiscal else ""
            census_adapted.imp_iva = imp_iva
            census_adapted.impuestos = impuestos_ids
            census_adapted.monotributo = monotributo
            
            _logger.info(
                "Constancia Inscripción ARCA procesada - %s - IVA:%s Monotributo:%s Impuestos:%s",
                denominacion, imp_iva, monotributo, impuestos_ids
            )

            vals = self.parce_census_vals(census_adapted)
            return vals

        except Exception as error:
            error_msg = _(
                "No pudimos actualizar desde padrón ARCA al partner %s (%s).\n"
                "Recomendamos verificar manualmente en la página de ARCA.\n\n"
                "Error técnico: %s"
            )
            raise UserError(error_msg % (self.name, cuit, error)) from error

    def action_update_from_padron_arca(self):
        """Actualiza automáticamente los datos del partner desde padrón ARCA"""
        self.ensure_one()
        
        vals = self.get_data_from_padron_arca()
        self.write(vals)
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Actualización exitosa"),
                "message": _("Los datos del partner se actualizaron correctamente desde ARCA"),
                "type": "success",
                "sticky": False,
            },
        }

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
