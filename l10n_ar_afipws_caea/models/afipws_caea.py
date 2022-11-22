
from odoo import models, fields, api
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class AfipwsCaea(models.Model):
    _name = "afipws.caea"
    _description = "Caea registry"
    _order = "date_from desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    _sql_constraints = [
        ("name_uniq", "unique(name)", "CAEA already exists!")
    ]
    state = fields.Selection(
        [("draft", "draft"), ("active", "active"), ("reported", "reported")],
        string="State",
        default="draft",
    )
    name = fields.Char(string="CAEA", default="/")

    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    period = fields.Char(
        string="Period",
        size=6,
        required=True,
    )
    year = fields.Integer(
        string="Year",
        required=True,
    )
    month = fields.Selection(
        [
            ("01", "January"),
            ("02", "February"),
            ("03", "March"),
            ("04", "April"),
            ("05", "May"),
            ("06", "June"),
            ("07", "July"),
            ("08", "August"),
            ("09", "September"),
            ("10", "October"),
            ("11", "November"),
            ("12", "December"),
        ],
        string="Month",
        required=True,
    )
    order = fields.Selection(
        [("1", "first Fortnight"), ("2", "second Fortnight")],
        string="Fortnight",
        required=True,
    )
    afip_observations = fields.Text(
        string="Observations",
    )
    afip_errors = fields.Text(
        string="Errors",
    )
    date_from = fields.Date(
        string="from",
        compute="_compute_date",
        store=True,
    )
    date_to = fields.Date(
        string="to",
        compute="_compute_date",
        store=True,
    )
    process_deadline = fields.Date(string="process deadline")
    move_ids = fields.One2many(
        "account.move",
        "caea_id",
        string="Moves",
    )
    journal_ids = fields.Many2many(
        "account.journal",
        string="Autorized CAEA journals",
    )

    def action_get_caea_pos(self):
        self.ensure_one()
        afip_ws = self.company_id.get_caea_ws()
        ws = self.company_id.get_connection(afip_ws).connect()
        if afip_ws == "wsfe":
            ret = ws.ParamGetPtosVenta(sep="|")
            journal_ids = False
            pos_numbers = []
            for res in ret:
                if "EmisionTipo:CAEA" in res:
                    pos_numbers.append(int(res.split("|")[0]))
                    journal_ids = self.env["account.journal"].search(
                        [("l10n_ar_afip_pos_number", "in", pos_numbers)]
                    )
                if journal_ids:
                    self.journal_ids = [(6, 0, journal_ids.ids)]

    @api.onchange("month", "year")
    def _onchange_month_year(self):
        if self.year and self.month:
            self.period = str(self.year) + self.month

    @api.depends("month", "year", "order")
    def _compute_date(self):
        for caea in self:
            if caea.year and caea.month:
                if caea.order == "1":
                    caea.date_from = fields.Date.from_string(
                        "%s-%s-01" % (caea.year, caea.month)
                    )
                    caea.date_to = fields.Date.from_string(
                        "%s-%s-15" % (caea.year, caea.month)
                    )
                elif caea.order == "2":
                    caea.date_from = fields.Date.from_string(
                        "%s-%s-16" % (caea.year, caea.month)
                    )
                    caea.date_to = (
                        fields.Date.from_string("%s-%s-1" % (caea.year, caea.month))
                        + relativedelta(months=1)
                        - relativedelta(days=1)
                    )

    @api.model_create_multi
    def create(self, vals_list):
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "inactive")
        _logger.info(vals_list)

        for vals in vals_list:
            if 'name' not in vals:
                company_id = self.env["res.company"].search([("id", "=", vals["company_id"])])
                afip_ws = company_id.get_caea_ws()
                ws = company_id.get_connection(afip_ws).connect()
                caea = ws.CAEAConsultar(vals["period"], vals["order"])

                # _logger.info("ws.ErrMsg " % ws.ErrMsg)
                if caea == "":
                    caea = ws.CAEASolicitar(vals["period"], vals["order"])
                    _logger.info(ws.ErrMsg)
                    _logger.info(caea)

                vals["name"] = caea
                vals["afip_observations"] = ws.Obs
                vals["process_deadline"] = datetime.strptime(ws.FchTopeInf, "%Y%m%d")
                vals["state"] = "active"
                # TODO: FchProceso
        return super().create(vals_list)

    def action_send_invoices(self):
        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "inactive")

        move_ids = self.move_ids.filtered(
            lambda m: m.l10n_ar_afip_caea_reported is False
        )

        for inv in move_ids.sorted(key=lambda r: r.caea_post_datetime):
            _logger.info(inv.name)
            inv.do_pyafipws_post_caea_invoice()

    def cron_request_caea(self):
        request_date = fields.Date.today() + relativedelta(days=7)
        period = request_date.strftime("%Y%m")
        order = "1" if request_date.day < 16 else "2"

        company_ids = self.env["res.company"].search([("use_caea", "=", True)])
        for company_id in company_ids:
            caea = self.search(
                [
                    ("name", "=", period),
                    ("order", "=", order),
                    ("company_id", "=", company_id.id),
                ]
            )

            if not len(caea):
                self.create(
                    {"name": period, "order": order, "company_id": company_id.id}
                )

    @api.model
    def cron_caea_timeout(self):
        state = self.env["ir.config_parameter"].get_param(
            "afip.ws.caea.state", "inactive"
        )
        if state == "active":
            timeout = int(
                self.env["ir.config_parameter"].get_param("afip.ws.caea.timeout", 2)
            )
            threshold = fields.Datetime.from_string(
                fields.Datetime.now()
            ) - relativedelta(minutes=int(timeout * 60))
            log = self.env["afipws.caea.log"].search_count(
                [("event", "=", "start_caea"), ("event_datetime", ">", threshold)],
                order="event_datetime DESC",
            )
            if log < 1:
                self.env["ir.config_parameter"].set_param(
                    "afip.ws.caea.state", "inactive"
                )
                self.env["afipws.caea.log"].create(
                    [{"event": "end_caea", "user_id": self.env.user.id}]
                )

    def cron_send_caea_invoices(self):

        self.env["ir.config_parameter"].set_param("afip.ws.caea.state", "inactive")
        caea_ids = self.search(
            [
                ("date_from", "<=", fields.Date.today() + relativedelta(days=1)),
                ("date_to", ">=", fields.Date.today() + relativedelta(days=1)),
            ]
        )
        caea_ids.action_send_invoices()


class AfipwsCaeaLog(models.Model):

    _name = "afipws.caea.log"
    _description = "afipws caea log"

    user_id = fields.Many2one(
        "res.users", string="User", default=lambda self: self.env.user.id
    )
    event_datetime = fields.Datetime(
        string="Datetime", default=lambda self: fields.Datetime.now()
    )
    event = fields.Selection(
        [
            ("request", "request"),
            ("start_caea", "start caea mode"),
            ("end_caea", "end caea mode"),
        ],
        string="Event",
    )
