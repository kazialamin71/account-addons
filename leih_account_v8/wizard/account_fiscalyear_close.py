# -*- coding: utf-8 -*-
"""Year-end: generate the opening entry, and close a fiscal year.

The opening entry restates every balance-sheet account at its closing balance in
the *new* year's opening period, and dumps the accumulated profit or loss onto
the retained-earnings account. Built that way it balances by construction: the
whole ledger nets to zero, so the balance-sheet side and the earnings side are
exact mirrors of each other.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountFiscalyearClose(models.TransientModel):
    _name = 'account.fiscalyear.close'
    _description = 'Generate Opening Entries'

    fy_id = fields.Many2one(
        'account.fiscalyear', string='Fiscal Year to Close', required=True,
        domain="[('state', '=', 'draft')]")
    fy2_id = fields.Many2one(
        'account.fiscalyear', string='New Fiscal Year', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Opening Entries Journal', required=True,
        domain="[('type', '=', 'general')]")
    period_id = fields.Many2one(
        'account.period', string='Opening Entries Period', required=True,
        help='Period of the new fiscal year that receives the opening entry. '
             'Use its special opening period.')
    retained_earnings_account_id = fields.Many2one(
        'account.account', string='Retained Earnings Account', required=True,
        domain="[('internal_group', '=', 'equity')]",
        help='Equity account that receives the accumulated result carried forward.')
    report_name = fields.Char(
        'Entry Reference', required=True,
        default=lambda self: _('End of Fiscal Year Entry'))
    sure = fields.Boolean('I confirm, generate the opening entry')

    @api.onchange('fy2_id')
    def _onchange_fy2_id(self):
        """Default to the new year's special opening period."""
        if not self.fy2_id:
            return
        special = self.fy2_id.period_ids.filtered('special')[:1]
        self.period_id = special or self.fy2_id.period_ids[:1]

    def _check(self):
        self.ensure_one()
        if not self.sure:
            raise UserError(_('Tick the confirmation box to generate the opening entry.'))
        if self.fy_id == self.fy2_id:
            raise UserError(_('The new fiscal year must be different from the one being closed.'))
        if self.fy_id.state == 'done':
            raise UserError(_('Fiscal year %s is already closed.', self.fy_id.name))
        if self.period_id.fiscalyear_id != self.fy2_id:
            raise UserError(_('The opening period must belong to the new fiscal year.'))
        if self.fy_id.end_journal_period_id:
            raise UserError(_(
                'Fiscal year %s already has an opening entry. Delete that entry '
                'before generating a new one.', self.fy_id.name))
        self.period_id._check_open()

    def action_compute(self):
        """Create and post the opening entry, then close the old year."""
        self.ensure_one()
        self._check()
        company = self.fy_id.company_id

        # Closing balance of every balance-sheet account, from the beginning of
        # time up to the last day of the year being closed.
        balances = self.env['account.move.line']._read_group(
            [('company_id', '=', company.id),
             ('parent_state', '=', 'posted'),
             ('date', '<=', self.fy_id.date_stop),
             ('account_id.include_initial_balance', '=', True)],
            groupby=['account_id'], aggregates=['balance:sum'])

        currency = company.currency_id
        lines, total = [], 0.0
        for account, balance in balances:
            if currency.is_zero(balance):
                continue
            total += balance
            lines.append(fields.Command.create({
                'name': self.report_name,
                'account_id': account.id,
                'debit': balance if balance > 0 else 0.0,
                'credit': -balance if balance < 0 else 0.0,
            }))

        if not lines:
            raise UserError(_(
                'There is nothing to carry forward: no posted balance-sheet '
                'entry exists up to %s.', self.fy_id.date_stop))

        # The counterpart is the accumulated result. Because every posted line in
        # the ledger nets to zero, this is exactly the cumulative P&L.
        if not currency.is_zero(total):
            lines.append(fields.Command.create({
                'name': _('Accumulated Result Carried Forward'),
                'account_id': self.retained_earnings_account_id.id,
                'debit': -total if total < 0 else 0.0,
                'credit': total if total > 0 else 0.0,
            }))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'ref': self.report_name,
            'journal_id': self.journal_id.id,
            'company_id': company.id,
            'date': self.period_id.date_start,
            'period_id': self.period_id.id,
            'line_ids': lines,
        })
        move.action_post()

        self.fy_id.write({'state': 'done', 'end_journal_period_id': self.period_id.id})
        self.fy_id.period_ids.write({'state': 'done'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Opening Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }


class AccountFiscalyearCloseState(models.TransientModel):
    """Close a fiscal year without generating anything."""
    _name = 'account.fiscalyear.close.state'
    _description = 'Close a Fiscal Year'

    fy_id = fields.Many2one(
        'account.fiscalyear', string='Fiscal Year to Close', required=True,
        domain="[('state', '=', 'draft')]")

    def action_close(self):
        self.ensure_one()
        if self.fy_id.state == 'done':
            raise UserError(_('Fiscal year %s is already closed.', self.fy_id.name))
        self.fy_id.write({'state': 'done'})
        self.fy_id.period_ids.write({'state': 'done'})
        return {'type': 'ir.actions.act_window_close'}
