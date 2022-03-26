from odoo import fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
import sys
import traceback
import logging
_logger = logging.getLogger(__name__)

try:
    from pysimplesoap.client import SoapFault
except ImportError:
    _logger.debug('Can not `from pyafipws.soap import SoapFault`.')


class AccountMove(models.Model):
    _inherit = 'account.move'

    caea_id = fields.Many2one(
        'afipws.caea',
        string='Caea',
        copy=False
    )
    caea_post_datetime = fields.Datetime(
        string='CAEA post datetime',
    )
    l10n_ar_afip_caea_reported = fields.Boolean(
        string='Caea Reported',
    )

    def get_pyafipws_last_invoice(self, document_type):
        if self.journal_id.l10n_ar_afip_pos_system == 'CAEA':
            return self._l10n_ar_get_document_number_parts(self.l10n_latam_document_number,
                                                           self.l10n_latam_document_type_id.code)['invoice_number']
        else:
            return super().get_pyafipws_last_invoice(document_type)

    def post(self):
        caea_state = self.env['ir.config_parameter'].sudo().get_param(
            'afip.ws.caea.state', 'inactive')
        if caea_state == 'active':
            inv_ids = self.filtered(
                lambda record: record.journal_id.l10n_ar_afip_pos_system != 'CAEA')
            for inv in inv_ids:
                if len(inv.journal_id.caea_journal_id):
                    inv.journal_id = inv.journal_id.caea_journal_id.id

        res = super().post()
        return res

    def do_pyafipws_request_cae(self):
        caea_state = self.env['ir.config_parameter'].sudo().get_param(
            'afip.ws.caea.state', 'inactive')
        if caea_state == 'inactive':
            return super().do_pyafipws_request_cae()
        elif caea_state == 'active':
            return self.do_pyafipws_request_caea()

    def do_pyafipws_request_caea(self):
        for inv in self:
            if inv.journal_id.l10n_ar_afip_pos_system != 'CAEA':
                continue
            # Ignore invoices with cae (do not check date)
            if inv.afip_auth_code:
                continue

            afip_ws = inv.journal_id.afip_ws
            if not afip_ws:
                continue

            # Ignore invoice if not ws on point of sale
            if not afip_ws:
                raise UserError(_(
                    'If you use electronic journals (invoice id %s) you need '
                    'configure AFIP WS on the journal') % (inv.id))

            active_caea = inv.company_id.get_active_caea()
            if len(active_caea):
                msg = (
                    _('Afip conditional validation (CAEA %s)') % active_caea.name)
                inv.write({
                    'afip_auth_mode': 'CAEA',
                    'afip_auth_code': active_caea.name,
                    'afip_auth_code_due': inv.invoice_date,
                    'afip_result': '',
                    'afip_message': msg,
                    'caea_post_datetime': fields.Datetime.now(),
                    'caea_id': active_caea.id
                })
                inv.message_post(body=msg)
                continue
            else:
                raise UserError(_('The company does not have active CAEA'))

    def do_pyafipws_post_caea_invoice(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        for inv in self:
            # Ignore invoices without caea
            if inv.afip_auth_mode != 'CAEA':
                continue
            afip_ws = inv.company_id.get_caea_ws() 
            if not afip_ws:
                continue

            # Ignore invoice if not ws on point of sale
            if not afip_ws:
                raise UserError(_(
                    'If you use electronic journals (invoice id %s) you need '
                    'configure AFIP WS on the journal') % (inv.id))

            # Inicio conexion
            ws = inv.company_id.get_connection(afip_ws).connect()

            # Preparo los datos
            invoice_info = inv.map_invoice_info(afip_ws)
            invoice_info['caea'] = inv.afip_auth_code
            invoice_info['CbteFchHsGen'] = inv.caea_post_datetime.strftime('%Y%m%d%H%M%S')

            # Creo la factura en el ambito de pyafipws
            inv.wsfe_pyafipws_caea_create_invoice(ws, invoice_info)

            # Agrego informacion a la factura dentro de pyafipws
            inv.pyafipws_add_info(ws, afip_ws, invoice_info)

            # Request the authorization! (call the AFIP webservice method)
            vto = None
            msg = False
            try:
                inv.wsfe_caea_request_autorization(ws, afip_ws)

            except SoapFault as fault:
                msg = 'Falla SOAP %s: %s' % (
                    fault.faultcode, fault.faultstring)
            except Exception as e:
                msg = e
            except Exception:
                if ws.Excepcion:
                    # get the exception already parsed by the helper
                    msg = ws.Excepcion
                else:
                    # avoid encoding problem when   raising error
                    msg = traceback.format_exception_only(
                        sys.exc_type,
                        sys.exc_value)[0]

            if msg:
                _logger.info(_('AFIP Validation Error. %s' % msg) + ' XML Request: %s XML Response: %s' % (
                    ws.XmlRequest, ws.XmlResponse))
                raise UserError(_('AFIP Validation Error. %s' % msg))

            msg = u"\n".join([ws.Obs or "", ws.ErrMsg or ""])
            if not ws.CAEA or ws.Resultado != 'A':

                raise UserError(_('AFIP Validation Error. %s' % msg))
            # TODO ver que algunos campos no tienen sentido porque solo se
            # escribe aca si no hay errores
            _logger.info('CAEA solicitado con exito. %s. Resultado %s' % (afip_auth_code, ws.Resultado))
            if hasattr(ws, 'Vencimiento'):
                vto = datetime.strptime(ws.Vencimiento, '%Y%m%d').date()
            if hasattr(ws, 'FchVencCAE'):
                vto = datetime.strptime(ws.FchVencCAE, '%Y%m%d').date()


            inv.write({
                'afip_auth_code_due': vto,
                'afip_result': ws.Resultado,
                'afip_message': msg,
                'afip_xml_request': ws.XmlRequest,
                'afip_xml_response': ws.XmlResponse,
                'l10n_ar_afip_caea_reported': True
            })

            inv._cr.commit()
