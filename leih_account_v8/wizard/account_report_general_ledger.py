# -*- coding: utf-8 -*-
"""General Ledger: every account with its opening balance and its movements."""
from odoo import _, fields, models


class AccountReportGeneralLedger(models.TransientModel):
    _name = 'account.report.general.ledger'
    _inherit = 'account.common.report'
    _description = 'General Ledger Report'

    initial_balance = fields.Boolean(
        'Include Initial Balances', default=True,
        help='Print an opening line per account with everything booked before '
             'the start of the reporting window.')
    sortby = fields.Selection(
        [('sort_date', 'Date'), ('sort_journal_partner', 'Journal & Partner')],
        string='Sort by', required=True, default='sort_date')
    display_account = fields.Selection(
        [('all', 'All'),
         ('movement', 'With movements'),
         ('not_zero', 'With balance not equal to zero')],
        string='Display Accounts', required=True, default='movement')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_general_ledger'

    # ------------------------------------------------------------------
    def _initial_balances(self):
        """{account_id: balance before the window}."""
        domain = self._initial_balance_domain()
        if not domain:
            return {}
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['account_id'], aggregates=['balance:sum'])
        return {account.id: balance for account, balance in groups}

    def _order_clause(self):
        return ('journal_id, partner_id, date, id' if self.sortby == 'sort_journal_partner'
                else 'date, move_id, id')

    def _compute_rows(self):
        """Build the ordered list of row values for screen and PDF."""
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        lines = MoveLine.search(self._base_domain(), order=self._order_clause())
        initials = self._initial_balances() if self.initial_balance else {}

        by_account = {}
        for line in lines:
            by_account.setdefault(line.account_id.id, []).append(line)

        account_ids = set(by_account) | set(initials)
        if self.display_account == 'all':
            accounts = self.env['account.account'].search(
                [('company_ids', 'in', self.company_id.id)])
        else:
            accounts = self.env['account.account'].browse(sorted(account_ids))
        accounts = accounts.sorted(lambda a: (a.code or '', a.id))

        currency = self.company_id.currency_id
        rows, sequence = [], 0
        for account in accounts:
            movements = by_account.get(account.id, [])
            opening = initials.get(account.id, 0.0)
            closing = opening + sum(m.balance for m in movements)

            if self.display_account == 'movement' and not movements and not opening:
                continue
            if self.display_account == 'not_zero' and currency.is_zero(closing):
                continue

            sequence += 1
            rows.append({
                'sequence': sequence,
                'is_group': True,
                'level': 0,
                'account_id': account.id,
                'label': '%s %s' % (account.code or '', account.name),
                'debit': sum(m.debit for m in movements),
                'credit': sum(m.credit for m in movements),
                'balance': closing,
                'cumulative': closing,
            })
            if self.initial_balance:
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': 1,
                    'account_id': account.id,
                    'label': _('Initial Balance'),
                    'debit': opening if opening > 0 else 0.0,
                    'credit': -opening if opening < 0 else 0.0,
                    'balance': opening,
                    'cumulative': opening,
                })

            cumulative = opening
            for move_line in movements:
                cumulative += move_line.balance
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': 1,
                    'account_id': account.id,
                    'partner_id': move_line.partner_id.id,
                    'partner_name': move_line.partner_id.display_name or '',
                    'journal_id': move_line.journal_id.id,
                    'move_id': move_line.move_id.id,
                    'move_name': move_line.move_id.name or '',
                    'move_line_id': move_line.id,
                    'date': move_line.date,
                    'date_maturity': move_line.date_maturity,
                    'label': move_line.name or '',
                    'ref': move_line.move_id.ref or '',
                    'reconciled': move_line.matching_number or '',
                    'debit': move_line.debit,
                    'credit': move_line.credit,
                    'balance': move_line.balance,
                    'cumulative': cumulative,
                })
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.ledger.line', rows, _('General Ledger'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.ledger.line', _('General Ledger'),
            'leih_account_v8.view_report_ledger_line_list', records)
