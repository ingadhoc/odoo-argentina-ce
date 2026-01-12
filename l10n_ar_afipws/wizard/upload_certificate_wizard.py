##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64

from odoo import api, fields, models


class L10nArAfipwsUploadCertificate(models.TransientModel):
    _name = "afipws.upload_certificate.wizard"
    _description = "afipws.upload_certificate.wizard"

    @api.model
    def get_certificate(self):
        return self.env["afipws.certificate"].browse(self._context.get("active_id"))

    certificate_id = fields.Many2one(
        "afipws.certificate",
        required=True,
        readonly=True,
        default=get_certificate,
        ondelete="cascade",
    )
    certificate_file = fields.Binary("Upload Certificate", required=True)

    def action_confirm(self):
        """Upload and confirm certificate."""
        self.ensure_one()

        from odoo.exceptions import UserError

        try:
            # En Odoo, certificate_file es un campo Binary
            # Los datos pueden venir en diferentes formatos según cómo se suba el archivo
            cert_data = self.certificate_file

            if not cert_data:
                raise UserError("No se ha cargado ningún certificado")

            # Si es bytes, intentar decodificar directamente como UTF-8
            # (esto pasa cuando subes un archivo .pem directamente)
            if isinstance(cert_data, bytes):
                try:
                    cert_pem = cert_data.decode("utf-8")
                except UnicodeDecodeError:
                    # Si no es UTF-8, puede estar en base64
                    cert_pem = base64.b64decode(cert_data).decode("utf-8")

            # Si es string, puede ser:
            # 1. Ya el contenido PEM directo
            # 2. Base64 encoded
            elif isinstance(cert_data, str):
                # Verificar si ya es PEM
                if "-----BEGIN CERTIFICATE-----" in cert_data:
                    cert_pem = cert_data
                else:
                    # Intentar decodificar de base64
                    try:
                        cert_pem = base64.b64decode(cert_data).decode("utf-8")
                    except Exception:
                        raise UserError("El archivo no está en un formato válido (ni PEM ni base64)")
            else:
                raise UserError(f"Tipo de datos inesperado: {type(cert_data)}")

            # Validar que sea un certificado PEM válido
            cert_pem = cert_pem.strip()
            if not cert_pem.startswith("-----BEGIN CERTIFICATE-----"):
                raise UserError(
                    "El archivo no parece ser un certificado PEM válido. "
                    "Debe comenzar con '-----BEGIN CERTIFICATE-----'"
                )

            if not cert_pem.endswith("-----END CERTIFICATE-----"):
                raise UserError(
                    "El archivo no parece ser un certificado PEM válido. "
                    "Debe terminar con '-----END CERTIFICATE-----'"
                )

            # Log del certificado recibido
            from odoo import _logger

            _logger.info("==== WIZARD: Subiendo certificado ====")
            _logger.info(
                "Certificado ID: %s, Alias: %s", self.certificate_id.id, self.certificate_id.alias_id.common_name
            )
            _logger.info("Longitud del certificado PEM: %s caracteres", len(cert_pem))
            _logger.info("Primeros 100 caracteres: %s...", cert_pem[:100])

            # Escribir el certificado
            self.certificate_id.write({"crt": cert_pem})
            _logger.info("Certificado escrito correctamente. Estado actual: %s", self.certificate_id.state)

            # IMPORTANTE: Forzar el cálculo inmediatamente después de escribir
            # porque con store=True el @api.depends a veces no se dispara correctamente
            _logger.info("Forzando _compute_cert_info() después de escribir CRT...")
            self.certificate_id._compute_cert_info()
            _logger.info(
                "Después de compute forzado: valid_to=%s, days=%s",
                self.certificate_id.cert_valid_to,
                self.certificate_id.cert_days_to_expire,
            )

            # Confirmar el certificado
            _logger.info("Llamando a action_confirm()...")
            self.certificate_id.action_confirm()
            _logger.info("action_confirm() completado. Nuevo estado: %s", self.certificate_id.state)

        except UserError:
            raise
        except Exception as e:
            raise UserError(f"Error al procesar el certificado: {str(e)}")

        return True
