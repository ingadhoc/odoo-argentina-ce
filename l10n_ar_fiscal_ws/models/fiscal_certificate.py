##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import logging

from cryptography import x509
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nArFiscalCertificate(models.Model):
    _name = "l10n_ar.fiscal.certificate"
    _description = "Fiscal Certificate"
    _rec_name = "alias_id"

    alias_id = fields.Many2one(
        "l10n_ar.fiscal.certificate.alias",
        ondelete="cascade",
        string="Certificate Alias",
        required=True,
        bypass_search_access=True,
        index=True,
    )
    csr = fields.Text(
        "Request Certificate",
        readonly=True,
        help="Certificate Request in PEM format.",
    )
    crt = fields.Text(
        "Certificate",
        readonly=True,
        help="Certificate in PEM format.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancel", "Cancelled"),
        ],
        index=True,
        readonly=True,
        default="draft",
        help="* The 'Draft' state is used when a user is creating a new pair "
        "key. Warning: everybody can see the key."
        "\n* The 'Confirmed' state is used when a certificate is valid."
        "\n* The 'Canceled' state is used when the key is not more used. You "
        "cant use this key again.",
    )
    request_file = fields.Binary(
        "Download Signed Certificate Request",
        compute="_compute_request_file",
        readonly=True,
    )
    request_filename = fields.Char(
        "Filename",
        readonly=True,
        compute="_compute_request_file",
    )

    @api.depends("csr")
    def _compute_request_file(self):
        for rec in self:
            rec.request_filename = "request.csr"
            rec.request_file = base64.encodebytes(rec.csr.encode("utf-8")) if rec.csr else False

    def action_to_draft(self):
        if self.alias_id.state != "confirmed":
            raise UserError(_("Certificate Alias must be confirmed first!"))
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    def action_confirm(self):
        self.verify_crt()
        self.write({"state": "confirmed"})
        return True

    def verify_crt(self):
        """Check that the certificate is well formed before confirming it."""
        for rec in self:
            if not rec.crt:
                raise UserError(_("Pegá el certificado que te devolvió ARCA antes de confirmar."))
            rec.get_certificate()
        return True

    def get_certificate(self):
        """Loaded x509 certificate, or None when there is nothing loaded yet."""
        self.ensure_one()
        if not self.crt:
            return None
        try:
            return x509.load_pem_x509_certificate(self.crt.encode("utf-8"))
        except Exception as error:
            raise UserError(
                _(
                    "No pudimos leer el certificado. Revisá que empiece con la línea "
                    "BEGIN CERTIFICATE y que no le falten saltos de línea.\n\n%s",
                    error,
                )
            ) from error
