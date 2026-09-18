from lxml import etree


def _get_response_info(xml_response):
    if isinstance(xml_response, bytes):
        xml_response = xml_response.decode("utf-8", "ignore")
    return etree.fromstring(xml_response.encode("utf-8"))


def _find_first_text(root, tag):
    """Busca primer nodo cuyo tag local sea `tag` (ignora namespaces)."""
    found = root.xpath('//*[local-name()=$name]', name=tag)
    if found and found[0].text:
        return found[0].text.strip()
    return False


def get_invoice_number_from_response(xml_response, afip_ws='wsfe'):
    if not xml_response:
        return False
    try:
        root = _get_response_info(xml_response)
        # wsfe/wsbfe/wsmtxca usan CbteDesde; wsfex usa CbteNro/Id según método
        for tag in ("CbteDesde", "CbteNro", "Cbte_nro"):
            number = _find_first_text(root, tag)
            if number:
                return int(number)
        return False
    except Exception:
        return False


def check_invoice_number(account_move):
    pass
