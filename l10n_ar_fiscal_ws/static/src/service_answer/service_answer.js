import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

export class ServiceAnswerDialog extends Component {
    static template = "l10n_ar_fiscal_ws.ServiceAnswerDialog";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        message: { type: String },
        close: { type: Function },
    };
    static defaultProps = { title: _t("Respuesta de ARCA") };
}

// Answer of a fiscal web service. It always opens a dialog: the answers are long,
// are read line by line, and a notification would cut them at 400px.
export function serviceAnswerAction(env, action) {
    const { title, message } = action.params || {};
    if (!message) {
        return;
    }
    env.services.dialog.add(ServiceAnswerDialog, { title, message });
}

registry.category("actions").add("l10n_ar_fiscal_ws.service_answer", serviceAnswerAction);
