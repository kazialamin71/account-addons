# -*- coding: utf-8 -*-
"""Trial Balance: one line per account with opening, debit, credit and balance."""
from odoo import _, fields, models


class AccountBalanceReport(models.TransientModel):
    _name = 'account.balance.report'
    _inherit = 'account.common.report'
    _description = 'Trial Balance Report'

    display_account = fields.Selection(
        [('all', 'All'),
         ('movement', 'With movements'),
         ('not_zero', 'With balance not equal to zero')],
        string='Display Accounts', required=True, default='movement')
    initial_balance = fields.Boolean(
        'Show Initial Balances', default=True,
        help='Add a column with each account balance before the reporting window.')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_trial_balance'

    def _compute_rows(self):
        self.ensure_one()
        MoveLine = self.env['account.move.line']

        movements = {
            account.id: (debit, credit, balance)
            for account, debit, credit, balance in MoveLine._read_group(
                self._base_domain(), groupby=['account_id'],
                aggregates=['debit:sum', 'credit:sum', 'balance:sum'])
        }
        initials = {}
        if self.initial_balance:
            initial_domain = self._initial_balance_domain()
            if initial_domain:
                initials = {
                    account.id: balance
                    for account, balance in MoveLine._read_group(
                        initial_domain, groupby=['account_id'], aggregates=['balance:sum'])
                }

        if self.display_account == 'all':
            accounts = self.env['account.account'].search(
                [('company_ids', 'in', self.company_id.id)])
        else:
            accounts = self.env['account.account'].browse(
                sorted(set(movements) | set(initials)))
        accounts = accounts.sorted(lambda a: (a.code or '', a.id))

        currency = self.company_id.currency_id
        rows, sequence = [], 0
        for account in accounts:
            debit, credit, balance = movements.get(account.id, (0.0, 0.0, 0.0))
            opening = initials.get(account.id, 0.0)
            closing = opening + balance

            if self.display_account == 'movement' and not debit and not credit and not opening:
                continue
            if self.display_account == 'not_zero' and currency.is_zero(closing):
                continue

            sequence += 1
            rows.append({
                'sequence': sequence,
                'account_id': account.id,
                'code': account.code,
                'name': account.name,
                'initial_balance': opening,
                'debit': debit,
                'credit': credit,
                'balance': closing,
            })
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.balance.line', rows, _('Trial Balance'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.balance.line', _('Trial Balance'),
            'leih_account_v8.view_report_balance_line_list', records)
