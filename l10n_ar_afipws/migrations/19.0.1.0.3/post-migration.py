##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migración para agregar campos de validación AFIP a certificados existentes."""

    _logger.info("=== Iniciando migración 19.0.1.0.3 ===")

    # 1. Agregar valores por defecto para nuevos campos
    _logger.info("Estableciendo valores por defecto para certificados existentes...")

    cr.execute("""
        UPDATE afipws_certificate
        SET
            afip_services = 'wsfe
wsfex',
            certificate_validated = FALSE,
            validation_date = NULL,
            validation_error = NULL
        WHERE afip_services IS NULL
    """)

    affected_rows = cr.rowcount
    _logger.info("✓ %s certificados actualizados con valores por defecto", affected_rows)

    # 2. Intentar validar certificados confirmados automáticamente
    _logger.info("Intentando validar certificados confirmados existentes...")

    try:
        # Usar el ORM para validar certificados
        from odoo import SUPERUSER_ID, api

        env = api.Environment(cr, SUPERUSER_ID, {})
        certificates = env["afipws.certificate"].search(
            [
                ("state", "=", "confirmed"),
                ("crt", "!=", False),
            ]
        )

        _logger.info("Encontrados %s certificados confirmados para validar", len(certificates))

        validated_count = 0
        failed_count = 0

        for cert in certificates:
            try:
                _logger.info("Validando certificado ID %s (%s)...", cert.id, cert.alias_id.common_name)
                success, msg = cert.test_wsaa_authentication()

                if success:
                    validated_count += 1
                    _logger.info("✓ Certificado %s validado exitosamente", cert.id)
                else:
                    failed_count += 1
                    _logger.warning("⚠ Certificado %s falló validación: %s", cert.id, msg[:200])

            except Exception as e:
                failed_count += 1
                _logger.error("Error validando certificado %s: %s", cert.id, str(e))

        _logger.info(
            "Validación completada: %s exitosos, %s fallidos de %s totales",
            validated_count,
            failed_count,
            len(certificates),
        )

    except Exception as e:
        _logger.warning("No se pudo validar certificados automáticamente (esto es opcional): %s", str(e))

    _logger.info("=== Migración 19.0.1.0.3 completada ===")
