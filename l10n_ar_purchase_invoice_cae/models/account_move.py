import logging
from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from pysimplesoap.client import SoapFault
except ImportError:
    _logger.debug('Can not `from pyafipws.soap import SoapFault`.')


class AccountMove(models.Model):
    _inherit = 'account.move'

    def verify_cae(self):
        """
        Método para constatar un comprobante de compra en AFIP
        """
        afip_ws = "wscdc"
        ws = self.company_id.get_connection(afip_ws).connect()
        for inv in self:
            cbte_modo = inv.afip_auth_mode
            cod_autorizacion = inv.afip_auth_code
            if not cbte_modo or not cod_autorizacion:
                raise UserError(_('AFIP authorization mode and Code are required!'))

            # get issuer and receptor depending on supplier or customer invoice
            if inv.move_type in ['in_invoice', 'in_refund']:
                issuer = inv.commercial_partner_id
                receptor = inv.company_id.partner_id
            else:
                issuer = inv.company_id.partner_id
                receptor = inv.commercial_partner_id

            cuit_emisor = issuer.vat  # TODO modificar para asegurar que sea CUIT

            receptor_doc_code = str(receptor.l10n_latam_identification_type_id.l10n_ar_afip_code)
            doc_tipo_receptor = receptor_doc_code or '99'
            doc_nro_receptor = (
                receptor_doc_code and receptor.vat or "0")
            doc_type = inv.l10n_latam_document_type_id
            if (doc_type.l10n_ar_letter in ['A', 'M'] and doc_tipo_receptor != '80' or not doc_nro_receptor):
                raise UserError(_(
                    'Para Comprobantes tipo A o tipo M:\n'
                    '*  el documento del receptor debe ser CUIT\n'
                    '*  el documento del Receptor es obligatorio\n'
                ))

            number_parts = self._l10n_ar_get_document_number_parts(
                self.l10n_latam_document_number, self.l10n_latam_document_type_id.code
            )
            cbte_nro = number_parts['point_of_sale']
            pto_vta = number_parts['invoice_number']

            cbte_tipo = doc_type.code
            if not pto_vta or not cbte_nro or not cbte_tipo:
                raise UserError(_('Point of sale and document number and document type are required!'))
            cbte_fch = inv.invoice_date
            if not cbte_fch:
                raise UserError(_('Invoice Date is required!'))
            cbte_fch = cbte_fch.replace("-", "")
            imp_total = str("%.2f" % inv.amount_total_signed)

            _logger.info('Constatando Comprobante en afip')

            # atrapado de errores en afip
            msg = False
            try:
                ws.ConstatarComprobante(
                    cbte_modo, cuit_emisor, pto_vta, cbte_tipo, cbte_nro,
                    cbte_fch, imp_total, cod_autorizacion, doc_tipo_receptor,
                    doc_nro_receptor)
            except SoapFault as fault:
                msg = 'Falla SOAP %s: %s' % (fault.faultcode, fault.faultstring)
            except Exception as e:
                msg = e
            except Exception:
                if ws.Excepcion:
                    # get the exception already parsed by the helper
                    msg = ws.Excepcion
                # else:
                #     # avoid encoding problem when raising error
                #     msg = traceback.format_exception_only(sys.exc_type, sys.exc_value)[0]
            if msg:
                raise UserError(_('AFIP Verification Error. %s' % msg))

            inv.write({
                'afip_result': ws.Resultado,
                'afip_message': '%s%s' % (ws.Obs, ws.ErrMsg)
            })
