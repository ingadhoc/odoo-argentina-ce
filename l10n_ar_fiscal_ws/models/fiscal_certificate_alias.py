##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class L10nArFiscalCertificateAlias(models.Model):
    _name = "l10n_ar.fiscal.certificate.alias"
    _description = "Fiscal Certificate Alias"
    _rec_name = "common_name"

    """
    Para poder acceder a un servicio, la aplicación a programar debe utilizar
    un certificado de seguridad, que se obtiene en la web de afip. Entre otras
    cosas, el certificado contiene un Distinguished Name (DN) que incluye una
    CUIT. Cada DN será identificado por un "alias" o "nombre simbólico",
    que actúa como una abreviación.
    EJ alias: AFIP WS Prod - ADHOC SA
    EJ DN: C=ar, ST=santa fe, L=rosario, O=adhoc s.a., OU=it,
           SERIALNUMBER=CUIT 30714295698, CN=afip web services - adhoc s.a.
    """

    common_name = fields.Char(
        size=64,
        default="AFIP WS",
        help="Just a name, you can leave it this way",
        readonly=True,
        required=True,
    )
    key = fields.Text(
        "Private Key",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
        bypass_search_access=True,
        index=True,
    )
    country_id = fields.Many2one(
        "res.country",
        "Country",
        readonly=True,
        required=True,
    )
    state_id = fields.Many2one(
        "res.country.state",
        "State",
        readonly=True,
    )
    city = fields.Char(
        readonly=True,
        required=True,
    )
    department = fields.Char(
        default="IT",
        readonly=True,
        required=True,
    )
    cuit = fields.Char(
        "CUIT",
        compute="_compute_cuit",
        required=True,
    )
    company_cuit = fields.Char(
        "Company CUIT",
        size=16,
        readonly=True,
    )
    service_provider_cuit = fields.Char(
        "Service Provider CUIT",
        size=16,
        readonly=True,
    )
    certificate_ids = fields.One2many(
        "l10n_ar.fiscal.certificate",
        "alias_id",
        "Certificates",
        bypass_search_access=True,
    )
    service_type = fields.Selection(
        [("in_house", "In House"), ("outsourced", "Outsourced")],
        default="in_house",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancel", "Cancelled"),
        ],
        "Status",
        index=True,
        readonly=True,
        default="draft",
        help="* The 'Draft' state is used when a user is creating a new pair "
        "key. Warning: everybody can see the key."
        "\n* The 'Confirmed' state is used when the key is completed with "
        "public or private key."
        "\n* The 'Canceled' state is used when the key is not more used. "
        "You cant use this key again.",
    )
    type = fields.Selection(
        [("production", "Production"), ("homologation", "Homologation")],
        required=True,
        default="production",
        readonly=True,
    )

    @api.onchange("company_id")
    def change_company_name(self):
        if self.company_id:
            common_name = "AFIP WS %s - %s" % (self.type, self.company_id.name)
            self.common_name = common_name[:50]

    @api.depends("company_cuit", "service_provider_cuit", "service_type")
    def _compute_cuit(self):
        for rec in self:
            if rec.service_type == "outsourced":
                rec.cuit = rec.service_provider_cuit
            else:
                rec.cuit = rec.company_cuit

    @api.onchange("company_id")
    def change_company_id(self):
        if self.company_id:
            self.country_id = self.company_id.country_id.id
            self.state_id = self.company_id.state_id.id
            self.city = self.company_id.city
            self.company_cuit = self.company_id.vat

    def action_confirm(self):
        if not self.key:
            self.generate_key()
        self.write({"state": "confirmed"})
        return True

    def generate_key(self, key_length=2048):
        """Generate the private key that will sign the certificate request."""
        for rec in self:
            key = rsa.generate_private_key(public_exponent=65537, key_size=key_length)
            rec.key = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")

    def action_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        self.certificate_ids.write({"state": "cancel"})
        return True

    def action_create_certificate_request(self):
        """Build the certificate request (CSR) to upload on the tax authority site."""
        for record in self:
            if not record.key:
                record.generate_key()
            attributes = [
                x509.NameAttribute(NameOID.COUNTRY_NAME, record.country_id.code),
                x509.NameAttribute(NameOID.LOCALITY_NAME, record.city),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, record.company_id.name),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, record.department),
                x509.NameAttribute(NameOID.COMMON_NAME, record.common_name),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, "CUIT %s" % record.cuit),
            ]
            if record.state_id:
                attributes.insert(1, x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, record.state_id.name))
            key = serialization.load_pem_private_key(record.key.encode("utf-8"), password=None)
            csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attributes)).sign(key, hashes.SHA256())
            record.certificate_ids.create(
                {
                    "csr": csr.public_bytes(serialization.Encoding.PEM).decode("utf-8"),
                    "alias_id": record.id,
                }
            )
        return True

    @api.constrains("common_name")
    def check_common_name_len(self):
        if self.filtered(lambda x: x.common_name and len(x.common_name) > 50):
            raise ValidationError(_("The Common Name must be lower than 50 characters long"))
