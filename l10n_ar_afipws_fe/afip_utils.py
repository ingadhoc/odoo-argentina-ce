from lxml import etree


def _get_response_info(xml_response):
    """Parsea XML response de AFIP."""
    if isinstance(xml_response, str):
        return etree.fromstring(xml_response.encode("utf-8"))
    return etree.fromstring(xml_response)


def get_invoice_number_from_response(xml_response, afip_ws="wsfe"):
    """
    Extrae el número de comprobante del XML response de AFIP.

    NOTA: Con el nuevo cliente zeep, esta función no se usa mucho
    porque el resultado ya viene parseado como dict.
    """
    if not xml_response:
        return False
    try:
        root = _get_response_info(xml_response)

        # Buscar CbteDesde en el XML (sin namespace)
        # Funciona para WSFEv1, WSFEX, etc.
        cbte_desde = root.find(".//{*}CbteDesde")
        if cbte_desde is not None:
            return int(cbte_desde.text)

        # Fallback: buscar en cualquier nivel
        for elem in root.iter():
            if elem.tag.endswith("CbteDesde") and elem.text:
                return int(elem.text)

        return False
    except Exception:
        return False


def check_invoice_number(account_move):
    pass
