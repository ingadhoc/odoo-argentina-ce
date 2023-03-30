from odoo import fields, models, api, _
import logging
_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def parce_census_vals(self, census):
        vals = super().parce_census_vals(census)

        vals.update({
            'actividades_padron': self.actividades_padron.search([('code', 'in', census.actividades)]).ids,
            'impuestos_padron': self.impuestos_padron.search([('code', 'in', census.impuestos)]).ids,
            'monotributo_padron': census.monotributo,
            'actividad_monotributo_padron': census.actividad_monotributo,
            'empleador_padron': census.empleador == 'S' and True,
            'integrante_soc_padron': census.integrante_soc,
            'estado_padron': census.estado,
        })
        # Ganancias
        ganancias_inscripto = [10, 11]
        ganancias_exento = [12]
        if set(ganancias_inscripto) & set(census.impuestos):
            vals['imp_ganancias_padron'] = 'AC'
        elif set(ganancias_exento) & set(census.impuestos):
            vals['imp_ganancias_padron'] = 'EX'
        elif census.monotributo == 'S':
            vals['imp_ganancias_padron'] = 'NC'
        else:
            _logger.info(
                "We couldn't get impuesto a las ganancias from padron, you"
                "must set it manually")
        return vals
