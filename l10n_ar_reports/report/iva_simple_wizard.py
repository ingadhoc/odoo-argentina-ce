##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/wizards/iva_simple_wizard.py
# (LGPL-3).
"""Wizard: generar los 4 CSV del régimen IVA Simple en un ZIP.

UX:
    - Menú: Contabilidad → Informes → Declaraciones Argentina → IVA Simple.
    - Período (date_from / date_to) + Actividad ARCA (default '0').
    - Botón "Generar ZIP" → 4 archivos.

Queries SQL planos sobre `account_move_line` agrupados por
``(actividad, op_type, sujeto, vat_code)`` para Ventas y por
``(concepto, vat_code)`` para Compras. Inspirado (no copiado) en
``odoo/enterprise/l10n_ar_reports_simple/models/l10n_ar_vat_book.py``.
"""
import base64
import io
import logging
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import iva_simple_csv as fmt
from . import iva_simple_spec as spec

_logger = logging.getLogger(__name__)


class IvaSimpleWizard(models.TransientModel):
    _name = "l10n_ar.iva.simple.wizard"
    _description = "IVA Simple — generar 4 CSV (régimen ARCA)"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
        help="Primer día del período. Recomendado: día 1 del mes.",
    )
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.today(),
        help="Último día del período.",
    )
    activity_id = fields.Many2one(
        "l10n_ar.arca.activity",
        string="Actividad ARCA (override)",
        help=(
            "Actividad ARCA a usar como fallback global. Cadena de prioridad:\n"
            "  1. Cuenta contable de la línea (account.l10n_ar_arca_activity_id)\n"
            "  2. Default de la empresa (company.l10n_ar_arca_activity_id)\n"
            "  3. Este campo del wizard\n"
            "Si nada matchea, se usa '0' (sin clasificar)."
        ),
        default=lambda self: self.env.company.l10n_ar_arca_activity_id,
    )
    # Compatibilidad: campo computado para mostrar el código en el CSV.
    activity = fields.Char(
        compute="_compute_activity_code",
        store=False,
    )

    @api.depends("activity_id")
    def _compute_activity_code(self):
        for rec in self:
            rec.activity = (rec.activity_id.code or "0")[:3] if rec.activity_id else "0"

    # Salida.
    file_name = fields.Char(readonly=True)
    file_content = fields.Binary(readonly=True, attachment=False)
    state = fields.Selection(
        [("draft", "Configurar"), ("done", "Listo")],
        default="draft",
    )

    # ------------------------------------------------------------------
    # Botón
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("El 'Desde' debe ser anterior o igual al 'Hasta'."))

        files = self._build_csv_files()
        if not files:
            raise UserError(_(
                "No se encontraron comprobantes posted con IVA para "
                "%(c)s entre %(d1)s y %(d2)s.",
                c=self.company_id.name,
                d1=self.date_from, d2=self.date_to,
            ))

        # Empaquetar ZIP.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, content in files.items():
                zf.writestr(fname, content)
        buf.seek(0)

        period = self.date_from.strftime("%Y%m")
        self.write({
            "file_name": "iva_simple_%s_%s.zip" % (period, self.company_id.id),
            "file_content": base64.b64encode(buf.getvalue()),
            "state": "done",
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": self.env.context,
        }

    # ------------------------------------------------------------------
    # Construcción de los 4 CSV
    # ------------------------------------------------------------------
    def _build_csv_files(self):
        period_str = self.date_to.strftime("%Y%m%d")
        files = {}

        sale_invoice_rows = self._build_sale_rows("out_invoice")
        if sale_invoice_rows:
            files["DEBITO_%s.csv" % period_str] = fmt.rows_to_csv_bytes(
                spec.HEADERS_DEBITO, sale_invoice_rows,
            )

        sale_refund_rows = self._build_sale_rows("out_refund")
        if sale_refund_rows:
            files["REST_DEBITO_%s.csv" % period_str] = fmt.rows_to_csv_bytes(
                spec.HEADERS_REST_DEBITO, sale_refund_rows,
            )

        purchase_invoice_rows = self._build_purchase_rows("in_invoice")
        if purchase_invoice_rows:
            files["CREDITO_%s.csv" % period_str] = fmt.rows_to_csv_bytes(
                spec.HEADERS_CREDITO, purchase_invoice_rows,
            )

        purchase_refund_rows = self._build_purchase_rows("in_refund")
        if purchase_refund_rows:
            files["REST_CREDITO_%s.csv" % period_str] = fmt.rows_to_csv_bytes(
                spec.HEADERS_REST_CREDITO, purchase_refund_rows,
            )

        _logger.info(
            "IVA Simple generado para %s [%s..%s]: "
            "ventas inv=%d ref=%d, compras inv=%d ref=%d",
            self.company_id.name, self.date_from, self.date_to,
            len(sale_invoice_rows), len(sale_refund_rows),
            len(purchase_invoice_rows), len(purchase_refund_rows),
        )
        return files

    # ------------------------------------------------------------------
    # Ventas
    # ------------------------------------------------------------------
    def _build_sale_rows(self, move_type):
        """Devuelve lista de dicts ya con los headers del CSV de Ventas.

        ``move_type`` ∈ {'out_invoice', 'out_refund'}. Para refund se
        omiten columnas que no aplican.
        """
        is_refund = move_type == "out_refund"
        fixed_asset_tag_id = self._get_tag_id("fixed_asset")

        # Query agrupado por (account_activity, op_type, sujeto, vat_code).
        # base_lines = aml NO tax_line, con vat_afip_code IN ('0'..'9') via tax_group.
        # account_activity_code: 3 dígitos de la actividad ARCA asignada a la cuenta
        # contable (account.account.l10n_ar_arca_activity_id) — si no, NULL → cae al
        # fallback Python (company → wizard → '0').
        sql = """
            WITH base_lines AS (
                SELECT
                    aml.id, aml.move_id, aml.balance, aml.account_id,
                    am.partner_id,
                    rprt.code AS partner_resp_code,
                    btg.l10n_ar_vat_afip_code AS vat_code,
                    LEFT(acc_act.code, 3) AS account_activity_code,
                    EXISTS(
                        SELECT 1 FROM account_account_account_tag aaat
                        WHERE aaat.account_account_id = aml.account_id
                          AND aaat.account_account_tag_id = %(fa_tag_id)s
                    ) AS is_fixed_asset
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                LEFT JOIN account_account acc ON acc.id = aml.account_id
                LEFT JOIN l10n_ar_arca_activity acc_act
                    ON acc_act.id = acc.l10n_ar_arca_activity_id
                LEFT JOIN res_partner rp ON rp.id = am.commercial_partner_id
                LEFT JOIN l10n_ar_afip_responsibility_type rprt
                    ON rprt.id = rp.l10n_ar_afip_responsibility_type_id
                LEFT JOIN account_journal aj ON aj.id = am.journal_id
                LEFT JOIN account_move_line_account_tax_rel amltr
                    ON amltr.account_move_line_id = aml.id
                LEFT JOIN account_tax bt ON bt.id = amltr.account_tax_id
                LEFT JOIN account_tax_group btg ON btg.id = bt.tax_group_id
                WHERE
                    am.state = 'posted'
                    AND am.company_id = %(company_id)s
                    AND am.invoice_date BETWEEN %(date_from)s AND %(date_to)s
                    AND am.move_type = %(move_type)s
                    AND aj.l10n_latam_use_documents = TRUE
                    AND aml.tax_line_id IS NULL
                    AND btg.l10n_ar_vat_afip_code IS NOT NULL
                    AND btg.l10n_ar_vat_afip_code IN ('0','1','2','3','4','5','6','8','9')
            )
            SELECT
                vat_code,
                partner_resp_code,
                account_activity_code,
                BOOL_OR(is_fixed_asset) AS is_fixed_asset_grp,
                SUM(ABS(balance)) AS net_amount
            FROM base_lines
            GROUP BY vat_code, partner_resp_code, account_activity_code
            ORDER BY account_activity_code NULLS LAST, vat_code, partner_resp_code
        """
        self.env.cr.execute(sql, {
            "fa_tag_id": fixed_asset_tag_id,
            "company_id": self.company_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "move_type": move_type,
        })
        rows = []
        for r in self.env.cr.dictfetchall():
            vat_code = r["vat_code"]
            net = r["net_amount"] or 0.0
            op_type = spec.map_sale_operation_type(vat_code, r["is_fixed_asset_grp"])
            is_exempt = (op_type == spec.OP_TYPE_EXENTA)
            buyer = "" if is_exempt else spec.map_responsibility_to_buyer_type(r["partner_resp_code"])
            # Cadena de fallback: cuenta contable → company default → wizard
            activity_code = r.get("account_activity_code") or self._fallback_activity_code()

            if is_refund:
                rows.append({
                    "Actividad": activity_code,
                    "Tipo de Operacion": op_type,
                    "Codigo de Alicuota": "" if is_exempt else vat_code,
                    "Monto Neto Gravado": "" if is_exempt else net,
                    "Debito Fiscal a Restituir": "" if is_exempt else spec.vat_amount(net, vat_code),
                    "Monto Neto Exento o No Gravado": net if is_exempt else "",
                })
            else:
                rows.append({
                    "Actividad": activity_code,
                    "Tipo de Operacion": op_type,
                    "Tipo de sujeto comprador": buyer,
                    "Codigo de Alicuota": "" if is_exempt else vat_code,
                    "Monto Neto Gravado": "" if is_exempt else net,
                    "Debito Fiscal Facturado": "" if is_exempt else spec.vat_amount(net, vat_code),
                    "Debito Fiscal O.D.P.": "" if is_exempt else spec.vat_amount(net, vat_code),
                    "Monto Neto Exento o No Gravado": net if is_exempt else "",
                })
        return rows

    def _fallback_activity_code(self):
        """Devuelve el código de actividad ARCA con la cadena de fallback:
        wizard.activity_id → company.l10n_ar_arca_activity_id → '0'."""
        if self.activity_id and self.activity_id.code:
            return self.activity_id.code[:3]
        company_act = self.company_id.l10n_ar_arca_activity_id
        if company_act and company_act.code:
            return company_act.code[:3]
        return "0"

    # ------------------------------------------------------------------
    # Compras
    # ------------------------------------------------------------------
    def _build_purchase_rows(self, move_type):
        """Devuelve lista de dicts ya con los headers del CSV de Compras."""
        is_refund = move_type == "in_refund"
        fixed_asset_tag_id = self._get_tag_id("fixed_asset")
        leases_tag_id = self._get_tag_id("leases")

        sql = """
            WITH base_lines AS (
                SELECT
                    aml.id, aml.move_id, aml.balance, aml.account_id,
                    aml.product_id,
                    pt.type AS product_type,
                    btg.l10n_ar_vat_afip_code AS vat_code,
                    EXISTS(
                        SELECT 1 FROM account_account_account_tag aaat
                        WHERE aaat.account_account_id = aml.account_id
                          AND aaat.account_account_tag_id = %(fa_tag_id)s
                    ) AS is_fixed_asset,
                    EXISTS(
                        SELECT 1 FROM account_account_account_tag aaat
                        WHERE aaat.account_account_id = aml.account_id
                          AND aaat.account_account_tag_id = %(leases_tag_id)s
                    ) AS is_leases
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                LEFT JOIN account_journal aj ON aj.id = am.journal_id
                LEFT JOIN account_move_line_account_tax_rel amltr
                    ON amltr.account_move_line_id = aml.id
                LEFT JOIN account_tax bt ON bt.id = amltr.account_tax_id
                LEFT JOIN account_tax_group btg ON btg.id = bt.tax_group_id
                LEFT JOIN product_product pp ON pp.id = aml.product_id
                LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE
                    am.state = 'posted'
                    AND am.company_id = %(company_id)s
                    AND am.invoice_date BETWEEN %(date_from)s AND %(date_to)s
                    AND am.move_type = %(move_type)s
                    AND aj.l10n_latam_use_documents = TRUE
                    AND aml.tax_line_id IS NULL
                    AND btg.l10n_ar_vat_afip_code IS NOT NULL
                    AND btg.l10n_ar_vat_afip_code IN ('3','4','5','6','8','9')
            )
            SELECT
                vat_code,
                product_type,
                BOOL_OR(is_fixed_asset) AS is_fixed_asset_grp,
                BOOL_OR(is_leases)      AS is_leases_grp,
                SUM(ABS(balance)) AS net_amount
            FROM base_lines
            GROUP BY vat_code, product_type
            ORDER BY vat_code, product_type
        """
        self.env.cr.execute(sql, {
            "fa_tag_id": fixed_asset_tag_id,
            "leases_tag_id": leases_tag_id,
            "company_id": self.company_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "move_type": move_type,
        })
        rows = []
        for r in self.env.cr.dictfetchall():
            vat_code = r["vat_code"]
            net = r["net_amount"] or 0.0
            concept = spec.map_purchase_concept(
                r["product_type"], r["is_fixed_asset_grp"], r["is_leases_grp"]
            )
            vat = spec.vat_amount(net, vat_code)
            row = {
                "Concepto": concept,
                "Codigo de Alicuota": vat_code,
                "Monto Neto Gravado": net,
                "Credito Fiscal Facturado": vat,
            }
            if not is_refund:
                row["Credito Fiscal Computable"] = vat
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_tag_id(self, kind):
        """Devuelve el id del tag (fixed_asset|leases) o 0 si no existe."""
        xmlid = {
            "fixed_asset": "l10n_ar_reports.tag_fixed_asset_account",
            "leases": "l10n_ar_reports.tag_leases_rentals_account",
        }[kind]
        tag = self.env.ref(xmlid, raise_if_not_found=False)
        return tag.id if tag else 0
