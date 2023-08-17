
# Debemos borrar todas las coneciones porque algunas tienen referencia al viejo
# webserver consulta_padron_a5 y falla
import logging
_logger = logging.getLogger(__name__)

def migrate(cr, version):
    _logger.info('MIG l10n_ar_afipws -> Eliminando conexiones afip viejas')
    cr.execute("delete from afipws_connection;")
