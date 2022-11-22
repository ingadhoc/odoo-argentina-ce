odoo.define('l10n_ar_pos_afipws_fe.pos_order',function(require){
    "use strict"
    var models = require("point_of_sale.models");
    var SuperPosModel = models.PosModel.prototype;
    var SuperOrder = models.Order.prototype;
    var rpc = require('web.rpc');
    this.afip_invoice_data = {};

    models.PosModel = models.PosModel.extend({

            _flush_orders: function(orders, options) {
                let self = this;
                console.log(self);
                let result;
                result =  SuperPosModel._flush_orders.call(this,orders, options);
                result.then(function(order_server_id){
                    if (options['to_invoice']){
                        console.log(order_server_id);
                        rpc.query({
                            model: 'pos.order',
                            method: 'read',
                            args:[order_server_id, [
                                'l10n_ar_afip_qr_image',
                                'afip_auth_mode',
                                'afip_auth_code',
                                'afip_auth_code_due',
                                'account_move',
                                'pos_reference',
                                'company_id']
                            ]
                        }).then(function(vals){
                            var order_ids = self.get('orders').models;
                            console.log(order_ids);

                            _.each(vals, function (order_data) {
                                let line = order_ids.findIndex(function (item) {
                                    return item['name'] == order_data['pos_reference']

                                });
                                console.log(line);
                                if (line != -1){
                                    order_ids[line] = {
                                        ...order_ids[line],
                                        ...order_data

                                    }
                                }
                            });
                            console.log(order_ids);
                        });
                    }
                });


                return result

             }
    });
   models.Order = models.Order.extend({
        export_for_printing: function(){
            console.log(this);

            var receipt = SuperOrder.export_for_printing.call(this);
            if(this.to_invoice){
                receipt.l10n_ar_afip_qr_image = this.l10n_ar_afip_qr_image;
                receipt.afip_auth_mode = this.afip_auth_mode;
                receipt.afip_auth_code = this.afip_auth_code;
                receipt.afip_auth_code_due = this.afip_auth_code_due;
                receipt.account_move = this.account_move;
                receipt.pos_reference = this.pos_reference;
                receipt.company_id = this.company_id;

            }
            console.log(receipt);
            return receipt
        }
   });

});

