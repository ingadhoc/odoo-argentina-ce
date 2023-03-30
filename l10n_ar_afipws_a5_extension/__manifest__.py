# -*- coding: utf-8 -*-
{
    'name': "Modulo para agregar consultas al Padron A5 de AFIP",

    'summary': """
        Extension de consultas al padron A5
    """,

    'description': """
        Se agrega la actualizacion de los siguientes datos en la consulta al padron desde un Contacto:
        - Actividades
        - Impuestos
        - Monotributo
        - Actividad Monotributo
        - Empleador
        - Integrante de sociedad
        - Impuesto a ganancias
        
        Se agrega la actualizacion de actividades, impuestos y conceptos de AFIP desde Contabilidad / Ajustes / Localizacion argentina
        El contenido de este modulo fue migrado desde l10n_ar_account utilizando la rama 11.0 como guia.
    """,

    'author': "Abasto Software S.R.L.",
    'category': "Localization/Argentina",
    'version': '15.0.1.0.0',
    'depends': ['l10n_ar_afipws', 'l10n_ar_ux'],
    'data': [
        'views/res_config_settings.xml',
        'views/templates.xml',
    ],
    'demo': [],
}
