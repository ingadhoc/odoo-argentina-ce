{
    "name": "Argentinian Reports (CE)",
    'version': '13.0.1.0.0',
    'category': 'Localization/Argentina',
    'sequence': 14,
    'author': 'ADHOC SA,Moldeo Interactive,Odoo Community Association (OCA)',
    'license': 'AGPL-3',
    'summary': '',
    "depends": [
        "report_aeroo",
        "l10n_ar",
    ],
    'external_dependencies': {
    },
    "data": [
        'report/account_ar_vat_line_view.xml',
        'report/account_vat_ledger_report.xml',
        'views/account_vat_report_views.xml',
        'security/ir.model.access.csv',
        'security/security.xml',
    ],
    'demo': [
    ],
    'images': [
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
