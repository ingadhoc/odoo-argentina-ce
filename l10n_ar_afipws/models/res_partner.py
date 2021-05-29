##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################

from odoo import fields, models, api, _
from odoo.exceptions import UserError
try:
    from pysimplesoap.client import SoapFault
except ImportError:
    SoapFault = None
import logging
_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def cuit_required(self):
        self.ensure_one()
        if not self.vat:
            raise UserError(_('No CUIT configured for partner [%i] %s') % (
                self.id, self.name))
        return self.vat

    def get_data_from_padron_afip(self):
        self.ensure_one()
        cuit = self.cuit_required()

        # GET COMPANY
        # if there is certificate for user company, use that one, if not
        # use the company for the first certificate found
        company = self.env.user.company_id
        env_type = company._get_environment_type()
        try:
            certificate = company.get_key_and_certificate(
                company._get_environment_type())
        except Exception:
            certificate = self.env['afipws.certificate'].search([
                ('alias_id.type', '=', env_type),
                ('state', '=', 'confirmed'),
            ], limit=1)
            if not certificate:
                raise UserError(_(
                    'Not confirmed certificate found on database'))
            company = certificate.alias_id.company_id

        # consultamos a5 ya que extiende a4 y tiene validez de constancia
        padron = company.get_connection('ws_sr_padron_a5').connect()
        error_msg = _(
            'No pudimos actualizar desde padron afip al partner %s (%s).\n'
            'Recomendamos verificar manualmente en la página de AFIP.\n'
            'Obtuvimos este error: %s')
        try:
            padron.Consultar(cuit)
        except SoapFault as e:
            raise UserError(error_msg % (self.name, cuit, e.faultstring))
        except Exception as e:
            raise UserError(error_msg % (self.name, cuit, e))

        if not padron.denominacion or padron.denominacion == ', ':
            raise UserError(error_msg % (
                self.name, cuit, 'La afip no devolvió nombre'))

        # porque imp_iva activo puede ser S o AC
        imp_iva = padron.imp_iva
        if imp_iva == 'S':
            imp_iva = 'AC'
        elif imp_iva == 'N':
            # por ej. monotributista devuelve N
            imp_iva = 'NI'
        
        vals = {
            'name': padron.denominacion,
            'estado_padron': padron.estado,
            'street': padron.direccion,
            'city': padron.localidad,
            'zip': padron.cod_postal,
            'actividades_padron': self.actividades_padron.search(
                [('code', 'in', padron.actividades)]).ids,
            'impuestos_padron': self.impuestos_padron.search(
                [('code', 'in', padron.impuestos)]).ids,
            'imp_iva_padron': imp_iva,
            'monotributo_padron': padron.monotributo,
            'actividad_monotributo_padron': padron.actividad_monotributo,
            'empleador_padron': padron.empleador == 'S' and True,
            'integrante_soc_padron': padron.integrante_soc,
            'last_update_padron': fields.Date.today(),
        }
        ganancias_inscripto = [10, 11]
        ganancias_exento = [12]
        if set(ganancias_inscripto) & set(padron.impuestos):
            vals['imp_ganancias_padron'] = 'AC'
        elif set(ganancias_exento) & set(padron.impuestos):
            vals['imp_ganancias_padron'] = 'EX'
        elif padron.monotributo == 'S':
            vals['imp_ganancias_padron'] = 'NC'
        else:
            _logger.info(
                "We couldn't get impuesto a las ganancias from padron, you"
                "must set it manually")

        if padron.provincia:
            # depending on the database, caba can have one of this codes
            caba_codes = ['C', 'CABA', 'ABA']
            # if not localidad then it should be CABA.
            if not padron.localidad:
                state = self.env['res.country.state'].search([
                    ('code', 'in', caba_codes),
                    ('country_id.code', '=', 'AR')], limit=1)
            # If localidad cant be caba
            else:
                state = self.env['res.country.state'].search([
                    ('name', 'ilike', padron.provincia),
                    ('code', 'not in', caba_codes),
                    ('country_id.code', '=', 'AR')], limit=1)
            if state:
                vals['state_id'] = state.id

        if imp_iva == 'NI' and padron.monotributo == 'S':
            vals['l10n_ar_afip_responsibility_type_id'] = self.env.ref(
                'l10n_ar.res_RM').id
        elif imp_iva == 'AC':
            vals['l10n_ar_afip_responsibility_type_id'] = self.env.ref(
                'l10n_ar.res_IVARI').id
        elif imp_iva == 'EX':
            vals['l10n_ar_afip_responsibility_type_id'] = self.env.ref(
                'l10n_ar.res_IVAE').id
        else:
            _logger.info(
                "We couldn't infer the AFIP responsability from padron, you"
                "must set it manually.")

        return vals