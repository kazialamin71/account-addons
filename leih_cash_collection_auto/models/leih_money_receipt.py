import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LeihMoneyReceipt(models.Model):
    """Every section of LEIS books its money through a receipt, so this is the
    one place that has to notice an amount coming in."""
    _inherit = 'leih.money.receipt'

    opd_ticket_id = fields.Many2one('opd.ticket', string='OPD Ticket', readonly=True)
    cash_collection_line_id = fields.Many2one(
        'cash.collection.line', string='Cash Collection Line',
        readonly=True, copy=False, ondelete='set null')
    cash_collection_id = fields.Many2one(
        'cash.collection', string='Cash Collection',
        related='cash_collection_line_id.cash_collection_line_id',
        store=True, readonly=True)

    # The documents a receipt can be taken against. Every caller sets the right
    # one explicitly, so one arriving as a default is always a context leak.
    _SOURCE_FIELDS = (
        'bill_id', 'admission_id', 'general_admission_id',
        'optics_sale_id', 'opd_ticket_id',
    )

    @api.model
    def default_get(self, fields_list):
        """Never let a source document be filled in from the context.

        The admission payment action opens its wizard with
        ``default_admission_id`` set to a ``hospital.admission`` id, but this
        model's ``admission_id`` points at ``leih.admission``. Odoo matches
        defaults by field name, not by target model, so the receipt would be
        stamped with an id belonging to a different table and the insert fails
        on the foreign key.
        """
        defaults = super().default_get(fields_list)
        for name in self._SOURCE_FIELDS:
            defaults.pop(name, None)
        return defaults

    def _collection_section(self):
        """Which section of the hospital the money came from."""
        self.ensure_one()
        if self.opd_ticket_id:
            return 'opd'
        if self.optics_sale_id:
            return 'optics'
        if self.admission_id or self.general_admission_id:
            return 'admission'
        if self.bill_id:
            return 'bill' if self.diagonostic_bill else 'bill_others'
        return False

    def _source_document(self):
        """The bill / admission / OPD record the payment was taken against."""
        self.ensure_one()
        return (self.bill_id or self.admission_id or self.general_admission_id
                or self.optics_sale_id or self.opd_ticket_id)

    def _add_to_cash_collection(self):
        """Put each receipt on its section's sheet. Returns the ones collected."""
        Line = self.env['cash.collection.line']
        Collection = self.env['cash.collection']
        collected = self.browse()

        for receipt in self:
            if receipt.cash_collection_line_id or receipt.state != 'confirm':
                continue
            if not receipt.amount:
                continue
            section = receipt._collection_section()
            if not section:
                continue

            sheet = Collection._open_sheet(section, receipt.date, receipt.type)
            if not sheet:
                # Section not configured yet; leave it for action_collect_pending_receipts.
                receipt.already_collected = False
                _logger.info(
                    "Money receipt %s not collected: no cash collection account "
                    "configured for section %r.", receipt.name, section)
                continue

            source = receipt._source_document()
            line = Line.create({
                'cash_collection_line_id': sheet.id,
                'mr_no': receipt.id,
                'opd_id': receipt.opd_ticket_id.id or False,
                'bill_admission_opd_id': source.display_name if source else '',
                'amount': receipt.amount,
            })
            receipt.cash_collection_line_id = line.id
            receipt.already_collected = True
            sheet._recompute_total()
            collected |= receipt

        return collected

    @api.model_create_multi
    def create(self, vals_list):
        receipts = super().create(vals_list)
        receipts._add_to_cash_collection()
        return receipts
