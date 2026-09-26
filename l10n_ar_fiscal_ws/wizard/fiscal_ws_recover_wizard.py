##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# VAT codes of the authority for what is not taxed and for what is exempt: the
# service reports those two apart from the aliquots
NOT_TAXED_CODE = "1"
EXEMPT_CODE = "2"
LOCAL_CURRENCY_CODE = "PES"


class L10nArFiscalWsRecover(models.TransientModel):
    _name = "l10n_ar.fiscal.ws.recover"
    _description = "Recuperar comprobantes autorizados por el servicio"

    journal_id = fields.Many2one(
        "account.journal",
        string="Diario",
        required=True,
        domain="[('l10n_ar_fiscal_ws_id', '!=', False)]",
    )
    company_id = fields.Many2one(related="journal_id.company_id")
    currency_id = fields.Many2one(related="company_id.currency_id")
    document_type_id = fields.Many2one(
        "l10n_latam.document.type",
        string="Tipo de comprobante",
        required=True,
        domain="[('id', 'in', available_document_type_ids)]",
    )
    available_document_type_ids = fields.Many2many(
        "l10n_latam.document.type",
        compute="_compute_available_document_type_ids",
    )
    number_from = fields.Integer("Desde el número", required=True)
    number_to = fields.Integer("Hasta el número", required=True)
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta de los comprobantes que se crean",
        check_company=True,
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Cuenta de la única línea de los comprobantes que el asistente crea. No hace falta "
        "un producto: el comprobante ya existe en el organismo y lo que se registra es su importe.",
    )
    line_ids = fields.One2many("l10n_ar.fiscal.ws.recover.line", "wizard_id")
    state = fields.Selection(
        [("setup", "Qué buscar"), ("review", "Qué hacer con cada uno")],
        default="setup",
        required=True,
    )

    @api.depends("journal_id")
    def _compute_available_document_type_ids(self):
        """Los tipos que este diario puede emitir, según su sistema de punto de venta
        y la responsabilidad de la compañía."""
        for wizard in self:
            journal = wizard.journal_id
            if not journal.l10n_ar_fiscal_ws_id:
                wizard.available_document_type_ids = False
                continue
            wizard.available_document_type_ids = self.env["l10n_latam.document.type"].search(
                journal._get_journal_codes_domain()
                + [
                    ("country_id.code", "=", "AR"),
                    ("l10n_ar_letter", "in", journal._get_journal_letter()),
                    ("internal_type", "in", ("invoice", "debit_note", "credit_note")),
                ]
            )

    @api.onchange("journal_id", "document_type_id")
    def _onchange_proposed_range(self):
        """El hueco entre lo último que tiene Odoo y lo último que autorizó el servicio."""
        for wizard in self.filtered(lambda w: w.journal_id and w.document_type_id):
            wizard.number_from, wizard.number_to = wizard._l10n_ar_proposed_range()

    def _l10n_ar_proposed_range(self):
        self.ensure_one()
        last_here = self._l10n_ar_last_number_here()
        last_there = self.journal_id._l10n_ar_get_last_invoice_number(self.document_type_id)
        return last_here + 1, max(last_there, last_here)

    def _l10n_ar_last_number_here(self):
        """Último número que este diario ya tiene registrado, autorizado o no."""
        self.ensure_one()
        last = self.env["account.move"].search(
            [
                ("journal_id", "=", self.journal_id.id),
                ("l10n_latam_document_type_id", "=", self.document_type_id.id),
                ("name", "!=", "/"),
            ],
            order="name desc",
            limit=1,
        )
        if not last:
            return 0
        parts = last._l10n_ar_get_document_number_parts(last.l10n_latam_document_number, self.document_type_id.code)
        return int(parts["invoice_number"])

    # ------------------------------------------------------------------ traer

    def action_fetch(self):
        """Preguntarle al servicio por cada número del rango y proponer qué hacer."""
        self.ensure_one()
        self._l10n_ar_check_range()
        self.line_ids.unlink()
        values_list = []
        taken = self.env["account.move"]
        for number in range(self.number_from, self.number_to + 1):
            answer = self.journal_id._l10n_ar_get_invoice(self.document_type_id, number)
            if not answer:
                continue
            values = self._l10n_ar_prepare_line(answer, taken)
            taken |= self.env["account.move"].browse(values["move_id"] or [])
            values_list.append(values)
        if not values_list:
            raise UserError(
                _(
                    "El servicio no tiene ningún comprobante autorizado entre el %(start)s y el %(end)s.",
                    start=self.number_from,
                    end=self.number_to,
                )
            )
        self.write({"state": "review", "line_ids": [Command.create(values) for values in values_list]})
        return self._l10n_ar_reopen()

    def _l10n_ar_check_range(self):
        self.ensure_one()
        if self.number_to < self.number_from:
            raise UserError(_("El número final no puede ser menor que el inicial."))
        limit = int(self.env["ir.config_parameter"].sudo().get_param("l10n_ar_fiscal_ws.recover_limit", 100))
        size = self.number_to - self.number_from + 1
        if size > limit:
            raise UserError(
                _(
                    "El rango son %(size)s comprobantes y cada uno es una consulta al servicio. "
                    "Buscá de a %(limit)s o menos, o subí el parámetro l10n_ar_fiscal_ws.recover_limit.",
                    size=size,
                    limit=limit,
                )
            )

    def _l10n_ar_prepare_line(self, answer, taken):
        """Una línea por comprobante que el servicio informó, con lo que se propone hacer."""
        self.ensure_one()
        values = {
            "number": answer["number"],
            "date": answer.get("date"),
            "amount_total": float(answer.get("total") or 0),
            "document_number": answer.get("document_number") or "",
            "auth_mode": answer.get("auth_mode"),
            "auth_code": answer.get("auth_code"),
            "auth_code_due": answer.get("auth_code_due"),
            "values": self._l10n_ar_serialize(answer),
            "move_id": False,
            "action": "skip",
            "note": "",
        }
        existing = self._l10n_ar_find_registered(answer["number"])
        if existing:
            values["note"] = _("Ya está en Odoo como %s.", existing.display_name)
            return values

        partner = self._l10n_ar_find_partner(answer)
        values["partner_id"] = partner.id
        draft = self._l10n_ar_find_draft(answer, partner, taken)
        if draft:
            values.update({"move_id": draft.id, "action": "match"})
            return values
        blocker = self._l10n_ar_create_blocker(answer, partner)
        if blocker:
            values["note"] = blocker
            return values
        values["action"] = "create"
        return values

    @api.model
    def _l10n_ar_serialize(self, answer):
        """Lo que contestó el servicio, en tipos que entran en un campo json."""
        return {
            "total": float(answer.get("total") or 0),
            "not_taxed": float(answer.get("not_taxed") or 0),
            "exempt": float(answer.get("exempt") or 0),
            "tributes_amount": float(answer.get("tributes_amount") or 0),
            "currency_code": answer.get("currency_code") or LOCAL_CURRENCY_CODE,
            "result": answer.get("result"),
            "vat_items": [
                {
                    "code": str(item.Id),
                    "base": float(item.BaseImp or 0),
                    "amount": float(item.Importe or 0),
                }
                for item in (answer.get("vat_items") or [])
            ],
        }

    def _l10n_ar_find_registered(self, number):
        """El comprobante que Odoo ya tiene con ese número, si lo tiene."""
        self.ensure_one()
        formatted = self._l10n_ar_format_number(number)
        return self.env["account.move"].search(
            [
                ("journal_id", "=", self.journal_id.id),
                ("l10n_latam_document_type_id", "=", self.document_type_id.id),
                ("name", "=", "%s %s" % (self.document_type_id.doc_code_prefix, formatted)),
            ],
            limit=1,
        )

    def _l10n_ar_find_partner(self, answer):
        """El cliente que informó el servicio, buscado por su identificación.

        Un consumidor final anónimo no trae un número utilizable: esos van al contacto
        que crea la localización para ellos.
        """
        self.ensure_one()
        number = (answer.get("document_number") or "").strip()
        code = answer.get("document_code")
        if not number or number == "0":
            return self.env.ref("l10n_ar.par_cfa", raise_if_not_found=False) or self.env["res.partner"]
        candidates = [number]
        if len(number) == 11:
            candidates.append("%s-%s-%s" % (number[:2], number[2:10], number[10:]))
        return self.env["res.partner"].search(
            [
                ("vat", "in", candidates),
                ("l10n_latam_identification_type_id.l10n_ar_afip_code", "=", code),
                ("company_id", "in", (False, self.company_id.id)),
            ],
            limit=1,
        )

    def _l10n_ar_find_draft(self, answer, partner, taken):
        """El borrador que podría ser el que el servicio autorizó: mismo cliente y mismo total."""
        self.ensure_one()
        if not partner:
            return self.env["account.move"]
        candidates = self.env["account.move"].search(
            [
                ("journal_id", "=", self.journal_id.id),
                ("l10n_latam_document_type_id", "=", self.document_type_id.id),
                ("state", "=", "draft"),
                ("l10n_ar_fiscal_auth_code", "=", False),
                ("commercial_partner_id", "=", partner.id),
                ("id", "not in", taken.ids),
            ],
            order="invoice_date, id",
        )
        total = float(answer.get("total") or 0)
        return candidates.filtered(lambda m: not m.currency_id.compare_amounts(m.amount_total, total))[:1]

    def _l10n_ar_create_blocker(self, answer, partner):
        """Por qué este comprobante no se puede crear, cuando no se puede."""
        self.ensure_one()
        if not partner:
            return _("No hay ningún contacto con la identificación %s.", answer.get("document_number"))
        if (answer.get("currency_code") or LOCAL_CURRENCY_CODE) != LOCAL_CURRENCY_CODE:
            return _(
                "Está en moneda extranjera (%s): se puede asignar a un borrador, pero no crear.",
                answer.get("currency_code"),
            )
        if float(answer.get("tributes_amount") or 0):
            return _("Lleva otros tributos por %s, que hay que armar a mano.", answer.get("tributes_amount"))
        return ""

    # ----------------------------------------------------------------- aplicar

    def action_apply(self):
        """Asignar y crear lo que quedó marcado, del número más chico al más grande."""
        self.ensure_one()
        to_create = self.line_ids.filtered(lambda line: line.action == "create")
        if to_create and not self.account_id:
            raise UserError(_("Elegí la cuenta contable de los comprobantes que se van a crear."))
        done = self.env["account.move"]
        for line in self.line_ids.filtered(lambda line: line.action != "skip").sorted("number"):
            done |= line._l10n_ar_apply()
        if not done:
            raise UserError(_("No quedó ningún comprobante marcado para asignar ni para crear."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Comprobantes recuperados"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", done.ids)],
        }

    def _l10n_ar_sale_taxes_by_vat_code(self):
        """Un impuesto de venta por cada código de IVA del organismo.

        Cuando la compañía tiene más de uno con el mismo código se toma el primero; si
        no es el que corresponde, el total del comprobante no va a dar y el asistente
        no lo deja crear.
        """
        self.ensure_one()
        taxes = self.env["account.tax"].search(
            [
                ("company_id", "parent_of", self.company_id.id),
                ("type_tax_use", "=", "sale"),
                ("tax_group_id.l10n_ar_vat_afip_code", "!=", False),
            ],
            order="id",
        )
        by_code = {}
        for tax in taxes:
            by_code.setdefault(tax.tax_group_id.l10n_ar_vat_afip_code, tax)
        return by_code

    def _l10n_ar_format_number(self, number):
        self.ensure_one()
        return "%05d-%08d" % (int(self.journal_id.l10n_ar_afip_pos_number), number)

    def _l10n_ar_reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class L10nArFiscalWsRecoverLine(models.TransientModel):
    _name = "l10n_ar.fiscal.ws.recover.line"
    _description = "Comprobante del servicio a recuperar"
    _order = "number"

    wizard_id = fields.Many2one("l10n_ar.fiscal.ws.recover", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="wizard_id.company_id")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    number = fields.Integer("Número", readonly=True)
    date = fields.Date("Fecha", readonly=True)
    amount_total = fields.Monetary("Total", readonly=True)
    document_number = fields.Char("Identificación", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente")
    move_id = fields.Many2one(
        "account.move",
        string="Borrador",
        domain="[('journal_id', '=', parent.journal_id), ('state', '=', 'draft')]",
    )
    action = fields.Selection(
        [("match", "Asignar"), ("create", "Crear"), ("skip", "Omitir")],
        string="Qué hacer",
        required=True,
        default="skip",
    )
    reverse = fields.Boolean(
        "Neutralizar",
        help="Emite el comprobante que lo deja en cero: una nota de crédito si recuperamos "
        "una factura o una nota de débito, y una nota de débito si recuperamos una nota de "
        "crédito. Se valida en el acto, así que le pide su propia autorización al servicio.",
    )
    auth_mode = fields.Char(readonly=True)
    auth_code = fields.Char("CAE", readonly=True)
    auth_code_due = fields.Date("Vencimiento del CAE", readonly=True)
    note = fields.Char("Observación", readonly=True)
    values = fields.Json(readonly=True)

    def _l10n_ar_apply(self):
        self.ensure_one()
        move = self._l10n_ar_matched_move() if self.action == "match" else self._l10n_ar_created_move()
        if self.reverse:
            self._l10n_ar_reverse(move)
        return move

    def _l10n_ar_matched_move(self):
        """Asignarle al borrador el número y la autorización que ya tiene el servicio.

        Con la autorización escrita, el posteo no vuelve a pedírsela: el módulo solo le
        pide al servicio los comprobantes que no la tienen.
        """
        self.ensure_one()
        move = self.move_id
        if not move or move.state != "draft":
            raise UserError(_("El comprobante %s ya no está en borrador.", self.number))
        move.sudo().write(dict(self._l10n_ar_authorization_values(), invoice_date=self.date))
        move.l10n_latam_document_number = self.wizard_id._l10n_ar_format_number(self.number)
        move.action_post()
        return move

    def _l10n_ar_created_move(self):
        """Armar el comprobante que el servicio autorizó y del que Odoo no tiene nada."""
        self.ensure_one()
        move = self.env["account.move"].create(self._l10n_ar_move_values())
        if move.l10n_latam_document_type_id != self.wizard_id.document_type_id:
            raise UserError(
                _(
                    "El contacto %(partner)s no admite comprobantes %(document)s, así que este no se "
                    "puede crear a su nombre.",
                    partner=self.partner_id.display_name,
                    document=self.wizard_id.document_type_id.display_name,
                )
            )
        total = (self.values or {}).get("total") or 0
        if move.currency_id.compare_amounts(move.amount_total, total):
            raise UserError(
                _(
                    "El comprobante %(number)s quedó en %(built)s y el servicio informó %(reported)s. "
                    "Revisá los impuestos de venta de la compañía antes de recuperarlo.",
                    number=self.number,
                    built=move.amount_total,
                    reported=total,
                )
            )
        move.l10n_latam_document_number = self.wizard_id._l10n_ar_format_number(self.number)
        move.action_post()
        return move

    def _l10n_ar_move_values(self):
        self.ensure_one()
        wizard = self.wizard_id
        is_credit_note = wizard.document_type_id.internal_type == "credit_note"
        return dict(
            self._l10n_ar_authorization_values(),
            move_type="out_refund" if is_credit_note else "out_invoice",
            partner_id=self.partner_id.id,
            journal_id=wizard.journal_id.id,
            company_id=wizard.company_id.id,
            invoice_date=self.date,
            date=self.date,
            l10n_latam_document_type_id=wizard.document_type_id.id,
            invoice_line_ids=[Command.create(values) for values in self._l10n_ar_line_values()],
        )

    def _l10n_ar_line_values(self):
        """Una línea por alícuota que informó el servicio, más el no gravado y el exento."""
        self.ensure_one()
        values = self.values or {}
        taxes = self.wizard_id._l10n_ar_sale_taxes_by_vat_code()
        account = self.wizard_id.account_id
        label = _("Comprobante %s autorizado por el servicio", self.wizard_id._l10n_ar_format_number(self.number))
        buckets = [(item["code"], item["base"]) for item in values.get("vat_items") or []]
        buckets.append((NOT_TAXED_CODE, values.get("not_taxed") or 0))
        buckets.append((EXEMPT_CODE, values.get("exempt") or 0))
        lines = []
        for code, base in buckets:
            if not base:
                continue
            tax = taxes.get(code)
            if not tax:
                raise UserError(
                    _("La compañía no tiene ningún impuesto de venta con el código de IVA %s del organismo.", code)
                )
            lines.append(
                {
                    "name": label,
                    "account_id": account.id,
                    "quantity": 1,
                    "price_unit": base,
                    "tax_ids": [Command.set(tax.ids)],
                }
            )
        if not lines:
            raise UserError(_("El servicio no informó importes para el comprobante %s.", self.number))
        return lines

    def _l10n_ar_authorization_values(self):
        self.ensure_one()
        return {
            "l10n_ar_fiscal_auth_mode": self.auth_mode,
            "l10n_ar_fiscal_auth_code": self.auth_code,
            "l10n_ar_fiscal_auth_code_due": self.auth_code_due,
            "l10n_ar_fiscal_result": (self.values or {}).get("result") or "A",
            "l10n_ar_fiscal_message": _("Recuperado del servicio con el asistente de recuperación."),
        }

    def _l10n_ar_reverse(self, move):
        """El comprobante que deja en cero al recuperado.

        Una nota de crédito cuando recuperamos una factura o una nota de débito, y una
        nota de débito cuando lo que recuperamos es una nota de crédito.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        reason = _("Neutraliza el comprobante %s, recuperado del servicio", move.name)
        # los dos asistentes de Odoo, que son los que le eligen el tipo de comprobante
        # al que nace: una reversión copiando el tipo del original no pasa su propia
        # validación
        context = {"active_model": "account.move", "active_ids": move.ids}
        if move.move_type == "out_refund":
            self.env["account.debit.note"].with_context(**context).create(
                {"date": today, "reason": reason, "copy_lines": True}
            ).create_debit()
            reverse = self.env["account.move"].search([("debit_origin_id", "=", move.id)], limit=1)
        else:
            reversal = (
                self.env["account.move.reversal"]
                .with_context(**context)
                .create({"journal_id": move.journal_id.id, "date": today, "reason": reason})
            )
            reversal.reverse_moves()
            reverse = reversal.new_move_ids
        if not reverse:
            raise UserError(_("No pudimos armar el comprobante que neutraliza a %s.", move.name))
        reverse.action_post()
        return reverse
