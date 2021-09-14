##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
# from typing_extensions import Annotated
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools import float_repr
import base64
import json
import logging
import sys
import traceback
from datetime import datetime
_logger = logging.getLogger(__name__)

try:
    from pysimplesoap.client import SoapFault
except ImportError:
    _logger.debug('Can not `from pyafipws.soap import SoapFault`.')


class AccountMove(models.Model):
    _inherit = "account.move"

    afip_auth_mode = fields.Selection([
        ('CAE', 'CAE'), ('CAI', 'CAI'), ('CAEA', 'CAEA')],
        string='AFIP authorization mode',
        copy=False,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    afip_auth_code = fields.Char(
        copy=False,
        string='CAE/CAI/CAEA Code',
        readonly=True,
        size=24,
        states={'draft': [('readonly', False)]},
    )
    afip_auth_code_due = fields.Date(
        copy=False,
        readonly=True,
        string='CAE/CAI/CAEA due Date',
        states={'draft': [('readonly', False)]},
    )
    afip_qr_code = fields.Char(
        compute='_compute_qr_code',
        string='AFIP QR code'
    )
    afip_message = fields.Text(
        string='AFIP Message',
        copy=False,
    )
    afip_xml_request = fields.Text(
        string='AFIP XML Request',
        copy=False,
    )
    afip_xml_response = fields.Text(
        string='AFIP XML Response',
        copy=False,
    )
    afip_result = fields.Selection([
        ('', 'n/a'),
        ('A', 'Aceptado'),
        ('R', 'Rechazado'),
        ('O', 'Observado')],
        'Resultado',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=False,
        help="AFIP request result"
    )
    validation_type = fields.Char(
        'Validation Type',
        compute='_compute_validation_type',
    )
    afip_fce_es_anulacion = fields.Boolean(
        string='FCE: Es anulacion?',
        help='Solo utilizado en comprobantes MiPyMEs (FCE) del tipo débito o crédito. Debe informar:\n'
        '- SI: sí el comprobante asociado (original) se encuentra rechazado por el comprador\n'
        '- NO: sí el comprobante asociado (original) NO se encuentra rechazado por el comprador'
    )

    @api.depends('journal_id', 'afip_auth_code')
    def _compute_validation_type(self):
        for rec in self:
            if rec.journal_id.afip_ws and not rec.afip_auth_code:
                validation_type = self.env[
                    'res.company']._get_environment_type()
                # if we are on homologation env and we dont have certificates
                # we validate only locally
                if validation_type == 'homologation':
                    try:
                        rec.company_id.get_key_and_certificate(validation_type)
                    except Exception:
                        validation_type = False
                rec.validation_type = validation_type
            else:
                rec.validation_type = False

    @api.depends('afip_auth_code')
    def _compute_qr_code(self):
        for rec in self:
            if rec.afip_auth_mode in ['CAE', 'CAEA'] and rec.afip_auth_code:
                number_parts = self._l10n_ar_get_document_number_parts(
                    rec.l10n_latam_document_number, rec.l10n_latam_document_type_id.code)

                qr_dict = {
                    'ver': 1,
                    'fecha': str(rec.invoice_date),
                    'cuit': int(rec.company_id.partner_id.l10n_ar_vat),
                    'ptoVta': number_parts['point_of_sale'],
                    'tipoCmp': int(rec.l10n_latam_document_type_id.code),
                    'nroCmp': number_parts['invoice_number'],
                    'importe': float(float_repr(rec.amount_total, 2)),
                    'moneda': rec.currency_id.l10n_ar_afip_code,
                    'ctz': float(float_repr(rec.l10n_ar_currency_rate, 2)),
                    'tipoCodAut': 'E' if rec.afip_auth_mode == 'CAE' else 'A',
                    'codAut': rec.afip_auth_code,
                }
                if len(rec.commercial_partner_id.l10n_latam_identification_type_id) and rec.commercial_partner_id.vat:
                    qr_dict['tipoDocRec'] = int(
                        rec.commercial_partner_id.l10n_latam_identification_type_id.l10n_ar_afip_code)
                    qr_dict['nroDocRec'] = int(rec.commercial_partner_id.vat.replace('-', '').replace('.', ''))
                qr_data = base64.encodestring(json.dumps(
                    qr_dict, indent=None).encode('ascii')).decode('ascii')
                rec.afip_qr_code = 'https://www.afip.gob.ar/fe/qr/?p=%s' % qr_data
            else:
                rec.afip_qr_code = False

    def get_related_invoices_data(self):
        """
        List related invoice information to fill CbtesAsoc.
        """
        self.ensure_one()
        if self.l10n_latam_document_type_id.internal_type == 'credit_note':
            return self.reversed_entry_id
        elif self.l10n_latam_document_type_id.internal_type == 'debit_note':
            return self.debit_origin_id
        else:
            return self.browse()

    def post(self):
        """
        The last thing we do is request the cae because if an error occurs
        after cae requested, the invoice has been already validated on afip
        """
        
        res=super().post()
        self.do_pyafipws_request_cae()
        return res
    
    def do_pyafipws_request_cae(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        # JJVR - Inicio
        has_error = False
        error_invoice_ids = self.env['account.move']
        # JJVR - Fin
        for inv in self:
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

            # if no validation type and we are on electronic invoice, it means
            # that we are on a testing database without homologation
            # certificates
            if not inv.validation_type:
                msg = (
                    'Factura validada solo localmente por estar en ambiente '
                    'de homologación sin claves de homologación')
                inv.write({
                    'afip_auth_mode': 'CAE',
                    'afip_auth_code': '68448767638166',
                    'afip_auth_code_due': inv.invoice_date,
                    'afip_result': '',
                    'afip_message': msg,
                })
                inv.message_post(body=msg)
                continue

            # get the electronic invoice type, point of sale and afip_ws:
            commercial_partner = inv.commercial_partner_id
            country = commercial_partner.country_id
            journal = inv.journal_id
            pos_number = journal.l10n_ar_afip_pos_number
            doc_afip_code = inv.l10n_latam_document_type_id.code

            # authenticate against AFIP:
            ws = inv.company_id.get_connection(afip_ws).connect()

            if afip_ws == 'wsfex':
                if not country:
                    raise UserError(_(
                        'For WS "%s" country is required on partner' % (
                            afip_ws)))
                elif not country.code:
                    raise UserError(_(
                        'For WS "%s" country code is mandatory'
                        'Country: %s' % (
                            afip_ws, country.name)))
                elif not country.l10n_ar_afip_code:
                    raise UserError(_(
                        'For WS "%s" country afip code is mandatory'
                        'Country: %s' % (
                            afip_ws, country.name)))

            ws_next_invoice_number = int(
                inv.journal_id.get_pyafipws_last_invoice(inv.l10n_latam_document_type_id)['result']) + 1

            partner_id_code = commercial_partner.l10n_latam_identification_type_id.l10n_ar_afip_code
            tipo_doc = partner_id_code or '99'
            nro_doc = \
                partner_id_code and commercial_partner.vat or "0"
            cbt_desde = cbt_hasta = cbte_nro = ws_next_invoice_number
            concepto = tipo_expo = int(inv.l10n_ar_afip_concept)

            fecha_cbte = inv.invoice_date
            if afip_ws != 'wsmtxca':
                fecha_cbte = inv.invoice_date.strftime('%Y%m%d')

            mipyme_fce = int(doc_afip_code) in [201, 206, 211]
            # due date only for concept "services" and mipyme_fce
            if int(concepto) != 1 and int(doc_afip_code) not in [202, 203, 207, 208, 212, 213] or mipyme_fce:
                fecha_venc_pago = inv.invoice_date_due or inv.invoice_date
                if afip_ws != 'wsmtxca':
                    fecha_venc_pago = fecha_venc_pago.strftime('%Y%m%d')
            else:
                fecha_venc_pago = None

            # fecha de servicio solo si no es 1
            if int(concepto) != 1:
                fecha_serv_desde = inv.l10n_ar_afip_service_start
                fecha_serv_hasta = inv.l10n_ar_afip_service_end
                if afip_ws != 'wsmtxca':
                    fecha_serv_desde = fecha_serv_desde.strftime('%Y%m%d')
                    fecha_serv_hasta = fecha_serv_hasta.strftime('%Y%m%d')
            else:
                fecha_serv_desde = fecha_serv_hasta = None

            amounts = inv._l10n_ar_get_amounts()
            # invoice amount totals:
            imp_total = str("%.2f" % inv.amount_total)
            # ImpTotConc es el iva no gravado
            imp_tot_conc = str("%.2f" % amounts['vat_untaxed_base_amount'])
            # tal vez haya una mejor forma, la idea es que para facturas c
            # no se pasa iva. Probamos hacer que vat_taxable_amount
            # incorpore a los imp cod 0, pero en ese caso termina reportando
            # iva y no lo queremos
            if inv.l10n_latam_document_type_id.l10n_ar_letter == 'C':
                imp_neto = str("%.2f" % inv.amount_untaxed)
            else:
                imp_neto = str("%.2f" % amounts['vat_taxable_amount'])
            imp_iva = str("%.2f" % amounts['vat_amount'])
            # se usaba para wsca..
            # imp_subtotal = str("%.2f" % inv.amount_untaxed)
            imp_trib = str("%.2f" % amounts['not_vat_taxes_amount'])
            imp_op_ex = str("%.2f" % amounts['vat_exempt_base_amount'])
            moneda_id = inv.currency_id.l10n_ar_afip_code
            moneda_ctz = inv.l10n_ar_currency_rate

            CbteAsoc = inv.get_related_invoices_data()

            # create the invoice internally in the helper
            if afip_ws == 'wsfe':
                ws.CrearFactura(
                    concepto, tipo_doc, nro_doc, doc_afip_code, pos_number,
                    cbt_desde, cbt_hasta, imp_total, imp_tot_conc, imp_neto,
                    imp_iva,
                    imp_trib, imp_op_ex, fecha_cbte, fecha_venc_pago,
                    fecha_serv_desde, fecha_serv_hasta,
                    moneda_id, moneda_ctz
                )
            # elif afip_ws == 'wsmtxca':
            #     obs_generales = inv.comment
            #     ws.CrearFactura(
            #         concepto, tipo_doc, nro_doc, doc_afip_code, pos_number,
            #         cbt_desde, cbt_hasta, imp_total, imp_tot_conc, imp_neto,
            #         imp_subtotal,   # difference with wsfe
            #         imp_trib, imp_op_ex, fecha_cbte, fecha_venc_pago,
            #         fecha_serv_desde, fecha_serv_hasta,
            #         moneda_id, moneda_ctz,
            #         obs_generales   # difference with wsfe
            #     )
            elif afip_ws == 'wsfex':
                # # foreign trade data: export permit, country code, etc.:
                if inv.invoice_incoterm_id:
                    incoterms = inv.invoice_incoterm_id.code
                    incoterms_ds = inv.invoice_incoterm_id.name
                    # máximo de 20 caracteres admite
                    incoterms_ds = incoterms_ds and incoterms_ds[:20]
                else:
                    incoterms = incoterms_ds = None
                # por lo que verificamos, se pide permiso existente solo
                # si es tipo expo 1 y es factura (codigo 19), para todo el
                # resto pasamos cadena vacia
                if int(doc_afip_code) == 19 and tipo_expo == 1:
                    # TODO investigar si hay que pasar si ("S")
                    permiso_existente = "N"
                else:
                    permiso_existente = ""
                obs_generales = inv.narration

                if inv.invoice_payment_term_id:
                    forma_pago = inv.invoice_payment_term_id.name
                    obs_comerciales = inv.invoice_payment_term_id.name
                else:
                    forma_pago = obs_comerciales = None

                # 1671 Report fecha_pago with format YYYMMDD
                # 1672 Is required only doc_type 19. concept (2,4)
                # 1673 If doc_type != 19 should not be reported.
                # 1674 doc_type 19 concept (2,4). date should be >= invoice
                # date
                fecha_pago = datetime.strftime(inv.invoice_date_due, '%Y%m%d') \
                    if int(doc_afip_code) == 19 and tipo_expo in [2, 4] and inv.invoice_date_due else ''

                idioma_cbte = 1     # invoice language: spanish / español

                # TODO tal vez podemos unificar este criterio con el del
                # citi que pide el cuit al partner
                # customer data (foreign trade):
                nombre_cliente = commercial_partner.name
                # se debe informar cuit pais o id_impositivo
                if nro_doc:
                    id_impositivo = nro_doc
                    cuit_pais_cliente = None
                elif country.code != 'AR' and nro_doc:
                    id_impositivo = None
                    if commercial_partner.is_company:
                        cuit_pais_cliente = country.cuit_juridica
                    else:
                        cuit_pais_cliente = country.cuit_fisica
                    if not cuit_pais_cliente:
                        raise UserError(_(
                            'No vat defined for the partner and also no CUIT '
                            'set on country'))

                domicilio_cliente = " - ".join([
                    commercial_partner.name or '',
                    commercial_partner.street or '',
                    commercial_partner.street2 or '',
                    commercial_partner.zip or '',
                    commercial_partner.city or '',
                ])
                pais_dst_cmp = commercial_partner.country_id.l10n_ar_afip_code
                ws.CrearFactura(
                    doc_afip_code, pos_number, cbte_nro, fecha_cbte,
                    imp_total, tipo_expo, permiso_existente, pais_dst_cmp,
                    nombre_cliente, cuit_pais_cliente, domicilio_cliente,
                    id_impositivo, moneda_id, moneda_ctz, obs_comerciales,
                    obs_generales, forma_pago, incoterms,
                    idioma_cbte, incoterms_ds, fecha_pago,
                )
            elif afip_ws == 'wsbfe':
                zona = 1  # Nacional (la unica devuelta por afip)
                # los responsables no inscriptos no se usan mas
                impto_liq_rni = 0.0
                imp_iibb = amounts['iibb_perc_amount']
                imp_perc_mun = amounts['mun_perc_amount']
                imp_internos = amounts[
                    'intern_tax_amount'] + amounts['other_taxes_amount']
                imp_perc = amounts[
                    'vat_perc_amount'] + amounts['profits_perc_amount'] + amounts['other_perc_amount']

                ws.CrearFactura(
                    tipo_doc, nro_doc, zona, doc_afip_code, pos_number,
                    cbte_nro, fecha_cbte, imp_total, imp_neto, imp_iva,
                    imp_tot_conc, impto_liq_rni, imp_op_ex, imp_perc, imp_iibb,
                    imp_perc_mun, imp_internos, moneda_id, moneda_ctz,
                    fecha_venc_pago
                )

            if afip_ws in ['wsfe', 'wsbfe']:
                if mipyme_fce:
                    # agregamos cbu para factura de credito electronica
                    ws.AgregarOpcional(
                        opcional_id=2101,
                        valor=inv.invoice_partner_bank_id.acc_number)
                elif int(doc_afip_code) in [202, 203, 207, 208, 212, 213]:
                    valor = inv.afip_fce_es_anulacion and 'S' or 'N'
                    ws.AgregarOpcional(
                        opcional_id=22,
                        valor=valor)

            # TODO ver si en realidad tenemos que usar un vat pero no lo
            # subimos
            if afip_ws not in ['wsfex', 'wsbfe']:
                vat_taxable = inv.env['account.move.line']
                for line in inv.line_ids:
                    if any(
                            tax.tax_group_id.l10n_ar_vat_afip_code and tax.tax_group_id.l10n_ar_vat_afip_code
                            not in ['0', '1', '2'] for tax in line.tax_line_id) and line.price_subtotal:
                        vat_taxable |= line
                for vat in vat_taxable:
                    ws.AgregarIva(
                        vat.tax_line_id.tax_group_id.l10n_ar_vat_afip_code,
                        "%.2f" % sum(inv.invoice_line_ids.filtered(lambda x: x.tax_ids.filtered(
                            lambda y: y.tax_group_id.l10n_ar_vat_afip_code ==
                            vat.tax_line_id.tax_group_id.l10n_ar_vat_afip_code)).mapped('price_subtotal')),
                        # "%.2f" % abs(vat.base_amount),
                        "%.2f" % vat.price_subtotal,
                    )

                not_vat_taxes = inv.line_ids.filtered(
                    lambda x: x.tax_line_id and x.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code)
                for tax in not_vat_taxes:
                    ws.AgregarTributo(
                        tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code,
                        tax.tax_line_id.tax_group_id.name,
                        "%.2f" % sum(inv.invoice_line_ids.filtered(lambda x: x.tax_ids.filtered(
                            lambda y: y.tax_group_id.l10n_ar_tribute_afip_code ==
                            tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code)).mapped('price_subtotal')),
                        # "%.2f" % abs(tax.base_amount),
                        # TODO pasar la alicuota
                        # como no tenemos la alicuota pasamos cero, en v9
                        # podremos pasar la alicuota
                        0,
                        "%.2f" % tax.price_subtotal,
                    )

            if CbteAsoc:
                # fex no acepta fecha
                doc_number_parts = inv._l10n_ar_get_document_number_parts(
                    CbteAsoc.l10n_latam_document_number, CbteAsoc.l10n_latam_document_type_id.code)
                if afip_ws == 'wsfex':
                    ws.AgregarCmpAsoc(
                        CbteAsoc.l10n_latam_document_type_id.document_type_id.code,
                        doc_number_parts['point_of_sale'],
                        doc_number_parts['invoice_number'],
                        inv.company_id.vat,
                    )
                else:
                    ws.AgregarCmpAsoc(
                        CbteAsoc.l10n_latam_document_type_id.code,
                        doc_number_parts['point_of_sale'],
                        doc_number_parts['invoice_number'],
                        inv.company_id.vat,
                        afip_ws != 'wsmtxca' and CbteAsoc.invoice_date.strftime(
                            '%Y%m%d') or CbteAsoc.invoice_date.strftime('%Y-%m-%d'),
                    )

            # analize line items - invoice detail
            # wsfe do not require detail
            if afip_ws != 'wsfe':
                for line in inv.invoice_line_ids.filtered(lambda x: not x.display_type):
                    codigo = line.product_id.default_code
                    # unidad de referencia del producto si se comercializa
                    # en una unidad distinta a la de consumo
                    # uom is not mandatory, if no UOM we use "unit"
                    if not line.product_uom_id:
                        umed = '7'
                    elif not line.product_uom_id.l10n_ar_afip_code:
                        raise UserError(_(
                            'Not afip code con producto UOM %s' % (
                                line.product_uom_id.name)))
                    else:
                        umed = line.product_uom_id.l10n_ar_afip_code
                    # cod_mtx = line.uom_id.l10n_ar_afip_code
                    ds = line.name
                    qty = line.quantity
                    precio = line.price_unit
                    importe = line.price_subtotal
                    # calculamos bonificacion haciendo teorico menos importe
                    bonif = line.discount and str(
                        "%.2f" % (precio * qty - importe)) or None
                    if afip_ws in ['wsmtxca', 'wsbfe']:
                        # TODO No lo estamos usando. Borrar?
                        # if not line.product_id.uom_id.l10n_ar_afip_code:
                        #     raise UserError(_(
                        #         'Not afip code con producto UOM %s' % (
                        #             line.product_id.uom_id.name)))
                        # u_mtx = (
                        #     line.product_id.uom_id.l10n_ar_afip_code or
                        #     line.uom_id.l10n_ar_afip_code)
                        iva_id = line.vat_tax_id.tax_group_id.l10n_ar_vat_afip_code
                        vat_taxes_amounts = line.vat_tax_id.compute_all(
                            line.price_unit, inv.currency_id, line.quantity,
                            product=line.product_id,
                            partner=inv.partner_id)
                        imp_iva = sum(
                            [x['amount'] for x in vat_taxes_amounts['taxes']])
                        if afip_ws == 'wsmtxca':
                            raise UserError(
                                _('WS wsmtxca Not implemented yet'))
                            # ws.AgregarItem(
                            #     u_mtx, cod_mtx, codigo, ds, qty, umed,
                            #     precio, bonif, iva_id, imp_iva,
                            #     importe + imp_iva)
                        elif afip_ws == 'wsbfe':
                            sec = ""  # Código de la Secretaría (TODO usar)
                            ws.AgregarItem(
                                codigo, sec, ds, qty, umed, precio, bonif,
                                iva_id, importe + imp_iva)
                    elif afip_ws == 'wsfex':
                        ws.AgregarItem(
                            codigo, ds, qty, umed, precio, "%.2f" % importe,
                            bonif)

            # Request the authorization! (call the AFIP webservice method)
            vto = None
            msg = False
            try:
                if afip_ws == 'wsfe':
                    ws.CAESolicitar()
                    vto = ws.Vencimiento
                elif afip_ws == 'wsmtxca':
                    ws.AutorizarComprobante()
                    vto = ws.Vencimiento
                elif afip_ws == 'wsfex':
                    ws.Authorize(inv.id)
                    vto = ws.FchVencCAE
                elif afip_ws == 'wsbfe':
                    ws.Authorize(inv.id)
                    vto = ws.Vencimiento
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
                    # avoid encoding problem when raising error
                    msg = traceback.format_exception_only(
                        sys.exc_type,
                        sys.exc_value)[0]
            if msg:
                _logger.info(_('AFIP Validation Error. %s' % msg) + ' XML Request: %s XML Response: %s' % (
                    ws.XmlRequest, ws.XmlResponse))
                # raise UserError(_('AFIP Validation Error. %s' % msg))
                # Inicio JJVR
                # En caso que sea una unica factura y de error este raise se ejecuta.
                # Caso contrario, no se ejecutara el RAISE ya que afectara a todo el ciclo FOR.
                if (len(self) == 1):
                    raise UserError(_('AFIP Validation Error. %s' % msg))
                inv.button_draft()
                inv.button_cancel()
                inv.delete_number()
                inv.button_draft()
                has_error = True
                error_invoice_ids += inv
                continue
                # Fin JJVR
            
            # Inicio JJVR
            if falla:
                ws_next_invoice_number = int(inv.journal_id.get_pyafipws_last_invoice(inv.l10n_latam_document_type_id)['result']) + 1
                inv.name = inv.name[:-8] + str(ws_next_invoice_number).zfill(8)
            # Fin JJVR
            
            msg = u"\n".join([ws.Obs or "", ws.ErrMsg or ""])
            if not ws.CAE or ws.Resultado != 'A':
                raise UserError(_('AFIP Validation Error. %s' % msg))
            # TODO ver que algunso campos no tienen sentido porque solo se
            # escribe aca si no hay errores
            
            if vto:
                vto = datetime.strptime(vto, '%Y%m%d').date()
            _logger.info('CAE solicitado con exito. CAE: %s. Resultado %s' % (
                ws.CAE, ws.Resultado))
            inv.write({
                'afip_auth_mode': 'CAE',
                'afip_auth_code': ws.CAE,
                'afip_auth_code_due': vto,
                'afip_result': ws.Resultado,
                'afip_message': msg,
                'afip_xml_request': ws.XmlRequest,
                'afip_xml_response': ws.XmlResponse,
            })
            # si obtuvimos el cae hacemos el commit porque estoya no se puede
            # volver atras
            # otra alternativa seria escribir con otro cursor el cae y que
            # la factura no quede validada total si tiene cae no se vuelve a
            # solicitar. Lo mismo podriamos usar para grabar los mensajes de
            # afip de respuesta
            inv._cr.commit()
        
        # Inicio - JJVR
        if has_error:
            # Sincronizamos la numeración de los journals_ids con error
            error_invoice_ids.mapped('journal_id').sync_document_local_remote_number()
        # Fin - JJVR
