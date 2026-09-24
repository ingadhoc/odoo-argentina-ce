"""Post-migración de l10n_ar_fiscal_ws 19.0.1.0.0

Conserva la cola de facturas que esperaban validarse en segundo plano. El módulo viejo
tenía su propio campo con su cron; eso ahora lo hace account_background_post. Si ese
módulo está instalado, la marca se pasa a su campo; si no, la cola se pierde y se avisa.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    if not _column_exists(cr, "account_move", "asynchronous_post"):
        return

    if openupgrade.is_module_installed(cr, "account_background_post"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE account_move
               SET background_post = TRUE
             WHERE asynchronous_post IS TRUE
               AND background_post IS NOT TRUE
            """,
        )
        _logger.info("Facturas que conservan la validación en segundo plano: %s", cr.rowcount)
    else:
        cr.execute("SELECT count(*) FROM account_move WHERE asynchronous_post IS TRUE")
        pending = cr.fetchone()[0]
        if pending:
            _logger.warning(
                "Quedaron %s facturas marcadas para validarse en segundo plano y "
                "account_background_post no está instalado: hay que validarlas a mano",
                pending,
            )

    openupgrade.drop_columns(cr, [("account_move", "asynchronous_post")])

    _recompute_journal_service(env)


def _recompute_journal_service(env):
    """Vuelve a calcular el servicio fiscal de cada diario.

    El campo es un computado almacenado que solo depende del sistema de punto de venta,
    y ese no cambia en la migración: sin este paso los diarios quedan sin servicio y las
    facturas se asientan sin pedir el CAE, en silencio.
    """
    journals = env["account.journal"].search([("l10n_ar_afip_pos_system", "!=", False)])
    journals.invalidate_recordset(["l10n_ar_fiscal_ws_id"])
    journals._compute_l10n_ar_fiscal_ws_id()
    journals.flush_recordset(["l10n_ar_fiscal_ws_id"])
    _logger.info("Diarios con servicio fiscal: %s", len(journals.filtered("l10n_ar_fiscal_ws_id")))
