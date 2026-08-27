from odoo import api, fields, models


class OpdTicket(models.Model):
    """OPD took money without ever issuing a money receipt, which left it out of
    every collection and report. Issuing one puts OPD on the same footing as the
    bill, admission and optics counters."""
    _inherit = 'opd.ticket'

    money_receipt_id = fields.Many2one(
        'leih.money.receipt', string='Money Receipt', readonly=True, copy=False)

    def _ensure_money_receipt(self):
        """Issue the receipt for a confirmed ticket that has an amount on it.

        The ticket total is only known once its lines are in, so this is called
        from both create and write rather than from create alone.
        """
        MoneyReceipt = self.env['leih.money.receipt']
        for ticket in self:
            if ticket.money_receipt_id or ticket.state != 'confirmed':
                continue
            if not ticket.total:
                continue
            receipt = MoneyReceipt.create({
                'date': ticket.date or fields.Date.context_today(ticket),
                'opd_ticket_id': ticket.id,
                'amount': ticket.total,
                'bill_total_amount': ticket.total,
                'due_amount': 0.0,
                'p_type': 'advance',
                'user_id': ticket.user_id.id or self.env.user.id,
            })
            ticket.money_receipt_id = receipt.id
            ticket.already_collected = bool(receipt.cash_collection_line_id)

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        tickets._ensure_money_receipt()
        return tickets

    def write(self, vals):
        result = super().write(vals)
        if {'total', 'state'} & set(vals):
            self._ensure_money_receipt()
        return result
