# -*- coding: utf-8 -*-
"""Partner Ledger: receivable / payable movements grouped by partner."""
from odoo import _, fields, models


class AccountReportPartnerLedger(models.TransientModel):
    _name = 'account.report.partnerledger'
    _inherit = 'account.common.report'
    _description = 'Partner Ledger Report'

    result_selection = fields.Selection(
        [('customer', 'Receivable Accounts'),
         ('supplier', 'Payable Accounts'),
         ('customer_supplier', 'Receivable and Payable Accounts')],
        string='Partner\'s', required=True, default='customer')
    reconciled = fields.Boolean(
        'Include Reconciled Entries', default=False,
        help='Leave off to show only what is still open.')
    initial_balance = fields.Boolean('Include Initial Balances', default=True)
    partner_ids = fields.Many2many(
        'res.partner', string='Partners', help='Leave empty for all partners.')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_partner_ledger'

    # ------------------------------------------------------------------
    def _account_types(self):
        return {
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
            'customer_supplier': ['asset_receivable', 'liability_payable'],
        }[self.result_selection]

    def _partner_domain(self, domain):
        domain = domain + [
            ('account_id.account_type', 'in', self._account_types()),
            ('partner_id', '!=', False),
        ]
        if not self.reconciled:
            domain.append(('full_reconcile_id', '=', False))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        return domain

    def _initial_balances(self):
        domain = self._initial_balance_domain()
        if not domain:
            return {}
        groups = self.env['account.move.line']._read_group(
            self._partner_domain(domain), groupby=['partner_id'], aggregates=['balance:sum'])
        return {partner.id: balance for partner, balance in groups}

    def _compute_rows(self):
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        lines = MoveLine.search(
            self._partner_domain(self._base_domain()), order='partner_id, date, id')
        initials = self._initial_balances() if self.initial_balance else {}

        by_partner = {}
        for line in lines:
            by_partner.setdefault(line.partner_id, MoveLine)
            by_partner[line.partner_id] |= line

        partners = self.env['res.partner'].browse(
            sorted(set(p.id for p in by_partner) | set(initials)))
        partners = partners.sorted(lambda p: (p.display_name or '', p.id))

        rows, sequence = [], 0
        for partner in partners:
            movements = by_partner.get(partner, MoveLine)
            opening = initials.get(partner.id, 0.0)
            closing = opening + sum(movements.mapped('balance'))
            if not movements and not opening:
                continue

            sequence += 1
            rows.append({
                'sequence': sequence,
                'is_group': True,
                'level': 0,
                'partner_id': partner.id,
                'label': partner.display_name,
                'debit': sum(movements.mapped('debit')),
                'credit': sum(movements.mapped('credit')),
                'balance': closing,
                'cumulative': closing,
            })
            if self.initial_balance:
                sequence += 1
                rows.append({
                    'sequence': sequence,
                    'level': 1,
                    'partner_id': partner.id,
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
                    'partner_id': partner.id,
                    'account_id': move_line.account_id.id,
                    'account_name': move_line.account_id.display_name or '',
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
        return self._create_rows('leih.report.ledger.line', rows, _('Partner Ledger'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.ledger.line', _('Partner Ledger'),
            'leih_account_v8.view_report_ledger_line_list', records)
