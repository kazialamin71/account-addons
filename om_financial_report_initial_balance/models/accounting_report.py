from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountingReport(models.TransientModel):
    _inherit = 'accounting.report'

    initial_balance = fields.Boolean(
        string='Include Initial Balance', default=True,
        help="Show the balance carried into the period, that is everything "
             "booked strictly before the reporting window starts.")

    def _initial_balances(self):
        """{account_id: balance strictly before the reporting window}."""
        domain = self._initial_balance_domain()
        if not domain:
            return {}
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['account_id'], aggregates=['balance:sum'])
        return {account.id: balance for account, balance in groups}

    def _node_initial(self, node, initials):
        """Initial balance aggregated for one report node, with its sign applied."""
        total = sum(initials.get(account.id, 0.0) for account in node._accounts())
        return total * node.sign_factor

    def _compute_rows(self):
        """Mirror of ``leih_account_v8``'s rows, plus an initial balance per row.

        This restates the loop instead of enriching ``super()`` because a report
        carrying opening balances must also list accounts that moved in no way
        during the period yet still carry a balance into it. The original drops
        those rows, which would leave the account lines disagreeing with the
        group totals above them.
        """
        self.ensure_one()
        if not self.initial_balance:
            return super()._compute_rows()
        if not self.account_report_id:
            raise UserError(_('Choose the financial report to run.'))

        date_from, date_to = self._get_dates()
        balances = self._balances(date_from, date_to)
        comparison = (self._balances(self.date_from_cmp, self.date_to_cmp)
                      if self.enable_filter else {})
        initials = self._initial_balances()

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
                'initial_balance': self._node_initial(node, initials),
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
                account_initial = initials.get(account.id, 0.0)
                if not any((account_debit, account_credit, account_balance, account_initial)):
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
                    'initial_balance': account_initial * factor,
                    'balance_cmp': (comparison.get(account.id, (0.0, 0.0, 0.0))[2] * factor
                                    if self.enable_filter else 0.0),
                })
        return rows
