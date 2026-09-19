##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# Ported (and adapted to 17.0 / AGPL-3) from
# trixocom/odoo-argentina-trx-ce l10n_ar_iva_simple/lib/csv_format.py (LGPL-3).
"""Helpers de formateo para los CSV del régimen IVA Simple AFIP/ARCA.

Convención AFIP de los CSV de IVA Simple:

* Encoding: ``ISO-8859-1`` (Latin-1).
* Separador de campos: ``;`` (punto y coma).
* Decimales: ``,`` (coma) — ej: ``"123,45"``.
* Sin separador de miles.
* Negativos: prefijo ``-`` (pero AFIP suele esperar valor absoluto;
  el signo se da por el tipo de archivo: DEBITO/REST_DEBITO/CREDITO/REST_CREDITO).
* Newline: ``\\n`` (LF). Se usa ``DictWriter(lineterminator='\\n')``.

Lib pura — no importa ``odoo``. Testeable aislado.
"""
import io
from csv import DictWriter
from decimal import Decimal, ROUND_HALF_UP


def transform_value(value):
    """Normaliza un valor para escribir en el CSV.

    * ``None`` → ``""``.
    * ``int``/``float``/``Decimal`` → string con coma como separador
      decimal y punto removido. Si negativo, se devuelve el valor
      absoluto (AFIP infiere el signo por el archivo).
    * ``str`` → tal cual.

    >>> transform_value(123.45)
    '123,45'
    >>> transform_value(-123.45)
    '123,45'
    >>> transform_value(0)
    '0'
    >>> transform_value(None)
    ''
    >>> transform_value("ABC")
    'ABC'
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)):
        if value < 0:
            value = -value
        # Forzamos 2 decimales fijos con HALF_UP (spec ARCA: importes
        # siempre con 2 decimales, ej. "100,00", no "100" ni "100,5").
        d = Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        return format(d, "f").replace(".", ",")
    return str(value)


def rows_to_csv_bytes(headers, rows):
    """Convierte una lista de dicts en bytes CSV (latin-1, ; LF).

    :param headers: lista de strings con los nombres de columna en orden.
    :param rows: lista de dicts. Las keys deben coincidir con `headers`.
    :return: bytes en latin-1 listo para escribir a archivo o ZIP.
    """
    buf = io.StringIO()
    writer = DictWriter(
        buf, fieldnames=headers, delimiter=";", lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        out = {h: transform_value(row.get(h)) for h in headers}
        writer.writerow(out)
    text = buf.getvalue()
    return text.encode("latin-1", errors="replace")
