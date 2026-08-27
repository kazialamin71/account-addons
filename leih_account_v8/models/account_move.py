# -*- coding: utf-8 -*-
"""Wire journal entries back onto accounting periods.

Every move gets a ``period_id`` derived from its date (overridable, which is how
Odoo 8 let you push an entry into the special opening/closing period). Posting
into a closed period is refused.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    period_id = fields.Many2one(
        'account.period', string='Period', copy=False, index=True,
        compute='_compute_period_id', store=True, readonly=False, precompute=True,
        help='Accounting period this entry belongs to. Defaults to the open period '
             'covering the entry date; set it manually to book into the special '
             'opening / closing period.')
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear', string='Fiscal Year',
        related='period_id.fiscalyear_id', store=True, readonly=True)

    @api.depends('date', 'company_id')
    def _compute_period_id(self):
        Period = self.env['account.period']
        for move in self:
            # Never move an entry the user has deliberately placed in a period,
            # and never fight a period that already matches the date.
            if move.period_id and move.period_id.date_start <= move.date <= move.period_id.date_stop:
                continue
            if not move.date:
                move.period_id = False
                continue
            period = Period.with_company(move.company_id or self.env.company).search([
                ('date_start', '<=', move.date), ('date_stop', '>=', move.date),
                ('special', '=', False),
                ('company_id', '=', (move.company_id or self.env.company).id),
            ], limit=1)
            move.period_id = period.id if period else False

    def _post(self, soft=True):
        """Refuse to post into a closed period or a closed fiscal year."""
        for move in self:
            period = move.period_id
            if not period:
                # Periods are optional until the user actually defines a fiscal
                # year; only enforce once at least one period exists.
                if self.env['account.period'].search_count([
                    ('company_id', '=', (move.company_id or self.env.company).id),
                ]):
                    raise UserError(_(
                        'No accounting period covers %(date)s for entry %(move)s. '
                        'Create the period or change the entry date.',
                        date=move.date, move=move.display_name))
                continue
            if period.state == 'done':
                raise UserError(_(
                    'Period %(period)s is closed - entry %(move)s cannot be posted into it.',
                    period=period.name, move=move.display_name))
            if period.fiscalyear_id.state == 'done':
                raise UserError(_(
                    'Fiscal year %(fy)s is closed - entry %(move)s cannot be posted into it.',
                    fy=period.fiscalyear_id.name, move=move.display_name))
        return super()._post(soft=soft)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    period_id = fields.Many2one(
        'account.period', related='move_id.period_id', string='Period',
        store=True, index=True, readonly=True)
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear', related='move_id.period_id.fiscalyear_id',
        string='Fiscal Year', store=True, readonly=True)
