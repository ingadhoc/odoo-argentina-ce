# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class pyafipwsDummy(models.TransientModel):
    _name = 'pyafipws.dummy'
    _description = 'AFIP dummy'

    def _default_afip_ws_caea_state(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'afip.ws.caea.state', 'inactive')

    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True
    )
    afip_ws_caea_state = fields.Selection(
        [('inactive', 'Use WS'), ('active', 'Use CAEA')],
        string='AFIP enviroment type',
        compute='_compute_afip_ws_caea_state',
        default=lambda self: self._default_afip_ws_caea_state()
    )

    app_server_status = fields.Boolean(
        string='AppServerStatus',
        readonly=True,
    )
    db_server_status = fields.Boolean(
        string='AppServerStatus',
        readonly=True,
    )
    auth_server_status = fields.Boolean(
        string='AppServerStatus',
        readonly=True,
    )
    status = fields.Boolean(
        string='AFIP status',
    )

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        afip_ws = self.journal_id.afip_ws
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        try:
            ws = self.journal_id.company_id.get_connection(afip_ws).connect()
            ws.Dummy()
            status = ws.AppServerStatus and ws.DbServerStatus and ws.AuthServerStatus
            self.write({'app_server_status': ws.AppServerStatus,
                        'db_server_status': ws.DbServerStatus,
                        'auth_server_status': ws.AuthServerStatus,
                        'status': status
                        })
        except Exception as e:
            self.write({'app_server_status': False,
                        'db_server_status': False,
                        'auth_server_status': False,
                        'status': False
                        })

    def _compute_afip_ws_caea_state(self):
        _logger.info("x%r" % self.env['ir.config_parameter'].sudo().get_param(
            'afip.ws.caea.state', 'inactive'))
        self.afip_ws_caea_state = self.env['ir.config_parameter'].sudo().get_param(
            'afip.ws.caea.state', 'inactive')

    def afip_green_button(self):
        self.env['ir.config_parameter'].set_param(
            'afip.ws.caea.state', 'inactive')

    def afip_red_button(self):
        self.env['ir.config_parameter'].set_param(
            'afip.ws.caea.state', 'active')
