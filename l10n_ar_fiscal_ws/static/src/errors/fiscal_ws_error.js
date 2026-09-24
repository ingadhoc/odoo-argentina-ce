import { WarningDialog, odooExceptionTitleMap } from "@web/core/errors/error_dialogs";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

const EXCEPTION = "odoo.addons.l10n_ar_fiscal_ws.models.exceptions.FiscalWsError";

// Same dialog as any warning, with the answer in a monospaced block: what the
// service returns is long and is read line by line.
export class FiscalWsErrorDialog extends WarningDialog {
    static template = "l10n_ar_fiscal_ws.FiscalWsErrorDialog";
}

odooExceptionTitleMap.set(EXCEPTION, _t("Respuesta de ARCA"));
registry.category("error_dialogs").add(EXCEPTION, FiscalWsErrorDialog);
