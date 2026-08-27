from datetime import datetime, time

from odoo import _, api, fields, models


class CashCollection(models.Model):
    _inherit = 'cash.collection'

    payment_type_id = fields.Many2one(
        'payment.type', string='Payment Type', readonly=True,
        help="Money taken through this payment type. A sheet carries one debit "
             "account, so each payment type collects onto its own sheet.")
    auto_generated = fields.Boolean(
        string='Created Automatically', readonly=True, copy=False,
        help="Opened by a money receipt rather than typed in by hand.")

    def _recompute_total(self):
        for sheet in self:
            sheet.total = sum(sheet.cash_collection_lines.mapped('amount'))

    @api.model
    def _open_sheet(self, section_type, date, payment_type):
        """The pending sheet money of this kind belongs on, opened if needed.

        Sheets are per section and per day, split further by payment type because
        a sheet holds a single debit account and cash cannot share one with card.
        Returns an empty recordset when the section has no configured credit
        account, so a missing configuration never blocks taking a payment.
        """
        date = date or fields.Date.context_today(self)
        config = self.env['leih.cash.collection.account']._for_section(section_type)
        if not config:
            return self.browse()

        payment_type = payment_type or config.default_payment_type_id
        debit_account = payment_type.account if payment_type else False
        if not debit_account:
            return self.browse()

        sheet = self.search([
            ('type', '=', section_type),
            ('state', '=', 'pending'),
            ('payment_type_id', '=', payment_type.id if payment_type else False),
            ('date', '>=', datetime.combine(date, time.min)),
            ('date', '<=', datetime.combine(date, time.max)),
        ], limit=1)
        if sheet:
            return sheet

        return self.create({
            'name': self.env['ir.sequence'].next_by_code('leih.cash.collection') or _('New'),
            'date': datetime.combine(date, time.min),
            'type': section_type,
            'payment_type_id': payment_type.id if payment_type else False,
            'debit_act_id': debit_account.id,
            'credit_act_id': config.credit_account_id.id,
            'auto_generated': True,
            'total': 0.0,
        })

    @api.model
    def action_collect_pending_receipts(self):
        """Sweep up confirmed receipts that never made it onto a sheet.

        Receipts taken while a section was unconfigured stay uncollected; run this
        once the accounts exist to bring them in.
        """
        pending = self.env['leih.money.receipt'].search([
            ('state', '=', 'confirm'),
            ('cash_collection_line_id', '=', False),
        ])
        collected = pending._add_to_cash_collection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cash Collection'),
                'message': _('%(done)s of %(total)s pending receipts collected.',
                             done=len(collected), total=len(pending)),
                'type': 'success' if collected else 'warning',
                'sticky': False,
            },
        }
