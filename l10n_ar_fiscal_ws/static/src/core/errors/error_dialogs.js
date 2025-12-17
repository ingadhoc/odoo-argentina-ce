import { Dialog } from "@web/core/dialog/dialog";
import {
    ErrorDialog,
    odooExceptionTitleMap,
    standardErrorDialogProps
} from "@web/core/errors/error_dialogs";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// -----------------------------------------------------------------------------
// ARCA Service Error Dialog
// -----------------------------------------------------------------------------
export class ArcaServiceErrorDialog extends ErrorDialog {
    static template = "l10n_ar_fiscal_ws.ArcaServiceErrorDialog";
    static title = _t("ARCA Service Error");
    static components = { Dialog };
    static props = { ...standardErrorDialogProps };

    // setup() {
    //     super.setup();
    //     this.arcaErrorCode = this.props.data?.arca_error_code || null;
    //     this.arcaService = this.props.data?.arca_service || null;
    //     this.arcaDetails = this.props.data?.arca_details || null;
    // }

}


// Add custom error mappings to the existing map
const arcaExceptionTitleMap = new Map([
    ["odoo.addons.l10n_ar_fiscal_ws.models.exceptions.ArcaError", _t("ARCA Error")],

]);

// Merge with existing exception title map
arcaExceptionTitleMap.forEach((value, key) => {
    odooExceptionTitleMap.set(key, value);
});

// Register custom error dialogs
registry
    .category("error_dialogs")
    .add("odoo.addons.l10n_ar_fiscal_ws.models.exceptions.ArcaError", ArcaServiceErrorDialog);
