##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, api, fields, _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    afip_ws = fields.Selection(selection='_get_afip_ws', compute='_compute_afip_ws', string='AFIP WS')

    def _get_afip_ws(self):
        return [('wsfe', _('Domestic market -without detail- RG2485 (WSFEv1)')),
                ('wsfex', _('Export -with detail- RG2758 (WSFEXv1)')),
                ('wsbfe', _('Fiscal Bond -with detail- RG2557 (WSBFE)'))]

    def _get_l10n_ar_afip_pos_types_selection(self):
        res = super()._get_l10n_ar_afip_pos_types_selection()
        res.insert(0, ('RAW_MAW', _('Electronic Invoice - Web Service')))
        res.insert(3, ('BFEWS', _('Electronic Fiscal Bond - Web Service')))
        res.insert(5, ('FEEWS', _('Export Voucher - Web Service')))
        return res

    @api.depends('l10n_ar_afip_pos_system')
    def _compute_afip_ws(self):
        """ Depending on AFIP POS System selected set the proper AFIP WS """
        type_mapping = {'RAW_MAW': 'wsfe', 'FEEWS': 'wsfex', 'BFEWS': 'wsbfe'}
        for rec in self:
            rec.afip_ws = type_mapping.get(rec.l10n_ar_afip_pos_system, False)

    @api.model
    def create(self, vals):
        journal = super(AccountJournal, self).create(vals)
        if self.afip_ws:
            try:
                journal.sync_document_local_remote_number()
            except Exception:
                _logger.info(
                    'Could not sincronize local and remote numbers')
        return journal

    def sync_document_local_remote_number(self):
        if self.type != 'sale':
            return True
        for sequence in self.l10n_ar_sequence_ids:
            last = self.get_pyafipws_last_invoice(sequence.l10n_latam_document_type_id)['result']
            sequence.sudo().number_next_actual = last + 1
            # next_by_ws = int(
            #     journal_document_type.get_pyafipws_last_invoice(
            #     )['result']) + 1
            # journal_document_type.sequence_id.number_next_actual = next_by_ws

    def get_pyafipws_last_invoice(self, document_type):
        self.ensure_one()
        company = self.company_id
        afip_ws = self.afip_ws

        if not afip_ws:
            return (_('No AFIP WS selected on point of sale %s') % (self.name))
        ws = company.get_connection(afip_ws).connect()
        # call the webservice method to get the last invoice at AFIP:

        try:
            if afip_ws in ("wsfe", "wsmtxca"):
                last = ws.CompUltimoAutorizado(document_type.code, self.l10n_ar_afip_pos_number)
            elif afip_ws in ["wsfex", 'wsbfe']:
                last = ws.GetLastCMP(document_type.code, self.l10n_ar_afip_pos_number)
            else:
                return(_('AFIP WS %s not implemented') % afip_ws)
        except ValueError as error:
            _logger.warning('exception in get_pyafipws_last_invoice: %s' % (
                str(error)))
            if 'The read operation timed out' in str(error):
                raise UserError(_(
                    'Servicio AFIP Ocupado reintente en unos minutos'))
            else:
                raise UserError(_(
                    'Hubo un error al conectarse a AFIP, contacte a su'
                    ' proveedor de Odoo para mas información'))

        msg = " - ".join([ws.Excepcion, ws.ErrMsg, ws.Obs])

        next_ws = int(last or 0) + 1
        next_local = self.sequence_id.number_next_actual
        if next_ws != next_local:
            msg = _(
                'ERROR! Local (%i) and remote (%i) next number '
                'mismatch!\n') % (next_local, next_ws) + msg
        else:
            msg = _('OK! Local and remote next number match!') + msg
        title = _('Last Invoice %s\n' % last)
        return {'msg': (title + msg), 'result': int(last)}

    def test_pyafipws_dummy(self):
        """
        AFIP Description: Método Dummy para verificación de funcionamiento de
        infraestructura (FEDummy)
        """
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.company_id.get_connection(afip_ws).connect()
        ws.Dummy()
        title = _("AFIP service %s\n") % afip_ws
        msg = (
            "AppServerStatus: %s DbServerStatus: %s AuthServerStatus: %s" % (
                ws.AppServerStatus,
                ws.DbServerStatus,
                ws.AuthServerStatus))
        raise UserError(title + msg)

    def test_pyafipws_point_of_sales(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.company_id.get_connection(afip_ws).connect()
        if afip_ws == 'wsfex':
            ret = ws.GetParamPtosVenta()
        elif afip_ws == 'wsfe':
            ret = ws.ParamGetPtosVenta(sep=" ")
        else:
            raise UserError(_(
                'Get point of sale for ws %s is not implemented yet') % (
                afip_ws))
        msg = (_(" %s %s") % (
            '. '.join(ret), " - ".join([ws.Excepcion, ws.ErrMsg, ws.Obs])))
        title = _('Enabled Point Of Sales on AFIP\n')
        raise UserError(title + msg)

    def get_pyafipws_cuit_document_classes(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.company_id.get_connection(afip_ws).connect()
        if afip_ws == 'wsfex':
            ret = ws.GetParamTipoCbte(sep=",")
        elif afip_ws == 'wsfe':
            ret = ws.ParamGetTiposCbte(sep=",")
        elif afip_ws == 'wsbfe':
            ret = ws.GetParamTipoCbte()
        else:
            raise UserError(_(
                'Get document types for ws %s is not implemented yet') % (
                afip_ws))
        msg = (_(
            "Authorized Document Clases on AFIP\n%s\n. \nObservations: %s") % (
            '\n '.join(ret), ".\n".join([ws.Excepcion, ws.ErrMsg, ws.Obs])))
        raise UserError(msg)

    def get_pyafipws_zonas(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.company_id.get_connection(afip_ws).connect()
        if afip_ws == 'wsbfe':
            ret = ws.GetParamZonas()
        else:
            raise UserError(_(
                'Get zonas for ws %s is not implemented yet') % (
                afip_ws))
        msg = (_(
            "Zonas on AFIP\n%s\n. \nObservations: %s") % (
            '\n '.join(ret), ".\n".join([ws.Excepcion, ws.ErrMsg, ws.Obs])))
        raise UserError(msg)

    def get_pyafipws_NCM(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.company_id.get_connection(afip_ws).connect()
        if afip_ws == 'wsbfe':
            ret = ws.GetParamNCM()
        else:
            raise UserError(_(
                'Get NCM for ws %s is not implemented yet') % (
                afip_ws))
        msg = (_(
            "Zonas on AFIP\n%s\n. \nObservations: %s") % (
            '\n '.join(ret), ".\n".join([ws.Excepcion, ws.ErrMsg, ws.Obs])))
        raise UserError(msg)

    def action_get_connection(self):
        self.ensure_one()
        afip_ws = self.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        self.company_id.get_connection(afip_ws).connect()

    def get_pyafipws_currency_rate(self, currency):
        raise UserError(currency.get_pyafipws_currency_rate(
            afip_ws=self.afip_ws,
            company=self.company_id,
        )[1])
