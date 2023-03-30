from odoo import models, api, fields, _
from ast import literal_eval
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class UpdateFromPadronWizard(models.TransientModel):
    _inherit = "res.partner.update.from.padron.wizard"

    @api.model
    def _get_domain(self):
        domain = super()._get_domain()
        # Modifico la tupla que tenga el "name" como campo
        for t in domain:
            if t[0] == 'name':
                t[2].extend([
                    'actividades_padron',
                    'impuestos_padron',
                    'monotributo_padron',
                    'actividad_monotributo_padron',
                    'empleador_padron',
                    'integrante_soc_padron',
                    'estado_padron',
                    'imp_ganancias_padron',
                ])
        return domain