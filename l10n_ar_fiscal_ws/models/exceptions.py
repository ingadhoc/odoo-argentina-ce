##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo.exceptions import UserError
from zeep.helpers import serialize_object

INDENT = "    "


def serialize_answer(value):
    """Answer of a service as readable text: one line per key, children indented.

    The shape is the one of a yaml document, written here to avoid pulling a
    library only to print an answer.
    """
    if value is None:
        return ""
    # always: zeep objects also travel inside lists and dicts, and for anything
    # else serialize_object gives back the same value
    value = serialize_object(value, target_cls=dict)
    if not isinstance(value, (dict, list, tuple)):
        return str(value)
    return _render(value, 0)


def _render(value, level):
    if isinstance(value, dict):
        return "\n".join(_render_item(key, item, level) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join(_render_element(item, level) for item in value)
    return "%s%s" % (INDENT * level, value)


def _render_item(key, value, level):
    """A key and its value: on the same line when it is plain, below when it is not."""
    pad = INDENT * level
    if isinstance(value, (dict, list, tuple)) and value:
        return "%s%s:\n%s" % (pad, key, _render(value, level + 1))
    if value is None or value == "" or isinstance(value, (dict, list, tuple)):
        return "%s%s:" % (pad, key)
    return "%s%s: %s" % (pad, key, value)


def _render_element(value, level):
    """An element of a list: the dash opens it and the rest lines up under it."""
    pad = INDENT * level
    if not isinstance(value, (dict, list, tuple)) or not value:
        return "%s- %s" % (pad, value if value else "")
    lines = _render(value, 0).split("\n")
    return "\n".join(["%s- %s" % (pad, lines[0])] + ["%s  %s" % (pad, line) for line in lines[1:]])


class FiscalWsError(UserError):
    """Answer of a fiscal web service shown to the user as is.

    It inherits UserError so Odoo treats it as a controlled error, and lowers the
    log level: these are answers of the tax authority, not failures of ours, and
    a traceback per call floods the log.
    """

    loglevel = logging.INFO
    exc_info = None

    def __init__(self, message):
        super().__init__(serialize_answer(message) or str(message))
