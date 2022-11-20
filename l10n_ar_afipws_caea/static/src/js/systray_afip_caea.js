/** @odoo-module **/
import SystrayMenu from 'web.SystrayMenu';
import Widget from 'web.Widget';
/**
 * Menu item appended in the systray part of the navbar
 */

//var model_obj = new instance.web.Model('ir.model.data');
const { Component } = owl;
   var CaeaMenu = Widget.extend({
      name: 'caea_menu',
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


SystrayMenu.Items.push(CaeaMenu);

export default CaeaMenu;

