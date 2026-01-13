{
    "name": "Modulo Base para los Web Services de ARCA",
    "version": "19.0.1.7.4",
    "category": "Localization/Argentina",
    "author": "ADHOC SA, Moldeo Interactive,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "summary": "",
    "depends": [
        "l10n_ar",  # needed for CUIT and also demo data
        # TODO this module should be merged with l10n_ar_fiscal_ws_fe as the dependencies are the same
    ],
    "external_dependencies": {"python": ["OpenSSL"]},
    "data": [
        "wizard/upload_certificate_view.xml",
        "wizard/res_partner_update_from_padron_wizard_view.xml",
        "views/arcaws_menuitem.xml",
        "views/arcaws_certificate_view.xml",
        "views/arcaws_certificate_alias_view.xml",
        "views/arcaws_connection_view.xml",
        "views/arcaws.xml",
        "views/res_config_settings.xml",
        "views/res_partner.xml",
        "views/arcaws_request.xml",
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir.actions.url_data.xml",
        "data/arcaws.xml",
    ],
    "assets": {
        "web._assets_core": [
            "l10n_ar_fiscal_ws/static/src/core/errors/error_dialogs.js",
            "l10n_ar_fiscal_ws/static/src/core/errors/error_dialogs.xml",
        ]
    },
    "demo": [
        "demo/certificate_demo.xml",
        "demo/parameter_demo.xml",
    ],
    "images": [],
    "installable": True,
    "auto_install": False,
    "application": False,
}
