odoo.define('afip.caea', function (require) {
"use strict";

var SystrayMenu = require('web.SystrayMenu');
var Widget = require('web.Widget');
//var model_obj = new instance.web.Model('ir.model.data');

var ActionMenu = Widget.extend({
   template: 'systray_afip.caea',
   events: {
      'click .caea_label': 'onclick_caea_icon',
   },
   onclick_caea_icon:function(){
      var action = {
              type: 'ir.actions.act_window',
              res_model: 'pyafipws.dummy',
              view_type: 'form',
              views:[[false, 'form']],
              target: 'new',
      };
                             
      this.do_action(action);
   },
   //some functions

   });

   SystrayMenu.Items.push(ActionMenu);
   return ActionMenu;
});


