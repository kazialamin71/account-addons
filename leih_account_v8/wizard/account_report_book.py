# -*- coding: utf-8 -*-
"""Cash Book, Bank Book and Day Book.

All three are the same listing over a different slice of journals, which is why
Odoo 8 shipped them as one report with a switch.
"""
from odoo import _, fields, models


class AccountBookReport(models.TransientModel):
    _name = 'account.book.report'
    _inherit = 'account.common.report'
    _description = 'Cash / Bank / Day Book'

    book_type = fields.Selection(
        [('cash', 'Cash Book'), ('bank', 'Bank Book'), ('day', 'Day Book')],
        string='Book', required=True, default='cash')
    show_opening = fields.Boolean(
        'Show Opening Balance', default=True,
        help='Start each book with the balance carried in from before the period.')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_book'

    def _book_label(self):
        return dict(self._fields['book_type'].selection)[self.book_type]

    def _book_domain(self, domain):
        """Restrict to the journals this book covers."""
        self.ensure_one()
        if self.book_type == 'cash':
            return domain + [('journal_id.type', '=', 'cash')]
        if self.book_type == 'bank':
            return domain + [('journal_id.type', '=', 'bank')]
        return domain

    def _opening_balances(self):
        domain = self._initial_balance_domain()
        if not domain or not self.show_opening:
            return {}
        groups = self.env['account.move.line']._read_group(
            self._book_domain(domain), groupby=['journal_id'], aggregates=['balance:sum'])
        return {journal.id: balance for journal, balance in groups}

    def _compute_rows(self):
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        # The Day Book is chronological across every journal; the cash and bank
        # books read journal by journal.
        order = 'date, id' if self.book_type == 'day' else 'journal_id, date, id'
        lines = MoveLine.search(self._book_domain(self._base_domain()), order=order)
        openings = self._opening_balances()

        rows, sequence = [], 0
        if self.book_type == 'day':
            running = 0.0
            for line in lines:
                running += line.balance
                sequence += 1
                rows.append(self._line_row(sequence, line, running, level=0))
            return rows

        by_journal = {}
        for line in lines:
            by_journal.setdefault(line.journal_id, []).append(line)

        journal_ids = set(j.id for j in by_journal) | set(openings)
        journals = self.env['account.journal'].browse(sorted(journal_ids)).sorted(
            lambda j: (j.code or '', j.id))
        for journal in journals:
            items = by_journal.get(journal, [])
            opening = openings.get(journal.id, 0.0)
            if not items and not opening:
                continue
            sequence += 1
            rows.append({
                'sequence': sequence,
                'is_group': True,
                'level': 0,
                'journal_id': journal.id,
                'label': '%s - %s' % (journal.code or '', journal.name),
                'debit': sum(i.debit for i in items),
                'credit': sum(i.credit for i in items),
                'balance': opening + sum(i.balance for i in items),
            })
            if self.show_opening:
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': 1,
                    'journal_id': journal.id,
                    'label': _('Opening Balance'),
                    'debit': opening if opening > 0 else 0.0,
                    'credit': -opening if opening < 0 else 0.0,
                    'balance': opening,
                    'cumulative': opening,
                })
            running = opening
            for line in items:
                running += line.balance
                sequence += 1
                rows.append(self._line_row(sequence, line, running, level=1))
        return rows

    def _line_row(self, sequence, line, running, level):
        return {
            'sequence': sequence,
            'level': level,
            'journal_id': line.journal_id.id,
            'account_id': line.account_id.id,
            'account_name': line.account_id.display_name or '',
            'partner_id': line.partner_id.id,
            'partner_name': line.partner_id.display_name or '',
            'move_id': line.move_id.id,
            'move_name': line.move_id.name or '',
            'move_line_id': line.id,
            'date': line.date,
            'label': line.name or '',
            'ref': line.move_id.ref or '',
            'debit': line.debit,
            'credit': line.credit,
            'balance': line.balance,
            'cumulative': running,
        }

    def _materialise(self, rows):
        return self._create_rows('leih.report.ledger.line', rows, self._book_label())

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.ledger.line', self._book_label(),
            'leih_account_v8.view_report_ledger_line_list', records)
