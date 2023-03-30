# -*- coding: utf-8 -*-
# from odoo import http


# class L10nArAfipwsA5Extension(http.Controller):
#     @http.route('/l10n_ar_afipws_a5_extension/l10n_ar_afipws_a5_extension', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/l10n_ar_afipws_a5_extension/l10n_ar_afipws_a5_extension/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('l10n_ar_afipws_a5_extension.listing', {
#             'root': '/l10n_ar_afipws_a5_extension/l10n_ar_afipws_a5_extension',
#             'objects': http.request.env['l10n_ar_afipws_a5_extension.l10n_ar_afipws_a5_extension'].search([]),
#         })

#     @http.route('/l10n_ar_afipws_a5_extension/l10n_ar_afipws_a5_extension/objects/<model("l10n_ar_afipws_a5_extension.l10n_ar_afipws_a5_extension"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('l10n_ar_afipws_a5_extension.object', {
#             'object': obj
#         })
