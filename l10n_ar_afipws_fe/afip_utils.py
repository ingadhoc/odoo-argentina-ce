from pysimplesoap.client import SimpleXMLElement
#import xml.etree.ElementTree as ET

def _get_response_info(xml_response):
    return SimpleXMLElement(xml_response)


def get_invoice_number_from_response(xml_response, afip_ws='wsfe'):
    if not xml_response:
        return  False
    try:
        xml = _get_response_info(xml_response)
        return int(xml('CbteDesde'))
        # TODO por ahora usamos pysimplesoap porque es mas comodo
        # Sino generar una estrategia recusiva para todos los tipos de WS
        # namespaces = {
        #     'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
        #     'a': NS[afip_ws],
        # }
        # root = _get_response_info(xml_response)
        # number = root.findall('./soap:Body'
        #                '/a:FECAESolicitarResponse'
        #                '/a:FECAESolicitarResult'
        #                '/a:FeDetResp'
        #                '/a:FECAEDetResponse'
        #                '/a:CbteDesde' , namespaces)[0].text
        # return int(number)
    except:
        return  False


def check_invoice_number(account_move):
    pass
