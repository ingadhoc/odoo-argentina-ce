{
    "name": "Modulo Base para los Web Services de AFIP",
    "version": "16.0.1.0.0",
    "category": "Localization/Argentina",
    "sequence": 14,
    "author": "ADHOC SA, Moldeo Interactive,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "summary": "",
    "depends": [
        "l10n_ar",  # needed for CUIT and also demo data
        # TODO this module should be merged with l10n_ar_afipws_fe as the dependencies are the same
    ],
    "external_dependencies": {"python": ["pyafipws", "OpenSSL", "pysimplesoap"]},
    "data": [
        "wizard/upload_certificate_view.xml",
        "wizard/res_partner_update_from_padron_wizard_view.xml",
        "views/afipws_menuitem.xml",
        "views/afipws_certificate_view.xml",
        "views/afipws_certificate_alias_view.xml",
        "views/afipws_connection_view.xml",
        "views/res_config_settings.xml",
        "views/res_partner.xml",
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir.actions.url_data.xml",
    ],
    "demo": [
        "demo/certificate_demo.xml",
        "demo/parameter_demo.xml",
    ],
    "images": [],
    'installable': True,
    "auto_install": False,
    "application": False,
}
