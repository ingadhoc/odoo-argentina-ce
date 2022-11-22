{
    "name": "Factura Electrónica Argentina CAEA",
    "summary": """
        Habilita la gestion de CAEA para modo contingencia""",
    "sequence": 14,
    "author": "Filoquin",
    "website": "http://www.sipecu.com.ar",
    "license": "LGPL-3",
    "category": "Localization/Argentina",
    "version": "16.0.1.0.0",
    "depends": ["l10n_ar_afipws_fe"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal.xml",
        "views/afipws_caea.xml",
        "views/company.xml",
        "wizard/res_config_settings.xml",
        "wizard/pyafipws_dummy.xml",
        "views/account_move.xml",
        "data/ir_cron.xml",
    ],
    "qweb": [
        "static/src/xml/systray_afip_caea.xml",
    ],
    'assets': {
        #'web.assets_backend': ['/l10n_ar_afipws_caea/static/src/js/systray_afip_caea.js'],
        #'web.assets_qweb': ['/l10n_ar_afipws_caea/static/src/xml/systray_afip_caea.xml'],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
