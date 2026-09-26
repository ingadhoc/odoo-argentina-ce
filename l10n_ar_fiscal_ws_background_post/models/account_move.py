##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
import logging

from odoo import api, fields, models
from odoo.addons.l10n_ar_fiscal_ws.models.exceptions import FiscalWsError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------- marking

    def _post(self, soft=True):
        """Deferring to the queue comes before asking for the authorization.

        Which of the two `_post` of the chain runs first depends on the order the
        modules load, and with the batch outside, an invoice on its way to the queue
        would be sent to the service all the same: the batch posts each invoice with
        `super()`, sees it come back unposted, and asks for a voucher that nobody
        numbered. Settling the deferral here leaves the order out of the question.
        """
        force = self.env.context.get("force_background_post")
        to_defer = self.filtered(lambda x: x.move_type in ("out_invoice", "out_refund")) if force else self.browse()
        if not to_defer:
            return super()._post(soft=soft)
        to_defer._schedule_background_post(False if force is True else fields.Datetime.to_datetime(force))
        rest = (self - to_defer).with_context(force_background_post=False)
        return super(AccountMove, rest)._post(soft=soft) if rest else self.browse()

    # ------------------------------------------------------------- background post

    @api.model
    def _cron_background_post_invoices(self, ids=None):
        """Post the queue of electronic invoices in batches: one request per batch.

        The original cron posts one by one, and a batch of one is the flow of always,
        so without this the queue never gets anything out of asking for several
        vouchers at a time. The rest of the queue keeps going one by one.
        """
        moves = self.browse(ids) if ids is not None else self._get_background_post_due_moves()
        to_authorize = moves._l10n_ar_to_authorize()
        if not to_authorize:
            return super()._cron_background_post_invoices(ids=ids)

        cron = self.env["ir.cron"]
        remaining_time = cron._commit_progress(remaining=len(moves))
        # inside a batch the invoices travel from the oldest to the newest, which is the
        # order the service numbers and accepts them in; that beats the priority of the
        # queue, where a rescheduled one goes after the healthy ones
        queue = to_authorize._l10n_ar_batches()
        while queue:
            if remaining_time <= 0:
                _logger.info("Background post cron ran out of time, %s batches left for the next run", len(queue))
                return
            batch = queue.pop(0)
            settled, retry = batch._l10n_ar_background_post_batch()
            if retry:
                queue.insert(0, retry)
            remaining_time = cron._commit_progress(processed=settled)

        rest = moves - to_authorize
        if rest:
            super()._cron_background_post_invoices(ids=rest.ids)

    def _l10n_ar_background_post_batch(self):
        """Post one batch of the queue and deal with what it leaves behind.

        Returns (how many invoices of the batch are settled, the ones worth sending
        again in this same run).
        """
        try:
            self.journal_id._l10n_ar_lock(self.l10n_latam_document_type_id)
        except FiscalWsError as error:
            # somebody else is invoicing this journal: no invoice of the batch failed,
            # so none is charged an attempt and the next run takes them again
            _logger.info("Background post leaves %s invoices for the next run: %s", len(self), error)
            return 0, self.browse()

        try:
            self.action_post()
        except FiscalWsError as error:
            self.env.cr.rollback()
            # the service answers in order and refuses everything behind the first bad
            # one, which the module gives back its number: what is left in draft opens
            # with the refused one, and the rest never reached the service
            pending = self.filtered(lambda x: x.state == "draft")
            refused = pending[:1]
            refused._l10n_ar_background_post_failed(error)
            return len(self) - len(pending) + len(refused), pending - refused
        except Exception as error:  # noqa: BLE001
            self.env.cr.rollback()
            pending = self.filtered(lambda x: x.state == "draft")
            # not an answer of the service, so there is no telling which invoice broke:
            # the original circuit takes them one by one and blames the right one
            _logger.warning("Background post batch failed, retrying one by one: %s", error)
            super()._cron_background_post_invoices(ids=pending.ids)
        return len(self), self.browse()

    def _l10n_ar_background_post_failed(self, error):
        """What the original cron does with an invoice that failed: reschedule it, or
        give up and leave the reason on the invoice."""
        self.ensure_one()
        if self._reschedule_background_post():
            _logger.warning(
                "Error while trying to post invoice %s in background, retry %s of %s scheduled for %s: %s",
                self.name or self.id,
                self.background_post_attempts,
                self._get_background_post_max_retries(),
                self.background_post_date,
                error,
            )
            return
        self._unschedule_background_post()
        try:
            with self.env.cr.savepoint():
                self._notify_background_post_error(error)
        except Exception:
            # the notification may have left the cursor aborted, keep at least the state
            self.env.cr.rollback()
            self._unschedule_background_post()
            _logger.exception("Could not notify the background post error of invoice %s", self.id)
        _logger.error("Error while trying to post invoice %s in background: %s", self.name or self.id, error)
