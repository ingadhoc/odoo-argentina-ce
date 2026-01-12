##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migración post: Eliminar el campo company_cuit y recalcular el campo cuit
    desde company_id.partner_id.vat.

    El campo cuit ahora se calcula automáticamente, por lo que no hay datos
    que migrar. Solo necesitamos asegurarnos de que las constraints se cumplan.
    """
    _logger.info("Starting post-migration for l10n_ar_afipws 19.0.1.0.1")

    # Verificar certificados alias con servicio in_house sin CUIT en la compañía
    cr.execute("""
        SELECT ca.id, ca.common_name, c.name as company_name
        FROM afipws_certificate_alias ca
        INNER JOIN res_company c ON ca.company_id = c.id
        INNER JOIN res_partner p ON c.partner_id = p.id
        WHERE ca.service_type = 'in_house'
          AND (p.vat IS NULL OR p.vat = '')
    """)

    aliases_sin_cuit = cr.fetchall()

    if aliases_sin_cuit:
        _logger.warning(
            "Se encontraron %s certificados alias con servicio 'in_house' "
            "cuyas compañías no tienen CUIT configurado. "
            "Estos certificados NO podrán ser confirmados hasta que se configure "
            "el CUIT en la compañía correspondiente.",
            len(aliases_sin_cuit),
        )
        for alias_id, alias_name, company_name in aliases_sin_cuit:
            _logger.warning("  - Alias ID %s ('%s') - Compañía: %s", alias_id, alias_name, company_name)
    else:
        _logger.info("Todos los certificados alias tienen CUIT configurado correctamente.")

    # Recomputar el campo cuit para todos los registros
    # Esto se hace automáticamente por Odoo al cargar el módulo con store=True
    _logger.info("El campo 'cuit' se recalculará automáticamente para todos los registros.")
    _logger.info("Post-migration for l10n_ar_afipws 19.0.1.0.1 completed successfully")
