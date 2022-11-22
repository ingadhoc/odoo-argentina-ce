# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class pyafipwsDummy(models.TransientModel):
    _name = "pyafipws.dummy"
    _description = "AFIP dummy"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "default_journal_id" not in self.env.context:
            journal = self.env["account.journal"].search(
                [("l10n_ar_afip_pos_system", "=", "RAW_MAW")], limit=1
            )
            _logger.info(journal)
            if len(journal):
                res["journal_id"] = journal.id
        _logger.info(res)
        return res

    def _default_afip_ws_caea_state(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("afip.ws.caea.state", "inactive")
        )

    journal_id = fields.Many2one("account.journal", string="Journal", required=True)
    afip_ws_caea_state = fields.Selection(
        [("inactive", "Use WS"), ("active", "Use CAEA")],
        string="AFIP enviroment type",
        compute="_compute_afip_ws_caea_state",
        default=lambda self: self._default_afip_ws_caea_state(),
    )

    app_server_status = fields.Boolean(
        string="App Server Status",
        # readonly=True,
    )
    db_server_status = fields.Boolean(
        string="DB Server Status",
        # readonly=True,
    )
    auth_server_status = fields.Boolean(
        string="auth Server Status",
        # readonly=True,
    )
    status = fields.Boolean(
        string="AFIP status",
    )

    @api.onchange("app_server_status", "db_server_status", "auth_server_status")
    def _onchange_status(self):
        self.status = (
            self.app_server_status and self.db_server_status and self.auth_server_status
        )

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        afip_ws = self.journal_id.afip_ws
        if self.journal_id and not afip_ws:
            raise UserError(_("No AFIP WS selected"))
        try:
            ws = self.journal_id.company_id.get_connection(afip_ws).connect()
            ws.Dummy()
            self.write(
                {
                    "app_server_status": ws.AppServerStatus,
                    "db_server_status": ws.DbServerStatus,
                    "auth_server_status": ws.AuthServerStatus,
                }
            )
        except Exception as e:
            self.write(
                {
                    "app_server_status": False,
                    "db_server_status": False,
                    "auth_server_status": False,
                    "status": False,
                }
            )

    def _compute_afip_ws_caea_state(self):
        self.afip_ws_caea_state = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("afip.ws.caea.state", "inactive")
        )

    def afip_green_button(self):
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "inactive")
        self.env["afipws.caea.log"].create(
            [{"event": "end_caea", "user_id": self.env.user.id}]
        )

    def afip_red_button(self):
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "active")
        self.env["afipws.caea.log"].create(
            [{"event": "start_caea", "user_id": self.env.user.id}]
        )
