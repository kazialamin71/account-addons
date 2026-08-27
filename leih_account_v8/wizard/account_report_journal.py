# -*- coding: utf-8 -*-
"""Journal report: the journal items of each journal, in posting order."""
from odoo import _, fields, models


class AccountReportJournal(models.TransientModel):
    _name = 'account.report.journal'
    _inherit = 'account.common.report'
    _description = 'Journal Report'

    group_entries = fields.Boolean(
        'Group by Entry', default=True,
        help='Insert a subtotal row per journal entry rather than listing bare items.')
    sort_selection = fields.Selection(
        [('date', 'Date'), ('move_name', 'Entry Number')],
        string='Entries Sorted by', required=True, default='date')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_journal'

    def _order_clause(self):
        return 'date, move_id, id' if self.sort_selection == 'date' else 'move_id, id'

    def _compute_rows(self):
        self.ensure_one()
        lines = self.env['account.move.line'].search(
            self._base_domain(), order='journal_id, ' + self._order_clause())

        by_journal = {}
        for line in lines:
            by_journal.setdefault(line.journal_id, []).append(line)

        rows, sequence = [], 0
        for journal in sorted(by_journal, key=lambda j: (j.code or '', j.id)):
            items = by_journal[journal]
            sequence += 1
            rows.append({
                'sequence': sequence,
                'is_group': True,
                'level': 0,
                'journal_id': journal.id,
                'label': '%s - %s' % (journal.code or '', journal.name),
                'debit': sum(i.debit for i in items),
                'credit': sum(i.credit for i in items),
                'balance': sum(i.balance for i in items),
            })
            current_move, running = None, 0.0
            for item in items:
                if self.group_entries and item.move_id != current_move:
                    current_move = item.move_id
                    running = 0.0
                running += item.balance
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': 1,
                    'journal_id': journal.id,
                    'account_id': item.account_id.id,
                    'account_name': item.account_id.display_name or '',
                    'partner_id': item.partner_id.id,
                    'partner_name': item.partner_id.display_name or '',
                    'move_id': item.move_id.id,
                    'move_name': item.move_id.name or '',
                    'move_line_id': item.id,
                    'date': item.date,
                    'label': item.name or '',
                    'ref': item.move_id.ref or '',
                    'debit': item.debit,
                    'credit': item.credit,
                    'balance': item.balance,
                    'cumulative': running,
                })
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.ledger.line', rows, _('Journal Report'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.ledger.line', _('Journal Report'),
            'leih_account_v8.view_report_ledger_line_list', records)
