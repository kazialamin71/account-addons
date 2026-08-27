# -*- coding: utf-8 -*-
"""Balance Sheet / Profit & Loss, driven by an ``account.financial.report`` tree."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountingReport(models.TransientModel):
    _name = 'accounting.report'
    _inherit = 'account.common.report'
    _description = 'Financial Report (Balance Sheet / P&L)'

    account_report_id = fields.Many2one(
        'account.financial.report', string='Report', required=True,
        default=lambda self: self.env.ref(
            'leih_account_v8.account_financial_report_balancesheet0',
            raise_if_not_found=False))
    debit_credit = fields.Boolean(
        'Show Debit/Credit Columns',
        help='Add the movement debit and credit next to the balance.')

    enable_filter = fields.Boolean('Enable Comparison')
    label_filter = fields.Char(
        'Comparison Column Label', default=lambda self: _('Previous'),
        help='Header printed above the comparison column.')
    date_from_cmp = fields.Date('Comparison Start Date')
    date_to_cmp = fields.Date('Comparison End Date')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_financial'

    # ------------------------------------------------------------------
    def _balances(self, date_from, date_to):
        """{account_id: (debit, credit, balance)} over a date range."""
        self.ensure_one()
        domain = self._base_domain(with_dates=False)
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return {
            account.id: (debit, credit, balance)
            for account, debit, credit, balance in self.env['account.move.line']._read_group(
                domain, groupby=['account_id'],
                aggregates=['debit:sum', 'credit:sum', 'balance:sum'])
        }

    def _node_totals(self, node, balances):
        """(debit, credit, signed balance) aggregated for one report node."""
        accounts = node._accounts()
        debit = credit = balance = 0.0
        for account in accounts:
            account_debit, account_credit, account_balance = balances.get(
                account.id, (0.0, 0.0, 0.0))
            debit += account_debit
            credit += account_credit
            balance += account_balance
        factor = node.sign_factor
        return debit, credit, balance * factor

    def _compute_rows(self):
        self.ensure_one()
        if not self.account_report_id:
            raise UserError(_('Choose the financial report to run.'))

        date_from, date_to = self._get_dates()
        balances = self._balances(date_from, date_to)
        comparison = (self._balances(self.date_from_cmp, self.date_to_cmp)
                      if self.enable_filter else {})

        rows, sequence = [], 0
        for node in self.account_report_id._get_children_by_order():
            debit, credit, balance = self._node_totals(node, balances)
            sequence += 1
            rows.append({
                'sequence': sequence,
                'is_group': True,
                'level': node.level,
                'financial_report_id': node.id,
                'name': node.name,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'balance_cmp': (self._node_totals(node, comparison)[2]
                                if self.enable_filter else 0.0),
            })
            # Optionally expand the node into the accounts behind it.
            if node.display_detail == 'no_detail' or node.type not in ('accounts', 'account_type'):
                continue
            factor = node.sign_factor
            for account in node._accounts().sorted(lambda a: (a.code or '', a.id)):
                account_debit, account_credit, account_balance = balances.get(
                    account.id, (0.0, 0.0, 0.0))
                if not account_debit and not account_credit and not account_balance:
                    continue
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': node.level + 1,
                    'financial_report_id': node.id,
                    'account_id': account.id,
                    'code': account.code,
                    'name': account.name,
                    'debit': account_debit,
                    'credit': account_credit,
                    'balance': account_balance * factor,
                    'balance_cmp': (comparison.get(account.id, (0.0, 0.0, 0.0))[2] * factor
                                    if self.enable_filter else 0.0),
                })
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.balance.line', rows, self.account_report_id.name)

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.balance.line', self.account_report_id.name,
            'leih_account_v8.view_report_financial_line_list', records)
