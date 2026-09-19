##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
"""Helpers compartidos para conexión AFIP vía zeep (sin pyafipws).

Port del tipo de conexión de l10n_ar_afip_fe (Pronexo, 15.0) a 17.0,
manteniendo nombres de modelos/campos de adhoc (afipws.connection)
para facilitar el PR a ingadhoc/odoo-argentina-ce.

Incorpora (adaptado, sin reestructurar a lib/) lo útil de
trixocom/odoo-argentina-trx-ce `l10n_ar_afip_ws`:
* Transporte con ciphers sin DH (bug TLS AFIP), caché WSDL sqlite con TTL,
  timeouts separados load/operation y captura de XML en `post` y `post_xml`.
* TRA con timestamps TZ-aware Argentina (-03:00) y uniqueId uint32-safe.
* Parse de LoginTicketResponse con generation/expiration/source.
* Margen de renovación del TA (ver `res_company.get_connection`).

Claves que se mantienen:
* TRA + CMS con `cryptography` (vía pública, sin APIs privadas de pyOpenSSL).
* Mapa de WSDLs homo/producción por servicio.
* Firmas públicas intactas para no romper el PR (mismos nombres).
"""
import base64
import logging
import os
import tempfile
import threading
import datetime

from lxml import builder, etree

_logger = logging.getLogger(__name__)

# Mapa idProvincia AFIP -> nombre (para padrón A4/A5 vía zeep).
# Fuente: pyafipws/padron.py PROVINCIAS (subset necesario para res_partner).
PROVINCIAS = {
    0: "CIUDAD AUTONOMA BUENOS AIRES",
    1: "BUENOS AIRES",
    2: "CATAMARCA",
    3: "CORDOBA",
    4: "CORRIENTES",
    5: "ENTRE RIOS",
    6: "JUJUY",
    7: "MENDOZA",
    8: "LA RIOJA",
    9: "SALTA",
    10: "SAN JUAN",
    11: "SAN LUIS",
    12: "SANTA FE",
    13: "SANTIAGO DEL ESTERO",
    14: "TUCUMAN",
    16: "CHACO",
    17: "CHUBUT",
    18: "FORMOSA",
    19: "MISIONES",
    20: "NEUQUEN",
    21: "LA PAMPA",
    22: "RIO NEGRO",
    23: "SANTA CRUZ",
    24: "TIERRA DEL FUEGO",
}

# Transporte (port trixocom/lib/transport.py, adaptado sin reestructurar)
AFIP_CIPHERS = "DEFAULT:!DH"
DEFAULT_LOAD_TIMEOUT = 15
DEFAULT_OPERATION_TIMEOUT = 60
DEFAULT_WSDL_CACHE_TTL = 7 * 24 * 3600
WSDL_CACHE_FILENAME = "afip_wsdl_cache.db"

# Margen de seguridad: renovar el TA si le quedan menos minutos (trixocom: 10)
TA_RENEWAL_MARGIN_MINUTES = 10

_cache_lock = threading.Lock()
_shared_cache = None
_shared_cache_path = None


class ARTransportLog:
    """Mixin mínimo para guardar xml de zeep sin depender del Transport real en tests."""

    xml_request = ""
    xml_response = ""


def get_wsdl_cache_path(data_dir=None):
    base = data_dir or os.environ.get("ODOO_DATA_DIR")
    if not base:
        try:
            from odoo.tools import config as _odoo_config

            base = _odoo_config.get("data_dir")
        except Exception:
            base = None
    if not base:
        base = tempfile.gettempdir()
    return os.path.join(base, WSDL_CACHE_FILENAME)


def get_wsdl_cache(data_dir=None, ttl=DEFAULT_WSDL_CACHE_TTL):
    """Caché WSDL compartida por proceso. Devuelve None si no se puede (degrada sin romper)."""
    global _shared_cache, _shared_cache_path
    try:
        from zeep.cache import SqliteCache
    except ImportError:
        return None
    path = get_wsdl_cache_path(data_dir=data_dir)
    with _cache_lock:
        if _shared_cache is not None and _shared_cache_path == path:
            return _shared_cache
        try:
            cache = SqliteCache(path=path, timeout=ttl)
        except Exception as e:
            _logger.warning(
                "AFIP: no pude abrir cache WSDL en %s (%s), sigo sin cache.", path, e
            )
            return None
        _shared_cache = cache
        _shared_cache_path = path
        _logger.info("AFIP: cache WSDL en %s (ttl %ss)", path, ttl)
        return cache


def build_afip_session():
    from requests import Session
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context

    class AfipHTTPAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            context = create_urllib3_context(ciphers=AFIP_CIPHERS)
            kwargs["ssl_context"] = context
            return super().init_poolmanager(*args, **kwargs)

        def proxy_manager_for(self, *args, **kwargs):
            context = create_urllib3_context(ciphers=AFIP_CIPHERS)
            kwargs["ssl_context"] = context
            return super().proxy_manager_for(*args, **kwargs)

    session = Session()
    session.mount("https://", AfipHTTPAdapter())
    return session


def make_zeep_client(wsdl, log_xml=True, data_dir=None, use_cache=True):
    """Crea zeep.Client con adapter AFIP, caché WSDL y logging de XML (misma firma que antes)."""
    import zeep
    from zeep import transports

    cache = get_wsdl_cache(data_dir=data_dir) if use_cache else None
    session = build_afip_session()
    kwargs = dict(
        session=session,
        timeout=DEFAULT_LOAD_TIMEOUT,
        operation_timeout=DEFAULT_OPERATION_TIMEOUT,
    )
    if cache is not None:
        kwargs["cache"] = cache

    if not log_xml:
        transport = transports.Transport(**kwargs)
        return zeep.Client(wsdl, transport=transport), transport

    class ARTransport(transports.Transport):
        def _store(self, message, response):
            try:
                data = message if isinstance(message, bytes) else etree.tostring(message, pretty_print=True)
                self.xml_request = etree.tostring(
                    etree.fromstring(data), pretty_print=True
                ).decode("utf-8")
            except Exception:
                self.xml_request = message.decode("utf-8", "ignore") if isinstance(message, bytes) else str(message)
            try:
                self.xml_response = etree.tostring(
                    etree.fromstring(response.content), pretty_print=True
                ).decode("utf-8")
            except Exception:
                try:
                    self.xml_response = response.text
                except Exception:
                    self.xml_response = ""

        def post(self, address, message, headers):
            response = super().post(address, message, headers)
            self._store(message, response)
            return response

        def post_xml(self, address, envelope, headers):
            from lxml import etree as _etree

            try:
                raw = _etree.tostring(envelope, pretty_print=True)
            except Exception:
                raw = b""
            response = super().post_xml(address, envelope, headers)
            self._store(raw, response)
            return response

    transport = ARTransport(**kwargs)
    return zeep.Client(wsdl, transport=transport), transport


WSAA_WSDL = {
    "production": "https://wsaa.afip.gov.ar/ws/services/LoginCms?WSDL",
    "testing": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL",
    # Nombres legacy usados en adhoc ("homologation" == "testing")
    "homologation": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?WSDL",
}

# WSDLs base (padrón + MiPyME). Los de FE (wsfe/wsfex/wsbfe/wscdc) los
# extiende l10n_ar_afipws_fe manteniendo este mismo formato.
AFIP_WSDL_MAP = {
    "ws_sr_padron_a4": {
        "production": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA4?wsdl",
        "homologation": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA4?wsdl",
        "testing": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA4?wsdl",
    },
    "ws_sr_constancia_inscripcion": {
        "production": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5?wsdl",
        "homologation": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5?wsdl",
        "testing": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5?wsdl",
    },
    "ws_sr_padron_a10": {
        "production": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA10?wsdl",
        "homologation": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA10?wsdl",
        "testing": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA10?wsdl",
    },
    "ws_sr_padron_a100": {
        "production": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA100?wsdl",
        "homologation": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA100?wsdl",
        "testing": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA100?wsdl",
    },
    "wsfecred": {
        "production": "https://serviciosjava.afip.gob.ar/wsfecred/FECredService?wsdl",
        "homologation": "https://fwshomo.afip.gov.ar/wsfecred/FECredService?wsdl",
        "testing": "https://fwshomo.afip.gov.ar/wsfecred/FECredService?wsdl",
    },
}


def get_wsaa_wsdl(environment_type):
    return WSAA_WSDL.get(environment_type or "production")


def get_afip_ws_url(afip_ws, environment_type):
    return AFIP_WSDL_MAP.get(afip_ws, {}).get(environment_type or "production")


def normalize_env(environment_type):
    """Adhoc usa production/homologation, zeep-ref usa production/testing."""
    if environment_type == "testing":
        return "homologation"
    return environment_type or "production"


def _afip_now_tz():
    """Ahora en TZ Argentina (UTC-3), como pide AFIP (port trixocom wsaa)."""
    tz_ar = datetime.timezone(datetime.timedelta(hours=-3))
    return datetime.datetime.now(tz_ar)


def _afip_iso(dt):
    base = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    if len(base) >= 5 and base[-5] in ("+", "-"):
        base = base[:-2] + ":" + base[-2:]
    return base


def build_tra(service, ttl=43200):
    """Arma el Ticket de Requerimiento de Acceso (TRA) como bytes XML.

    TTL default 12h (uso adhoc). uniqueId uint32-safe: epoch en segundos
    (no multiplicar por 1000, desborda y AFIP rechaza contra schema).
    """
    now = _afip_now_tz()
    exp = now + datetime.timedelta(seconds=ttl)
    unique_id = str(int(now.timestamp()))
    request_xml = builder.E.loginTicketRequest(
        {"version": "1.0"},
        builder.E.header(
            builder.E.uniqueId(unique_id),
            builder.E.generationTime(_afip_iso(now)),
            builder.E.expirationTime(_afip_iso(exp)),
        ),
        builder.E.service(service),
    )
    return etree.tostring(request_xml, pretty_print=True), unique_id


def sign_tra_cms(tra_xml, pkey_pem, cert_pem):
    """Firma el TRA con CMS/PKCS7 y devuelve bytes DER.

    Usa `cryptography` (vía pública). Acepta str o bytes en PEM.
    Misma API que `certificate` Odoo 19 pero sin ese módulo (17).
    """
    if isinstance(pkey_pem, str):
        pkey_pem = pkey_pem.encode("utf-8")
    if isinstance(cert_pem, str):
        cert_pem = cert_pem.encode("utf-8")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    private_key = serialization.load_pem_private_key(pkey_pem, password=None)
    certificate = x509.load_pem_x509_certificate(cert_pem)
    options = [pkcs7.PKCS7Options.Binary]
    builder_cms = pkcs7.PKCS7SignatureBuilder().set_data(tra_xml)
    builder_cms = builder_cms.add_signer(certificate, private_key, hashes.SHA256())
    return builder_cms.sign(serialization.Encoding.DER, options)


def parse_login_response(response_xml):
    """Extrae token/sign de la respuesta loginCms (str XML)."""
    root = etree.fromstring(response_xml.encode("utf-8"))
    token = root.xpath("/loginTicketResponse/credentials/token")[0].text
    sign = root.xpath("/loginTicketResponse/credentials/sign")[0].text
    return token, sign


def parse_login_ticket_response(xml_bytes):
    """Parse completo tipo trixocom: token/sign/generation/expiration/source (UTC naive)."""
    if isinstance(xml_bytes, str):
        xml_bytes = xml_bytes.encode("utf-8")
    root = etree.fromstring(xml_bytes)

    def _text(xpath):
        found = root.find(xpath)
        if found is None or found.text is None:
            raise ValueError("Falta %r en LoginTicketResponse" % xpath)
        return found.text.strip()

    def _parse_dt(value):
        dt = datetime.datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt

    source = root.find("header/source")
    return {
        "token": _text("credentials/token"),
        "sign": _text("credentials/sign"),
        "generation_time": _parse_dt(_text("header/generationTime")),
        "expiration_time": _parse_dt(_text("header/expirationTime")),
        "source_cuit": source.text.strip() if source is not None and source.text else None,
    }


def login_cms_zeep(service, pkey_pem, cert_pem, environment_type, ttl=43200):
    """Login WSAA vía zeep. Devuelve dict listo para afipws.connection.

    No usa cache en disco (el reuso lo hace res.company.get_connection
    contra los registros en DB, TTL 12h como la referencia 15).
    """
    environment_type = normalize_env(environment_type)
    tra_xml, unique_id = build_tra(service, ttl=ttl)
    cms_der = sign_tra_cms(tra_xml, pkey_pem, cert_pem)
    cms_b64 = base64.b64encode(cms_der).decode("utf-8")
    wsdl = get_wsaa_wsdl(environment_type)
    _logger.info("Connect to AFIP WSAA to get token: %s (%s)", service, environment_type)
    client, transport = make_zeep_client(wsdl)
    response = client.service.loginCms(cms_b64)
    if isinstance(response, bytes):
        response = response.decode("utf-8")
    parsed = parse_login_ticket_response(response)
    return {
        "uniqueid": unique_id,
        "generationtime": parsed["generation_time"],
        "expirationtime": parsed["expiration_time"],
        "token": parsed["token"],
        "sign": parsed["sign"],
    }
