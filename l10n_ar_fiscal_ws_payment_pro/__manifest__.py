{
    "name": "Pagos pro con web services fiscales",
    "version": "19.0.1.0.0",
    "category": "Localization/Argentina",
    "author": "ADHOC SA",
    "website": "www.adhoc.com.ar",
    "license": "AGPL-3",
    "summary": "Período asociado y comprobante de origen en las notas de crédito y débito que nacen de un pago",
    "depends": [
        "account_payment_pro",
        "l10n_ar_fiscal_ws",
    ],
    "external_dependencies": {},
    "data": [
        "wizards/account_payment_invoice_wizard_view.xml",
    ],
    "installable": True,
    "auto_install": True,
    "application": False,
}
