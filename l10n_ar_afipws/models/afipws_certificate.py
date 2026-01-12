##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import crypto_utils

_logger = logging.getLogger(__name__)


class AfipwsCertificate(models.Model):
    _name = "afipws.certificate"
    _description = "afipws.certificate"
    _rec_name = "alias_id"

    alias_id = fields.Many2one(
        "afipws.certificate_alias",
        ondelete="cascade",
        string="Certificate Alias",
        required=True,
        auto_join=True,
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

    # Campos informativos del certificado
    cert_valid_from = fields.Datetime(
        string="Válido desde",
        compute="_compute_cert_info",
        store=True,
        help="Fecha desde la cual el certificado es válido",
    )
    cert_valid_to = fields.Datetime(
        string="Válido hasta",
        compute="_compute_cert_info",
        store=True,
        help="Fecha de vencimiento del certificado",
    )
    cert_subject = fields.Char(
        string="Subject (DN)",
        compute="_compute_cert_info",
        store=True,
        help="Distinguished Name del sujeto del certificado",
    )
    cert_issuer = fields.Char(
        string="Emisor",
        compute="_compute_cert_info",
        store=True,
        help="Entidad que emitió el certificado",
    )
    cert_serial_number = fields.Char(
        string="Número de Serie",
        compute="_compute_cert_info",
        store=True,
        help="Número de serie del certificado",
    )
    cert_is_expired = fields.Boolean(
        string="Certificado Vencido",
        compute="_compute_cert_info",
        store=True,
        help="Indica si el certificado está vencido",
    )
    cert_days_to_expire = fields.Integer(
        string="Días para vencer",
        compute="_compute_cert_info",
        store=True,
        help="Cantidad de días hasta que expire el certificado",
    )

    # Campos de validación y servicios AFIP
    afip_services = fields.Text(
        string="Servicios AFIP",
        help="Servicios AFIP adheridos a este certificado (uno por línea). " "Ejemplos: wsfe, wsfex, wsbfe, wsmtxca",
        default="wsfe\nwsfex",
    )
    certificate_validated = fields.Boolean(
        string="Validado con AFIP",
        default=False,
        help="Indica si el certificado fue validado contra AFIP WSAA",
        copy=False,
    )
    validation_date = fields.Datetime(
        string="Fecha Validación",
        help="Fecha de la última validación exitosa con AFIP",
        copy=False,
    )
    validation_error = fields.Text(
        string="Error de Validación",
        help="Último error de validación con AFIP",
        copy=False,
    )

    @api.depends("csr")
    def _compute_request_file(self):
        for rec in self:
            rec.request_filename = "request.csr"
            if rec.csr:
                rec.request_file = base64.encodebytes(rec.csr.encode("utf-8"))
            else:
                rec.request_file = False

    @api.depends("crt")
    def _compute_cert_info(self):
        """Extraer información del certificado X.509"""
        import traceback
        from datetime import datetime, timezone

        _logger.info(f"==== _COMPUTE_CERT_INFO: Procesando {len(self)} certificado(s) ====")

        for record in self:
            _logger.info(
                f"Certificado ID: {record.id}, has_crt: {bool(record.crt)}, "
                f"state: {record.state}, crt_length: {len(record.crt) if record.crt else 0}"
            )

            # Inicializar todos los campos primero
            record.cert_valid_from = False
            record.cert_valid_to = False
            record.cert_subject = False
            record.cert_issuer = False
            record.cert_serial_number = False
            record.cert_is_expired = False
            record.cert_days_to_expire = 0

            if not record.crt:
                _logger.warning(f"Certificado {record.id}: Sin contenido CRT, saltando...")
                continue

            try:
                _logger.info(f"Cert {record.id}: Llamando a get_certificate()...")
                cert = record.get_certificate()
                _logger.info(f"Cert {record.id}: get_certificate() retornó tipo: {type(cert)}")

                if not cert:
                    _logger.warning(f"get_certificate() retornó None para certificado {record.id}")
                    record.cert_valid_from = False
                    record.cert_valid_to = False
                    record.cert_subject = False
                    record.cert_issuer = False
                    record.cert_serial_number = False
                    record.cert_is_expired = False
                    record.cert_days_to_expire = 0
                    continue

                _logger.info(f"Procesando certificado {record.id}, tipo: {type(cert)}")

                # Fechas de validez
                # IMPORTANTE: Odoo requiere datetime "naive" (sin timezone)
                # pero cryptography devuelve "aware" (con timezone UTC)
                try:
                    _logger.info(f"Cert {record.id}: Extrayendo fechas (usando _utc)...")
                    # Obtener datetimes aware y convertir a naive eliminando tzinfo
                    valid_from_utc = cert.not_valid_before_utc.replace(tzinfo=None)
                    valid_to_utc = cert.not_valid_after_utc.replace(tzinfo=None)

                    record.cert_valid_from = valid_from_utc
                    record.cert_valid_to = valid_to_utc

                    # Para comparación, usar datetime naive en UTC
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    record.cert_is_expired = valid_to_utc < now
                    days_diff = (valid_to_utc - now).days
                    record.cert_days_to_expire = days_diff if days_diff > 0 else 0

                    _logger.info(
                        f"Cert {record.id}: Fechas extraídas OK (UTC → naive): "
                        f"from={record.cert_valid_from}, to={record.cert_valid_to}, "
                        f"days={record.cert_days_to_expire}, expired={record.cert_is_expired}"
                    )
                except AttributeError as ae:
                    # Versiones antiguas de cryptography (sin _utc)
                    _logger.info(f"Cert {record.id}: Usando not_valid_before/after (sin _utc): {ae}")
                    # Estos ya son naive, solo asegurar que lo sean
                    valid_from = cert.not_valid_before
                    valid_to = cert.not_valid_after

                    # Si tienen tzinfo, quitarlo; si no, dejar como están
                    if hasattr(valid_from, "tzinfo") and valid_from.tzinfo is not None:
                        valid_from = valid_from.replace(tzinfo=None)
                    if hasattr(valid_to, "tzinfo") and valid_to.tzinfo is not None:
                        valid_to = valid_to.replace(tzinfo=None)

                    record.cert_valid_from = valid_from
                    record.cert_valid_to = valid_to

                    now = datetime.now()  # naive datetime local
                    record.cert_is_expired = valid_to < now
                    days_diff = (valid_to - now).days
                    record.cert_days_to_expire = days_diff if days_diff > 0 else 0

                    _logger.info(
                        f"Cert {record.id}: Fechas extraídas OK (fallback): "
                        f"from={record.cert_valid_from}, to={record.cert_valid_to}, "
                        f"days={record.cert_days_to_expire}"
                    )

                # Subject (DN)
                subject_parts = []
                for attr in cert.subject:
                    subject_parts.append(f"{attr.oid._name}={attr.value}")
                record.cert_subject = ", ".join(subject_parts)

                # Issuer
                issuer_parts = []
                for attr in cert.issuer:
                    issuer_parts.append(f"{attr.oid._name}={attr.value}")
                record.cert_issuer = ", ".join(issuer_parts)

                # Número de serie
                record.cert_serial_number = str(cert.serial_number)

                _logger.info(
                    f"✓ Certificado {record.id} procesado EXITOSAMENTE:\n"
                    f"  - Subject: {record.cert_subject}\n"
                    f"  - Serial: {record.cert_serial_number}\n"
                    f"  - Válido desde: {record.cert_valid_from}\n"
                    f"  - Válido hasta: {record.cert_valid_to}\n"
                    f"  - Días restantes: {record.cert_days_to_expire}\n"
                    f"  - Vencido: {record.cert_is_expired}"
                )

            except Exception as e:
                _logger.error(f"Error al extraer información del certificado {record.id}: {e}")
                _logger.error(traceback.format_exc())
                record.cert_valid_from = False
                record.cert_valid_to = False
                record.cert_subject = False
                record.cert_issuer = False
                record.cert_serial_number = False
                record.cert_is_expired = False
                record.cert_days_to_expire = 0

    def _validate_certificate_key_pair(self):
        """Valida que el certificado y la clave privada correspondan entre sí.

        Returns:
            tuple: (bool, str) - (es_válido, mensaje_error)
        """
        self.ensure_one()

        if not self.crt:
            return False, _("Falta el certificado")

        if not self.alias_id.key:
            return False, _("Falta la clave privada en el alias del certificado")

        try:
            import hashlib

            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key

            _logger.info("Validando par certificado-clave para certificado ID %s", self.id)

            # Cargar certificado
            try:
                cert = x509.load_pem_x509_certificate(self.crt.encode("utf-8"), default_backend())
                _logger.info("✓ Certificado cargado correctamente")
            except Exception as e:
                return False, _("Error al cargar el certificado: %s") % str(e)

            # Cargar clave privada
            try:
                pkey = load_pem_private_key(self.alias_id.key.encode("utf-8"), password=None, backend=default_backend())
                _logger.info("✓ Clave privada cargada correctamente")
            except ValueError as e:
                if "password" in str(e).lower():
                    return False, _(
                        "❌ La clave privada está protegida con contraseña.\n\n"
                        "AFIP requiere una clave privada SIN contraseña.\n\n"
                        "Para eliminar la contraseña ejecute:\n"
                        "openssl rsa -in clave_con_pass.key -out clave_sin_pass.key"
                    )
                else:
                    return False, _(
                        "❌ La clave privada no es válida o está en formato incorrecto.\n\n"
                        "Debe estar en formato PEM:\n"
                        "-----BEGIN PRIVATE KEY----- o -----BEGIN RSA PRIVATE KEY-----\n\n"
                        "Error: %s"
                    ) % str(e)
            except Exception as e:
                return False, _("❌ Error al cargar la clave privada: %s") % str(e)

            # Obtener claves públicas de ambos
            try:
                cert_public_key = cert.public_key()
                pkey_public_key = pkey.public_key()

                # Serializar a DER para comparación byte a byte
                cert_pub_bytes = cert_public_key.public_bytes(
                    encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo
                )
                pkey_pub_bytes = pkey_public_key.public_bytes(
                    encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo
                )

                # Calcular hashes para comparación y log
                cert_hash = hashlib.sha256(cert_pub_bytes).hexdigest()
                pkey_hash = hashlib.sha256(pkey_pub_bytes).hexdigest()

                _logger.info("Hash clave pública del certificado: %s", cert_hash)
                _logger.info("Hash clave pública de la clave privada: %s", pkey_hash)

                # Comparar
                if cert_pub_bytes != pkey_pub_bytes:
                    return False, _(
                        "❌ LA CLAVE PRIVADA NO CORRESPONDE A ESTE CERTIFICADO\n\n"
                        "Verificación criptográfica falló:\n"
                        "• Hash del certificado: %s...\n"
                        "• Hash de la clave privada: %s...\n\n"
                        "SOLUCIÓN:\n"
                        "Debe usar la MISMA clave privada que utilizó para generar el CSR.\n\n"
                        "Si no tiene la clave original, debe:\n"
                        "1. Generar una nueva clave privada\n"
                        "2. Generar un nuevo CSR con esa clave\n"
                        "3. Solicitar un nuevo certificado en AFIP\n"
                        "4. Subir ambos archivos (la nueva clave + el nuevo certificado)"
                    ) % (cert_hash[:16], pkey_hash[:16])

                _logger.info("✓ Certificado %s: Par clave-certificado VÁLIDO", self.id)
                return True, _(
                    "✅ Certificado y clave privada son un par válido\n\n" "Hash verificado: %s..."
                ) % cert_hash[:16]

            except Exception as e:
                _logger.exception("Error comparando claves públicas")
                return False, _("❌ Error al comparar claves públicas: %s") % str(e)

        except Exception as e:
            _logger.exception("Error inesperado validando certificado")
            return False, _("❌ Error inesperado: %s") % str(e)

    def test_wsaa_authentication(self):
        """Prueba la autenticación con AFIP WSAA usando este certificado.

        Returns:
            tuple: (bool, str) - (exitoso, mensaje)
        """
        self.ensure_one()

        if not self.crt:
            return False, _("Falta el certificado")

        # PASO 1: Validar SIEMPRE que el par certificado-clave privada sea correcto
        # Esta validación es criptográfica y funciona para cualquier certificado
        _logger.info("Validando par certificado-clave privada...")
        is_valid, msg = self._validate_certificate_key_pair()
        if not is_valid:
            _logger.error("❌ Par certificado-clave INVÁLIDO: %s", msg)
            self.write(
                {
                    "certificate_validated": False,
                    "validation_date": fields.Datetime.now(),
                    "validation_error": msg,
                }
            )
            return False, msg

        _logger.info("✓ Par certificado-clave VÁLIDO")

        # PASO 2: Detectar si es certificado de testing
        is_testing_cert = False
        if self.cert_issuer and ("test" in self.cert_issuer.lower() or "computadores test" in self.cert_issuer.lower()):
            is_testing_cert = True
            _logger.info("Certificado de testing detectado: %s", self.cert_issuer)

        # PASO 3: Si es testing en homologación, no intentar autenticar con AFIP
        env_type = self.alias_id.type
        if is_testing_cert and env_type == "homologation":
            _logger.warning("Certificado de testing en homologación - Omitiendo autenticación con AFIP")
            warning_msg = _(
                "⚠️ Certificado de Testing (Homologación)\n\n"
                "✅ El par certificado-clave privada es VÁLIDO (verificación criptográfica OK)\n\n"
                "Este es un certificado de prueba/testing para desarrollo.\n\n"
                "Información del certificado:\n"
                "• Emisor: %s\n"
                "• Ambiente: %s\n"
                "• Válido hasta: %s\n\n"
                "NOTA: Los certificados de testing no pueden validarse con AFIP real,\n"
                "pero son válidos para desarrollo y pruebas en ambiente de homologación.\n\n"
                "Para producción necesitará un certificado real de AFIP."
            ) % (self.cert_issuer or "N/A", env_type, self.cert_valid_to or "N/A")

            # Marcar como "validado" con advertencia en validation_error (NO mostrar mensaje largo)
            self.write(
                {
                    "certificate_validated": True,
                    "validation_date": fields.Datetime.now(),
                    "validation_error": warning_msg,  # Guardar el mensaje completo aquí
                }
            )

            return True, _("Certificado de testing validado. Ver detalles en campo de validación.")

        # PASO 4: Si es testing en producción, es error
        if is_testing_cert and env_type == "production":
            error_msg = _(
                "❌ Error: Certificado de Testing en Producción\n\n"
                "✅ El par certificado-clave privada es válido (verificación criptográfica OK)\n\n"
                "Pero NO puede usar un certificado de testing en ambiente de producción.\n\n"
                "Debe generar un certificado real de AFIP para producción:\n"
                "1. Use el script: ./generate_afip_certificate.sh <CUIT> produccion\n"
                "2. Suba el CSR a AFIP (ambiente Producción)\n"
                "3. Descargue y configure el certificado real"
            )
            self.write(
                {
                    "certificate_validated": False,
                    "validation_date": fields.Datetime.now(),
                    "validation_error": error_msg,
                }
            )
            return False, error_msg

        # PASO 5: Para certificados reales, intentar autenticar con AFIP
        _logger.info("Certificado real detectado - Intentando autenticación con AFIP...")

        services = [s.strip() for s in (self.afip_services or "wsfe").split("\n") if s.strip()]
        if not services:
            services = ["wsfe"]

        service_to_test = services[0]
        company = self.alias_id.company_id

        try:
            _logger.info("Probando autenticación WSAA para servicio '%s' (ambiente: %s)", service_to_test, env_type)

            # Verificar que el certificado esté confirmado en este ambiente
            if self.state != "confirmed":
                return False, _("El certificado debe estar confirmado antes de validarlo")

            # Obtener clave y certificado
            pkey = self.alias_id.key
            cert = self.crt

            if not pkey or not cert:
                return False, _("Faltan la clave privada o el certificado")

            # Intentar crear conexión directamente usando el método de la company
            # Esto forzará la autenticación con WSAA
            try:
                _logger.info("Creando conexión WSAA para validar certificado...")
                connection = company._create_connection(service_to_test, env_type)

                if connection and connection.token:
                    msg = _(
                        "✅ Autenticación WSAA exitosa\n\n"
                        "Servicio probado: %s\n"
                        "Ambiente: %s\n"
                        "Token obtenido: %s...\n"
                        "Expira: %s"
                    ) % (
                        service_to_test,
                        env_type,
                        (connection.token[:50] if connection.token else "N/A"),
                        (connection.expirationtime or "N/A"),
                    )

                    self.write(
                        {
                            "certificate_validated": True,
                            "validation_date": fields.Datetime.now(),
                            "validation_error": False,
                        }
                    )

                    return True, msg
                else:
                    error_msg = _(
                        "❌ Error en autenticación WSAA\n\n"
                        "No se pudo obtener token válido.\n"
                        "La conexión se creó pero no tiene token."
                    )

                    self.validation_error = error_msg
                    return False, error_msg

            except UserError as ue:
                # UserError contiene mensajes claros del sistema
                _logger.error("UserError en validación WSAA: %s", ue.args[0] if ue.args else str(ue))

                # Para certificados reales que fallan, mostrar error completo
                error_msg = _(
                    "❌ Error de validación AFIP\n\n%s\n\n"
                    "Posibles causas:\n"
                    "- El servicio '%s' no está adherido en AFIP para este certificado\n"
                    "- El ambiente configurado (%s) no coincide con el del certificado\n"
                    "- La clave privada no corresponde al certificado (Firma inválida)\n"
                    "- El certificado está vencido o no es válido aún"
                ) % (ue.args[0] if ue.args else str(ue), service_to_test, env_type)

                self.validation_error = error_msg
                return False, error_msg

            except Exception as conn_error:
                _logger.exception("Error en conexión WSAA")

                # Si es certificado de testing en homologación, solo advertir
                if is_testing_cert and env_type == "homologation":
                    warning_msg = _(
                        "⚠️ Certificado de Testing (Homologación)\n\n"
                        "Este es un certificado de prueba para desarrollo.\n"
                        "Válido para ambiente de homologación.\n\n"
                        "Emisor: %s\n"
                        "Válido hasta: %s"
                    ) % (self.cert_issuer or "N/A", self.cert_valid_to or "N/A")

                    self.write(
                        {
                            "certificate_validated": True,
                            "validation_date": fields.Datetime.now(),
                            "validation_error": warning_msg,
                        }
                    )

                    return True, warning_msg

                error_msg = _(
                    "❌ Error al conectar con AFIP WSAA\n\n"
                    "Error: %s\n\n"
                    "Posibles causas:\n"
                    "- Problemas de conectividad con AFIP\n"
                    "- El servicio WSAA no está disponible\n"
                    "- Error en la configuración del certificado"
                ) % str(conn_error)

                self.validation_error = error_msg
                return False, error_msg

        except Exception as e:
            error_msg = _("❌ Error al probar autenticación: %s") % str(e)
            _logger.exception("Error probando WSAA")
            self.validation_error = error_msg
            return False, error_msg

    def action_validate_certificate(self):
        """Acción para validar el certificado desde la interfaz."""
        self.ensure_one()

        # Primero validar el par criptográfico
        is_valid, msg = self._validate_certificate_key_pair()
        if not is_valid:
            raise UserError(msg)

        # Luego probar WSAA (o validar si es testing)
        success, msg = self.test_wsaa_authentication()

        notification_type = "success" if success else "danger"

        # Si es certificado de testing validado, usar tipo warning y mensaje breve
        if success and self.validation_error and "Testing" in self.validation_error:
            notification_type = "warning"
            msg = _("Certificado de testing validado. Ver detalles en 'ERROR DE VALIDACIÓN'.")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Validación de Certificado"),
                "message": msg,
                "type": notification_type,
                "sticky": False,  # Cambiar a False para que no sea pegajoso
            },
        }

    def action_to_draft(self):
        if self.alias_id.state != "confirmed":
            raise UserError(_("Certificate Alias must be confirmed first!"))
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    def action_confirm(self):
        """Confirmar certificado y calcular información de vencimiento."""
        self.ensure_one()

        _logger.info("==== ACTION_CONFIRM: Certificado ID %s ====", self.id)
        _logger.info("Estado antes: %s, Tiene CRT: %s", self.state, bool(self.crt))

        if self.crt:
            _logger.info("Longitud CRT: %s, Primeros 50 chars: %s...", len(self.crt), self.crt[:50])

        # Verificar el certificado
        self.verify_crt()
        _logger.info("verify_crt() completado OK")

        # CRÍTICO: El @api.depends("crt") no se dispara si el CRT ya estaba escrito
        # Por eso DEBEMOS forzar el cálculo manualmente aquí
        _logger.info("Forzando _compute_cert_info() manualmente...")
        self._compute_cert_info()

        # Leer valores DESPUÉS del compute forzado
        _logger.info(
            "Valores DESPUÉS de compute forzado: valid_to=%s, days_to_expire=%s, is_expired=%s",
            self.cert_valid_to,
            self.cert_days_to_expire,
            self.cert_is_expired,
        )

        # Cambiar estado
        self.write({"state": "confirmed"})
        _logger.info("Estado cambiado a 'confirmed'")

        # Log de información del certificado confirmado
        if self.cert_valid_to:
            _logger.info(
                "✓ Certificado confirmado OK: Alias=%s, Vencimiento=%s, Días restantes=%s",
                self.alias_id.common_name,
                self.cert_valid_to,
                self.cert_days_to_expire,
            )

            # Advertencia si el certificado ya está vencido o vence pronto
            if self.cert_is_expired:
                _logger.warning(
                    "⚠️ ADVERTENCIA: El certificado '%s' YA ESTÁ VENCIDO (venció el %s)",
                    self.alias_id.common_name,
                    self.cert_valid_to,
                )
            elif self.cert_days_to_expire < 30:
                _logger.warning(
                    "⚠️ ADVERTENCIA: El certificado '%s' vence en %s días (%s)",
                    self.alias_id.common_name,
                    self.cert_days_to_expire,
                    self.cert_valid_to,
                )
        else:
            _logger.error("❌ ERROR: cert_valid_to está vacío después del compute. Revisar _compute_cert_info()")

        return True

    def verify_crt(self):
        """
        Verify if certificate is well formed
        """
        for rec in self:
            crt = rec.crt
            msg = False

            if not crt:
                msg = _("Invalid action! Please, set the certification string to " "continue.")
            certificate = rec.get_certificate()
            if certificate is None:
                msg = _(
                    "Invalid action! Your certificate string is invalid. "
                    "Check if you forgot the header CERTIFICATE or forgot/ "
                    "append end of lines."
                )
            if msg:
                raise UserError(msg)
        return True

    def get_certificate(self):
        """
        Return Certificate object.
        """
        self.ensure_one()
        if self.crt:
            try:
                certificate = crypto_utils.load_certificate(self.crt)
            except ValueError as e:
                error_msg = str(e)
                if "CERTIFICATE" in error_msg:
                    raise UserError(
                        _(
                            "Wrong Certificate file format.\nBe sure you have "
                            "BEGIN CERTIFICATE string in your first line."
                        )
                    )
                else:
                    raise UserError(_("Unknown error.\nCertificate validation failed:\n %s") % error_msg)
            except Exception as e:
                raise UserError(_("Error loading certificate:\n %s") % str(e))
        else:
            certificate = None
        return certificate
