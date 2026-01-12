##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..lib import crypto_utils

_logger = logging.getLogger(__name__)


class AfipwsCertificateAlias(models.Model):
    _name = "afipws.certificate_alias"
    _description = "AFIP Distingish Name / Alias"
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
        auto_join=True,
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
        "afipws.certificate",
        "alias_id",
        "Certificates",
        auto_join=True,
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

    # Campos para alertas de certificados
    has_expired_certificate = fields.Boolean(
        string="Tiene certificado vencido",
        compute="_compute_certificate_alerts",
    )
    has_expiring_soon_certificate = fields.Boolean(
        string="Tiene certificado por vencer",
        compute="_compute_certificate_alerts",
    )
    certificate_alert_message = fields.Char(
        string="Mensaje de alerta",
        compute="_compute_certificate_alerts",
    )

    @api.depends("certificate_ids", "certificate_ids.state", "certificate_ids.crt")
    def _compute_certificate_alerts(self):
        """Computar alertas de certificados vencidos o por vencer"""
        for rec in self:
            confirmed_certs = rec.certificate_ids.filtered(lambda c: c.state == "confirmed")

            if not confirmed_certs:
                rec.has_expired_certificate = False
                rec.has_expiring_soon_certificate = False
                rec.certificate_alert_message = False
                _logger.debug(f"Alias {rec.id}: Sin certificados confirmados")
                continue

            _logger.debug(f"Alias {rec.id}: {len(confirmed_certs)} certificados confirmados")

            # Verificar si hay certificados vencidos
            expired = confirmed_certs.filtered(lambda c: c.cert_is_expired)
            if expired:
                rec.has_expired_certificate = True
                rec.has_expiring_soon_certificate = False
                rec.certificate_alert_message = "⚠ Tiene certificados vencidos. Debe renovarlos urgentemente."
                _logger.info(f"Alias {rec.id}: {len(expired)} certificados vencidos")
                continue

            # Verificar si hay certificados por vencer (menos de 30 días)
            expiring_soon = confirmed_certs.filtered(lambda c: c.cert_days_to_expire > 0 and c.cert_days_to_expire < 30)
            if expiring_soon:
                min_days = min(expiring_soon.mapped("cert_days_to_expire"))
                rec.has_expired_certificate = False
                rec.has_expiring_soon_certificate = True
                rec.certificate_alert_message = (
                    f"⚠ Tiene certificados que vencen en {min_days} días. Planifique su renovación."
                )
                _logger.info(f"Alias {rec.id}: {len(expiring_soon)} certificados por vencer")
                continue

            # Sin alertas
            rec.has_expired_certificate = False
            rec.has_expiring_soon_certificate = False
            rec.certificate_alert_message = False
            _logger.debug(f"Alias {rec.id}: Sin alertas, todos los certificados OK")

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
        """Generate RSA private key using cryptography library."""
        for rec in self:
            key_pem = crypto_utils.generate_rsa_key(key_length)
            rec.key = key_pem.decode("utf-8") if isinstance(key_pem, bytes) else key_pem

    def action_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        self.certificate_ids.write({"state": "cancel"})
        return True

    def action_create_certificate_request(self):
        """Create Certificate Signing Request (CSR) using cryptography library."""
        for record in self:
            # Prepare subject data
            country_code = record.country_id.code or "AR"
            state_name = record.state_id.name if record.state_id else ""
            city = record.city or ""
            company_name = record.company_id.name or ""
            department = record.department or "IT"
            common_name = record.common_name or "AFIP WS"
            cuit = record.cuit or ""

            # Generate CSR using crypto_utils
            csr_pem = crypto_utils.create_csr(
                private_key_pem=record.key.encode("utf-8") if isinstance(record.key, str) else record.key,
                country_code=country_code,
                state_name=state_name,
                city=city,
                company_name=company_name,
                department=department,
                common_name=common_name,
                cuit=cuit,
            )

            # Convert to string if needed
            csr_str = csr_pem.decode("utf-8") if isinstance(csr_pem, bytes) else csr_pem

            # Create certificate record
            vals = {
                "csr": csr_str,
                "alias_id": record.id,
            }
            record.certificate_ids.create(vals)
        return True

    @api.constrains("common_name")
    def check_common_name_len(self):
        if self.filtered(lambda x: x.common_name and len(x.common_name) > 50):
            raise ValidationError(_("The Common Name must be lower than 50 characters long"))
