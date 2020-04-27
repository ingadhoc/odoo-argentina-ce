from odoo import tools, models, fields


class AccountArVatLine(models.Model):
    """
    Modelo base para nuevos reportes argentinos de iva. La idea es que estas
    lineas tenga todos los datos necesarios y que frente a cambios en odoo, los
    mismos sean abosrvidos por este cubo y no se requieran cambios en los
    reportes que usan estas lineas.
    Se genera una linea para cada apunte contable afectado por iva
    Basicamente lo que hace es convertir los apuntes contables en columnas
    segun la informacion de impuestos y ademas agrega algunos otros
    campos
    """
    _name = "account.ar.vat.line"
    _description = "Línea de IVA para análisis en localización argentina"
    _auto = False

    document_type_id = fields.Many2one('l10n_latam.document.type', 'Document Type', readonly=True)
    date = fields.Date(readonly=True)
    invoice_date = fields.Date(readonly=True)
    cuit = fields.Char(readonly=True)
    afip_responsibility_type_name = fields.Char(readonly=True)
    partner_name = fields.Char(readonly=True)
    move_name = fields.Char(readonly=True)
    type = fields.Selection(selection=[
        ('entry', 'Journal Entry'),
        ('out_invoice', 'Customer Invoice'),
        ('out_refund', 'Customer Credit Note'),
        ('in_invoice', 'Vendor Bill'),
        ('in_refund', 'Vendor Credit Note'),
        ('out_receipt', 'Sales Receipt'),
        ('in_receipt', 'Purchase Receipt'),
    ], readonly=True)
    base_21 = fields.Monetary(readonly=True, string='Grav. 21%', currency_field='company_currency_id')
    vat_21 = fields.Monetary(readonly=True, string='VAT 21%', currency_field='company_currency_id')
    base_27 = fields.Monetary(readonly=True, string='Grav. 27%', currency_field='company_currency_id')
    vat_27 = fields.Monetary(readonly=True, string='VAT 27%', currency_field='company_currency_id')
    base_10 = fields.Monetary(readonly=True, string='Grav. 10,5%', currency_field='company_currency_id')
    vat_10 = fields.Monetary(readonly=True, string='VAT 10,5%', currency_field='company_currency_id')
    base_25 = fields.Monetary(readonly=True, string='Grav. 2,5%', currency_field='company_currency_id')
    vat_25 = fields.Monetary(readonly=True, string='VAT 2,5%', currency_field='company_currency_id')
    base_5 = fields.Monetary(readonly=True, string='Grav. 5%', currency_field='company_currency_id')
    vat_5 = fields.Monetary(readonly=True, string='VAT 5%', currency_field='company_currency_id')
    vat_per = fields.Monetary(
        readonly=True, string='VAT Perc.', currency_field='company_currency_id')
    not_taxed = fields.Monetary(
        readonly=True, string='Not taxed/ex', currency_field='company_currency_id')
    other_taxes = fields.Monetary(
        readonly=True, string='Other Taxes', currency_field='company_currency_id')
    total = fields.Monetary(readonly=True, currency_field='company_currency_id')
    state = fields.Selection([('draft', 'Unposted'), ('posted', 'Posted')], 'Status', readonly=True)
    journal_id = fields.Many2one('account.journal', 'Journal', readonly=True, auto_join=True)
    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True, auto_join=True)
    afip_responsibility_type_id = fields.Many2one(
        'l10n_ar.afip.responsibility.type', string='AFIP Responsibility Type', readonly=True, auto_join=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True, auto_join=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    move_id = fields.Many2one('account.move', string='Entry', auto_join=True)

    def open_journal_entry(self):
        self.ensure_one()
        return self.move_id.get_formview_action()

    def init(self):
        cr = self._cr
        tools.drop_view_if_exists(cr, self._table)
        # pylint: disable=sql-injection
        query = """
SELECT
    am.id,
    (CASE WHEN lit.l10n_ar_afip_code = '80' THEN rp.vat ELSE null END) as cuit,
    art.name as afip_responsibility_type_name,
    am.name as move_name,
    rp.name as partner_name,
    am.id as move_id,
    am.type,
    am.date,
    am.invoice_date,
    am.partner_id,
    am.journal_id,
    am.name,
    am.l10n_ar_afip_responsibility_type_id as afip_responsibility_type_id,
    am.l10n_latam_document_type_id as document_type_id,
    am.state,
    am.company_id,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code = '5' THEN aml.balance ELSE Null END) as base_21,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code = '5' THEN aml.balance ELSE Null END) as vat_21,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code = '4' THEN aml.balance ELSE Null END) as base_10,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code = '4' THEN aml.balance ELSE Null END) as vat_10,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code = '6' THEN aml.balance ELSE Null END) as base_27,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code = '6' THEN aml.balance ELSE Null END) as vat_27,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code = '9' THEN aml.balance ELSE Null END) as base_25,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code = '9' THEN aml.balance ELSE Null END) as vat_25,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code = '8' THEN aml.balance ELSE Null END) as base_5,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code = '8' THEN aml.balance ELSE Null END) as vat_5,
    sum(CASE WHEN btg.l10n_ar_vat_afip_code in ('0', '1', '2', '3', '7') THEN aml.balance ELSE Null END) as not_taxed,
    sum(CASE WHEN ntg.l10n_ar_tribute_afip_code = '06' THEN aml.balance ELSE Null END) as vat_per,
    sum(CASE WHEN ntg.l10n_ar_vat_afip_code is null and ntg.l10n_ar_tribute_afip_code != '06'
        THEN aml.balance ELSE Null END) as other_taxes,
    sum(aml.balance) as total
FROM
    account_move_line aml
LEFT JOIN
    account_move as am
    ON aml.move_id = am.id
LEFT JOIN
    -- nt = net tax
    account_tax AS nt
    ON aml.tax_line_id = nt.id
LEFT JOIN
    account_move_line_account_tax_rel AS amltr
    ON aml.id = amltr.account_move_line_id
LEFT JOIN
    -- bt = base tax
    account_tax AS bt
    ON amltr.account_tax_id = bt.id
LEFT JOIN
    account_tax_group AS btg
    ON btg.id = bt.tax_group_id
LEFT JOIN
    account_tax_group AS ntg
    ON ntg.id = nt.tax_group_id
LEFT JOIN
    res_partner AS rp
    ON rp.id = am.partner_id
LEFT JOIN
    l10n_latam_identification_type AS lit
    ON rp.l10n_latam_identification_type_id = lit.id
LEFT JOIN
    l10n_ar_afip_responsibility_type AS art
    ON am.l10n_ar_afip_responsibility_type_id = art.id
WHERE
    (aml.tax_line_id is not null or btg.l10n_ar_vat_afip_code is not null)
    and am.type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
GROUP BY
    am.id, art.name, rp.id, lit.id
ORDER BY
    am.date, am.name
        """
        sql = """CREATE or REPLACE VIEW %s as (%s)""" % (self._table, query)
        cr.execute(sql)
