##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command, models


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"

    def validate_move(self):
        """Validar la selección de a un comprobante deja al lote sin nada que juntar.

        Los que van por web service se validan con un solo `action_post` —el módulo
        los agrupa y los manda en un pedido—, y el resto sigue validándose de a uno,
        que es lo que el circuito original necesita para guardar el estado de cada
        comprobante y mandar su correo antes de seguir.
        """
        batch = self.move_ids.filtered(lambda move: move.state == "draft")._l10n_ar_to_authorize()
        if not self.count_inv or not batch or self.count_inv > self.batch_size:
            return super().validate_move()
        batch.action_post()
        self.env.cr.commit()  # pylint: disable=invalid-commit
        rest = self.move_ids - batch
        if not rest:
            return {"type": "ir.actions.act_window_close"}
        self.write({"move_ids": [Command.set(rest.ids)], "count_inv": len(rest)})
        return super().validate_move()
