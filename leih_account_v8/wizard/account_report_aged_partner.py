# -*- coding: utf-8 -*-
"""Aged Partner Balance: open items bucketed by how overdue they are."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountAgedTrialBalance(models.TransientModel):
    _name = 'account.aged.trial.balance'
    _inherit = 'account.common.report'
    _description = 'Aged Partner Balance Report'

    period_length = fields.Integer(
        'Bucket Length (days)', required=True, default=30,
        help='Width of each ageing bucket. 30 gives the classic '
             '30 / 60 / 90 / 120 / older columns.')
    result_selection = fields.Selection(
        [('customer', 'Receivable Accounts'),
         ('supplier', 'Payable Accounts'),
         ('customer_supplier', 'Receivable and Payable Accounts')],
        string='Partner\'s', required=True, default='customer')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_aged_partner'

    def _account_types(self):
        return {
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
            'customer_supplier': ['asset_receivable', 'liability_payable'],
        }[self.result_selection]

    def _as_of(self):
        """The date the ageing is measured from."""
        self.ensure_one()
        _date_from, date_to = self._get_dates()
        return date_to or fields.Date.context_today(self)

    def _bucket_labels(self):
        self.ensure_one()
        length = self.period_length
        return [
            _('Not Due'),
            _('1 - %s', length),
            _('%(from)s - %(to)s', **{'from': length + 1, 'to': 2 * length}),
            _('%(from)s - %(to)s', **{'from': 2 * length + 1, 'to': 3 * length}),
            _('%(from)s - %(to)s', **{'from': 3 * length + 1, 'to': 4 * length}),
            _('Older than %s', 4 * length),
        ]

    def _compute_rows(self):
        self.ensure_one()
        if self.period_length <= 0:
            raise UserError(_('The bucket length must be at least one day.'))
        as_of = self._as_of()

        domain = self._base_domain(with_dates=False) + [
            ('account_id.account_type', 'in', self._account_types()),
            ('partner_id', '!=', False),
            ('date', '<=', as_of),
            ('reconciled', '=', False),
        ]
        lines = self.env['account.move.line'].search(domain)

        buckets = {}
        for line in lines:
            due = line.date_maturity or line.date
            overdue = (as_of - due).days
            if overdue <= 0:
                slot = 0
            else:
                slot = min((overdue - 1) // self.period_length + 1, 5)
            amounts = buckets.setdefault(line.partner_id, [0.0] * 6)
            amounts[slot] += line.amount_residual

        currency = self.company_id.currency_id
        rows, sequence = [], 0
        for partner in sorted(buckets, key=lambda p: (p.display_name or '', p.id)):
            amounts = buckets[partner]
            total = sum(amounts)
            if currency.is_zero(total) and all(currency.is_zero(a) for a in amounts):
                continue
            sequence += 1
            rows.append({
                'sequence': sequence,
                'partner_id': partner.id,
                'partner_name': partner.display_name,
                'not_due': amounts[0],
                'period0': amounts[1],
                'period1': amounts[2],
                'period2': amounts[3],
                'period3': amounts[4],
                'period4': amounts[5],
                'total': total,
            })
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.aged.line', rows, _('Aged Partner Balance'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.aged.line', _('Aged Partner Balance'),
            'leih_account_v8.view_report_aged_line_list', records)
