##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_repr
from odoo.tools.safe_eval import safe_eval

from .fiscal_ws_connection import build_client, call_service

_logger = logging.getLogger(__name__)

PROVIDER_PREFIX = "_l10n_ar_fiscal_provider_"


class L10nArFiscalWsMapping(models.Model):
    _name = "l10n_ar.fiscal.ws.mapping"
    _description = "Fiscal Web Service Mapping"

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Name used from the code to pick this mapping, e.g. cae_request.")
    fiscal_ws_id = fields.Many2one("l10n_ar.fiscal.ws", required=True, ondelete="cascade")
    method_name = fields.Char(required=True, help="Method to call on the service, e.g. FECAESolicitar.")
    auth_style = fields.Selection(
        [
            ("block", "Auth block"),
            ("inline", "Auth block with the parameters inside"),
            ("request", "authRequest block"),
            ("plain", "Loose parameters"),
            ("none", "No credentials"),
        ],
        default="block",
        required=True,
        help="How this method expects the credentials: most take an Auth block, the census "
        "services take them as loose parameters.",
    )
    line_ids = fields.One2many("l10n_ar.fiscal.ws.mapping.line", "mapping_id")

    _unique_code_per_ws = models.Constraint(
        "unique (fiscal_ws_id, code)",
        "A service cannot have two mappings with the same code",
    )

    @api.model
    def _get_mapping(self, ws_code, code):
        mapping = self.search(
            [("fiscal_ws_id.code", "=", ws_code), ("code", "=", code)],
            limit=1,
        )
        if not mapping:
            raise UserError(_("The service %(service)s has no '%(code)s' mapping.", service=ws_code, code=code))
        return mapping

    def call(self, record, extra=None):
        """Build the payload of this mapping and call the service with it.

        A method that takes no credentials —the dummy of every service— is called
        without asking for an access ticket, so it works without certificates.
        """
        self.ensure_one()
        payload = self.build(record, extra)
        if self.auth_style == "none":
            client, transport = build_client(self.env, self._get_service_url())
            return call_service(client, transport, self.method_name, payload)
        company = getattr(record, "company_id", False) or self.env.company
        connection = company._get_fiscal_ws_connection(self.fiscal_ws_id.code)
        auth = connection.auth_payload(self.auth_style)
        if self.auth_style == "inline":
            # the export and fiscal bond services take the parameters inside the credentials block
            auth["Auth"].update(payload)
            return connection.call(self.method_name, auth)
        return connection.call(self.method_name, {**auth, **payload})

    def _get_service_url(self):
        self.ensure_one()
        environment_type = self.env["res.company"]._get_environment_type()
        return self.env["l10n_ar.fiscal.ws"]._get_url(self.fiscal_ws_id.code, environment_type)

    def build(self, source, extra=None):
        """Values built from the mapping lines.

        Used both ways: a record gives the payload to send, a response gives the
        values to write back.
        """
        self.ensure_one()
        if isinstance(source, models.BaseModel):
            source.ensure_one()
        return self.line_ids.filtered(lambda line: not line.parent_id)._build(source, extra or {})


class L10nArFiscalWsMappingLine(models.Model):
    _name = "l10n_ar.fiscal.ws.mapping.line"
    _description = "Fiscal Web Service Mapping Line"
    _order = "sequence, id"

    mapping_id = fields.Many2one("l10n_ar.fiscal.ws.mapping", required=True, ondelete="cascade", index=True)
    parent_id = fields.Many2one("l10n_ar.fiscal.ws.mapping.line", ondelete="cascade", index=True)
    child_ids = fields.One2many("l10n_ar.fiscal.ws.mapping.line", "parent_id")
    sequence = fields.Integer(default=10)
    name = fields.Char("Field", required=True, help="Field name as the service names it, e.g. ImpNeto.")
    source = fields.Selection(
        [
            ("field", "Odoo field"),
            ("fixed", "Fixed value"),
            ("provider", "Provider"),
            ("extra", "Call parameter"),
            ("child", "Nested structure"),
        ],
        required=True,
        default="field",
    )
    value = fields.Char(
        help="Path of Odoo fields, fixed value or provider name, depending on the source.",
    )
    format = fields.Selection(
        [
            ("str", "Text"),
            ("int", "Integer"),
            ("float2", "Amount (2 decimals)"),
            ("float6", "Rate (6 decimals)"),
            ("date", "Date (YYYYMMDD)"),
            ("date_in", "Date read from the service (YYYYMMDD)"),
            ("bool_sn", "Yes/No as S/N"),
            ("raw", "As is"),
        ],
        default="str",
    )
    condition_domain = fields.Char(help="The line is only sent when the record matches this domain.")
    condition = fields.Char(
        help="Boolean expression, for what a domain cannot express. Context: record, company, today.",
    )
    repeat_provider = fields.Char(
        help="For nested structures: provider returning the collection to repeat the children on.",
    )
    is_list = fields.Boolean(
        help="For nested structures: send the structure inside a list, as some services expect.",
    )

    @api.constrains("condition")
    def _check_condition(self):
        """Fail on install, not while invoicing."""
        for line in self.filtered("condition"):
            try:
                compile(line.condition, "<mapping line %s>" % line.name, "eval")
            except SyntaxError as error:
                raise ValidationError(
                    _(
                        "The condition of the line %(line)s is not a valid expression: %(error)s",
                        line=line.name,
                        error=error,
                    )
                ) from error

    def _build(self, record, extra):
        """Values of these lines for a record, skipping the ones that do not apply."""
        values = {}
        for line in self:
            if not line._applies(record, extra):
                continue
            value = line._get_value(record, extra)
            if value is not None:
                values[line.name] = value
        return values

    def _applies(self, record, extra):
        self.ensure_one()
        if self.condition_domain and not record.filtered_domain(safe_eval(self.condition_domain)):  # noqa
            return False
        if self.condition:
            context = {
                "record": record,
                "company": record.company_id,
                "today": fields.Date.context_today(record),
                "extra": extra,
            }
            result = safe_eval(self.condition, context)
            if not isinstance(result, bool):
                raise UserError(_("The condition of the line %s must return true or false.", self.name))
            return result
        return True

    def _get_value(self, record, extra):
        self.ensure_one()
        if self.source == "child":
            return self._get_child_value(record, extra)
        if self.source == "fixed":
            return self._format(self.value)
        if self.source == "provider":
            return self._format(self._call_provider(record, self.value, extra))
        if self.source == "extra":
            return self._format(self._read_path(extra, self.value))
        return self._format(self._read_path(record, self.value))

    def _get_child_value(self, record, extra):
        """Nested structure: one dict, or a list of dicts when it repeats."""
        if not self.repeat_provider:
            values = self.child_ids._build(record, extra) or None
            return [values] if values and self.is_list else values
        items = self._call_provider(record, self.repeat_provider, extra)
        if not items:
            return None
        return [self.child_ids._build(item, extra) for item in items]

    def _call_provider(self, record, name, extra):
        """Call a provider; what follows the first dot is read over its result."""
        provider_name, _dot, path = name.partition(".")
        provider = getattr(record, PROVIDER_PREFIX + provider_name, None)
        if provider is None:
            raise UserError(
                _(
                    "The mapping line %(line)s asks for the provider '%(name)s', which does not exist.",
                    line=self.name,
                    name=provider_name,
                )
            )
        result = provider(extra)
        return self._read_path(result, path) if path else result

    @staticmethod
    def _read_path(source, path):
        """Read a path over a record, a dict or a web service response.

        Accepts an index at the end of a part, as in FECAEDetResponse[0].
        """
        value = source
        for part in (path or "").split("."):
            index = None
            if part.endswith("]") and "[" in part:
                part, _, raw_index = part[:-1].partition("[")
                index = int(raw_index)
            value = value.get(part) if isinstance(value, dict) else getattr(value, part)
            if index is not None and value:
                value = value[index]
            if value is None or value is False:
                return value
        return value

    def _format(self, value):
        if self.format == "bool_sn":
            return "S" if value else "N"
        if value is None or value is False:
            return None
        if self.format == "raw":
            return value
        if self.format == "date_in":
            return datetime.strptime(str(value), "%Y%m%d").date()
        if self.format == "int":
            return int(value)
        if self.format == "float2":
            return float_repr(float(value), 2)
        if self.format == "float6":
            return float_repr(float(value), 6)
        if self.format == "date":
            if isinstance(value, str):
                return value
            if isinstance(value, (date, datetime)):
                return value.strftime("%Y%m%d")
            raise UserError(_("The line %s expects a date.", self.name))
        return str(value)
