odoo.define('l10n_ar_pos.models', function (require) {
    "use strict";

var { PosGlobalState, Order } = require('point_of_sale.models');
const Registries = require('point_of_sale.Registries');


const PosL10nArPosGlobalState = (PosGlobalState) => class PosL10nArPosGlobalState extends PosGlobalState {
    async _processData(loadedData) {
        await super._processData(...arguments);
        this.l10n_ar_afip_responsibility_type = loadedData['l10n_ar.afip.responsibility.type'];
        this.l10n_latam_identification_type = loadedData['l10n_latam.identification.type'];
    }
    isArgentineanCompany(){
        return this.company.country.code === 'AR';
    }
}
Registries.Model.extend(PosGlobalState, PosL10nArPosGlobalState);

});
