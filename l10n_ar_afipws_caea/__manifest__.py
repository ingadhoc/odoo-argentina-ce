{
    "name": "Factura Electrónica Argentina CAEA",
    "summary": """
        Habilita la gestion de CAEA""",
    "sequence": 14,
    "author": "Filoquin",
    "website": "http://www.sipecu.com.ar",
    "category": "Localization/Argentina",
    "version": "15.0.1.0.0",
    "depends": ["l10n_ar_afipws_fe"],
    "data": [
        "security/ir.model.access.csv",
        "views/asset.xml",
        "views/account_journal.xml",
        "views/afipws_caea.xml",
        "views/company.xml",
        "views/res_config_settings.xml",
        "views/pyafipws_dummy.xml",
        "views/account_move.xml",
        "data/ir_cron.xml",
    ],
    "qweb": [
        "static/src/xml/systray_afip_caea.xml",
    ],
    "installable": False,
    "auto_install": False,
    "application": False,
}
