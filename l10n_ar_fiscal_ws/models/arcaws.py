##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo.exceptions import ValidationError
from odoo.tools import float_repr, ormcache, safe_eval

from odoo import _, api, fields, models

from .exceptions import ArcaError

_logger = logging.getLogger(__name__)


class ArcaWs(models.Model):
    _name = "arcaws"
    _description = "Arca webservice URLs"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    production_url = fields.Char(required=True)
    homologation_url = fields.Char(required=True)
    view_id = fields.Many2one("ir.ui.view")
    dummy_method = fields.Boolean(compute="_compute_dummy_method", store=False)
    method_ids = fields.One2many("arcaws.method", "arcaws_id")
    connection_ids = fields.One2many("arcaws.connection", "arcaws")
    ws_parameters = fields.Json()
    active = fields.Boolean(default=True)

    _arcaws_unique_code = models.Constraint(
        "unique (code)",
        "A WS code must be unique",
    )

    @api.model
    @ormcache("code", "env_type", cache="stable")
    def get_arca_url(self, code, env_type):
        """Get ARCA URL for a given service code and environment type
        (production or homologation)
        """
        url_record = self.search([("code", "=", code)], limit=1)
        if not url_record:
            raise ValidationError(_("No ARCA URL found for service '%s'.") % code)
        if env_type == "production":
            return url_record.production_url
        else:
            return url_record.homologation_url

    def action_dummie(self):
        self.ensure_one()
        _logger.info("Dummie action called")
        company = self.env.company
        method_id = self.method_ids.filtered(lambda m: m.name == "dummy")
        if method_id:
            raise ArcaError(method_id.call_arca_method(self, company_id=company))

    def _compute_dummy_method(self):
        has_dummy = self.filtered(lambda x: x.method_ids.filtered(lambda x: x.name == "dummy"))
        has_dummy.dummy_method = True
        (self - has_dummy).dummy_method = False


class ArcaWsMethod(models.Model):
    _name = "arcaws.method"
    _description = "ARCA WS Method"

    name = fields.Char(required=True)
    arcaws_id = fields.Many2one("arcaws", required=True)
    model_id = fields.Many2one("ir.model")
    method_name = fields.Char(required=True)
    definition_dict = fields.Text(default="{}")
    response_dict = fields.Text()

    def call_arca_method(self, obj, mode="eval", **kwargs):
        self.ensure_one()
        if kwargs.get("company_id"):
            company_id = kwargs.get("company_id")
        elif obj.company_id:
            company_id = obj.company_id
        else:
            company_id = self.env.company
        connection = company_id.arca_get_connection(self.arcaws_id.code)
        eval_context = {
            "self": obj,
            "float_repr": float_repr,
            "connection": connection,
            "company_id": company_id,
            "context_today": safe_eval.datetime.datetime.today,
            "datetime": safe_eval.datetime,
            "dateutil": safe_eval.dateutil,
            "relativedelta": safe_eval.dateutil.relativedelta.relativedelta,
            "extra_values": kwargs.get("extra_values"),
            "time": safe_eval.time,
        }
        method_dict = safe_eval.safe_eval(self.definition_dict, eval_context, mode=mode)
        ws_query = eval_context.get("result", method_dict)
        res = connection.call_arca_service(self.method_name, ws_query)
        if self.response_dict:
            try:
                eval_context["ws_res"] = res
                if "result" in eval_context:
                    del eval_context["result"]
                method_dict = safe_eval.safe_eval(self.response_dict, eval_context)
                return eval_context.get("result", method_dict)

            except Exception as e:
                _logger.error("Error processing ARCA response: %s with result %s", e, res)

        return res
