"""Pre-migración de l10n_ar_fiscal_ws 19.0.1.0.0

Qué supone:
  - El renombre de los módulos ya se hizo a mano (ver MIGRATION.md en la raíz del
    repositorio): la base tiene l10n_ar_fiscal_ws instalado con la versión vieja, con
    l10n_ar_afipws_fe ya fusionado adentro.

Qué garantiza al terminar:
  - Los modelos y los campos de la versión vieja quedan con los nombres nuevos, con sus
    datos: la clave privada y el certificado firmado viajan con la tabla, y las facturas
    conservan su CAE, su vencimiento y el XML intercambiado.
  - No queda ningún ticket de acceso viejo: el modelo cambió de forma y los tickets
    duran doce horas, así que se piden de nuevo.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

_model_renames = [
    ("afipws.certificate", "l10n_ar.fiscal.certificate"),
    ("afipws.certificate_alias", "l10n_ar.fiscal.certificate.alias"),
]

_table_renames = [
    ("afipws_certificate", "l10n_ar_fiscal_certificate"),
    ("afipws_certificate_alias", "l10n_ar_fiscal_certificate_alias"),
]

# (modelo, tabla, nombre viejo, nombre nuevo). Solo los campos que tienen columna: los
# computados sin almacenar los rehace el registro al cargar el módulo.
_field_renames = [
    ("account.move", "account_move", "afip_auth_mode", "l10n_ar_fiscal_auth_mode"),
    ("account.move", "account_move", "afip_auth_code", "l10n_ar_fiscal_auth_code"),
    ("account.move", "account_move", "afip_auth_code_due", "l10n_ar_fiscal_auth_code_due"),
    ("account.move", "account_move", "afip_result", "l10n_ar_fiscal_result"),
    ("account.move", "account_move", "afip_message", "l10n_ar_fiscal_message"),
    ("account.move", "account_move", "afip_xml_request", "l10n_ar_fiscal_xml_request"),
    ("account.move", "account_move", "afip_xml_response", "l10n_ar_fiscal_xml_response"),
    ("account.move", "account_move", "afip_associated_period_from", "l10n_ar_fiscal_period_from"),
    ("account.move", "account_move", "afip_associated_period_to", "l10n_ar_fiscal_period_to"),
    ("account.move", "account_move", "afip_fce_es_anulacion", "l10n_ar_fiscal_fce_is_cancellation"),
    (
        "account.move",
        "account_move",
        "l10n_ar_payment_foreign_currency",
        "l10n_ar_fiscal_payment_foreign_currency",
    ),
    (
        "res.company",
        "res_company",
        "l10n_ar_payment_foreign_currency",
        "l10n_ar_fiscal_payment_foreign_currency",
    ),
]

# Relaciones inversas: no tienen columna, pero sí metadatos que conviene dejar al día.
_o2m_renames = [
    ("res.company", "res_company", "alias_ids", "l10n_ar_fiscal_alias_ids"),
    ("res.company", "res_company", "connection_ids", "l10n_ar_fiscal_connection_ids"),
]


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    _logger.info("Renombrando modelos y campos de la facturación electrónica argentina")

    openupgrade.rename_models(cr, _model_renames)
    openupgrade.rename_tables(cr, _table_renames)
    openupgrade.rename_fields(env, _field_renames + _o2m_renames)

    # El servicio dejó de ser una selección para pasar a ser un registro, así que los
    # tickets viejos no tienen a dónde apuntar. Duran doce horas: se piden de nuevo.
    openupgrade.logged_query(cr, "DROP TABLE IF EXISTS afipws_connection CASCADE")
    openupgrade.logged_query(cr, "DELETE FROM ir_model WHERE model = 'afipws.connection'")
