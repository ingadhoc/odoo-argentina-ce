##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
# import time


class AccountVatLedger(models.Model):

    _name = "account.vat.ledger"
    _description = "Account VAT Ledger"
    _inherit = ['mail.thread']
    _order = 'date_from desc'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda self: self.env[
            'res.company']._company_default_get('account.vat.ledger')
    )
    type = fields.Selection(
        [('sale', 'Sale'), ('purchase', 'Purchase')],
        "Type",
        required=True
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    journal_ids = fields.Many2many(
        'account.journal', 'account_vat_ledger_journal_rel',
        'vat_ledger_id', 'journal_id',
        string='Journals',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    first_page = fields.Integer(
        "First Page",
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    last_page = fields.Integer(
        "Last Page",
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    presented_ledger = fields.Binary(
        "Presented Ledger",
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    presented_ledger_name = fields.Char(
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('presented', 'Presented'), ('cancel', 'Cancel')],
        'State',
        required=True,
        default='draft'
    )
    note = fields.Html(
        "Notes"
    )
# Computed fields
    name = fields.Char(
        'Titile',
        compute='_compute_name'
    )
    reference = fields.Char(
        'Reference',
    )
    invoice_ids = fields.Many2many(
        'account.ar.vat.line',
        string="Invoices",
        compute="_compute_invoices"
    )

    @api.depends('journal_ids', 'date_from', 'date_to')
    def _compute_invoices(self):
        for rec in self:
            rec.invoice_ids = rec.env['account.ar.vat.line'].search([
                ('state', '!=', 'draft'),
                # ('number', '!=', False),
                # ('internal_number', '!=', False),
                ('journal_id', 'in', rec.journal_ids.ids),
                ('date', '>=', rec.date_from),
                ('date', '<=', rec.date_to),
            ])

    @api.depends(
        'type',
        'reference',
    )
    def _compute_name(self):
        date_format = self.env['res.lang']._lang_get(
            self._context.get('lang', 'en_US')).date_format
        for rec in self:
            if rec.type == 'sale':
                ledger_type = _('Sales')
            elif rec.type == 'purchase':
                ledger_type = _('Purchases')
            name = _("%s VAT Ledger %s - %s") % (
                ledger_type,
                rec.date_from and fields.Date.from_string(
                    rec.date_from).strftime(date_format) or '',
                rec.date_to and fields.Date.from_string(
                    rec.date_to).strftime(date_format) or '',
            )
            if rec.reference:
                name = "%s - %s" % (name, rec.reference)
            rec.name = name

    @api.onchange('company_id')
    def change_company(self):
        if self.type == 'sale':
            domain = [('type', '=', 'sale')]
        elif self.type == 'purchase':
            domain = [('type', '=', 'purchase')]
        domain += [
            ('l10n_latam_use_documents', '=', True),
            ('company_id', '=', self.company_id.id),
        ]
        journals = self.env['account.journal'].search(domain)
        self.journal_ids = journals

    def action_present(self):
        self.state = 'presented'

    def action_cancel(self):
        self.state = 'cancel'

    def action_to_draft(self):
        self.state = 'draft'

    def action_print(self):
        self.ensure_one()
        return self.env['ir.actions.report'].search(
            [('report_name', '=', 'report_account_vat_ledger')],
            limit=1).report_action(self)
