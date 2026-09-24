##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64

from odoo import api, fields, models


class L10nArAfipwsUploadCertificate(models.TransientModel):
    _name = "l10n_ar.fiscal.certificate.upload.wizard"
    _description = "l10n_ar.fiscal.certificate.upload.wizard"

    @api.model
    def get_certificate(self):
        return self.env["l10n_ar.fiscal.certificate"].browse(self._context.get("active_id"))

    certificate_id = fields.Many2one(
        "l10n_ar.fiscal.certificate",
        required=True,
        readonly=True,
        default=get_certificate,
        ondelete="cascade",
    )
    certificate_file = fields.Binary("Upload Certificate", required=True)

    def action_confirm(self):
        """ """
        self.ensure_one()
        self.certificate_id.write({"crt": base64.decodebytes(self.certificate_file)})
        self.certificate_id.action_confirm()
        return True
