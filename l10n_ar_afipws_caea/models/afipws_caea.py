# -*- coding: utf-8 -*-

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging
_logger = logging.getLogger(__name__)


class AfipwsCaea(models.Model):
    _name = 'afipws.caea'
    _description = 'Caea registry'
    _order = "date_from desc"
    _sql_constraints = [
        ('unique_caea', 'unique (company_id,name,order)', 'CAEA already exists!')
    ]

    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    name = fields.Char(
        string='Period',
        size=6,
        required=True,
    )
    order = fields.Selection(
        [('1', 'first Fortnight'), ('2', 'second Fortnight')],
        string='Fortnight',
        required=True,
    )
    afip_caea = fields.Char(
        string='CAEA',
    )
    afip_observations = fields.Text(
        string='Observations',
    )
    afip_errors = fields.Text(
        string='Errors',
    )
    date_from = fields.Date(
        string='from',
        compute="_compute_date",
        store=True,
    )
    date_to = fields.Date(
        string='to',
        compute="_compute_date",
        store=True,
    )
    move_ids = fields.One2many(
        'account.move',
        'caea_id',
        string='Moves',
    )

    @api.depends('name', 'order')
    def _compute_date(self):
        for caea in self:
            if caea.order and caea.name:
                if caea.order == '1':
                    caea.date_from = fields.Date.from_string(
                        "%s-%s-01" % (caea.name[0:4], caea.name[4:]))
                    caea.date_to = fields.Date.from_string(
                        "%s-%s-15" % (caea.name[0:4], caea.name[4:]))
                else:
                    caea.date_from = fields.Date.from_string(
                        "%s-%s-16" % (caea.name[0:4], caea.name[4:]))
                    caea.date_to = fields.Date.from_string(
                        "%s-%s-1" % (caea.name[0:4], caea.name[4:])) + relativedelta(months=1) - relativedelta(days=1)

    @api.model
    def create(self, values):

        """exist = self.search([
            ('company_id', '=', values['company_id']),
            ('name', '=', values['name']),
            ('order', '=', values['order'])
        ])
        if len(exist):
            return"""

        company_id = self.env['res.company'].search(
            [('id', '=', values['company_id'])])
        ws = company_id.get_connection('wsfe').connect()
        caea = ws.CAEAConsultar(values['name'], values['order'])
        # raise ValidationError(
        #        _('The Common Name must be lower than 50 characters long'))

        #_logger.info("ws.ErrMsg " % ws.ErrMsg)
        _logger.info(caea)
        if caea == '':
            caea = ws.CAEASolicitar(values['name'], values['order'])
            _logger.info(ws.ErrMsg)
            _logger.info(caea)

        values['afip_caea'] = caea
        values['afip_observations'] = ws.Obs

        return super().create(values)

    def send_caea_invoices(self):
        self.env['ir.config_parameter'].set_param(
            'afip.ws.caea.state', 'inactive')

        move_ids = self.env['account.move'].search([
            ('afip_auth_mode', '=', 'CAEA'),
            ('afip_auth_code', '=', self.afip_caea)
        ], order='name asc')
        out_invoice = move_ids.filtered(lambda i: i.type in ['out_invoice'])
        out_refund = move_ids.filtered(lambda i: i.type in ['out_refund'])
        for inv in out_invoice:
            inv.do_pyafipws_request_cae()
        for inv in out_refund:
            inv.do_pyafipws_request_cae()

    def cron_request_caea(self):
        request_date = fields.Date.today() + relativedelta(days=7)
        period = request_date.strftime('%Y%m')
        order = '1' if request_date.day < 16 else '2'

        company_ids = self.env['res.company'].search([('use_caea', '=', True)])
        for company_id in company_ids:
            caea = self.search([
                ('name', '=', period),
                ('order', '=', order),
                ('company_id', '=', company_id.id),
            ])

            if not len(caea):

                self.create({
                    'name': period,
                    'order': order,
                    'company_id': company_id.id
                })

    def cron_send_caea_invoices(self):

        self.env['ir.config_parameter'].set_param(
            'afip.ws.caea.state', 'inactive')
        caea_ids = self.search([
            ('date_from', '<=',  fields.Date.today() + relativedelta(days=1)),
            ('date_to', '>=',  fields.Date.today() + relativedelta(days=1))
        ])
        caea_ids.send_caea_invoices()
