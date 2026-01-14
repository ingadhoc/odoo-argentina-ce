##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Recalcular información de certificados existentes.

    Los campos cert_valid_from, cert_valid_to, cert_days_to_expire, etc.
    ahora tienen store=True, por lo que necesitamos recalcularlos para
    certificados existentes que tengan contenido CRT.
    """
    _logger.info("Iniciando migración 19.0.1.0.2: Recalculando información de certificados")

    # Obtener todos los certificados que tengan contenido CRT
    cr.execute("""
        SELECT id
        FROM afipws_certificate
        WHERE crt IS NOT NULL AND crt != ''
    """)

    certificate_ids = [row[0] for row in cr.fetchall()]

    if not certificate_ids:
        _logger.info("No hay certificados con contenido CRT para procesar")
        return

    _logger.info(f"Encontrados {len(certificate_ids)} certificados para recalcular")

    # Usar el ORM para recalcular (esto disparará el compute)
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    certificates = env["afipws.certificate"].browse(certificate_ids)

    # Forzar el recálculo de los campos compute
    certificates._compute_cert_info()

    _logger.info("Migración 19.0.1.0.2 completada: %s certificados actualizados", len(certificate_ids))
