# -*- coding: utf-8 -*-
"""Accounting periods (Odoo 8 ``account.period``).

A period is the smallest closable unit of the ledger. Journal entries carry a
``period_id`` and cannot be posted into a period that has been closed, which is
the Odoo 8 equivalent of (and complementary to) Odoo 19's lock dates.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPeriod(models.Model):
    _name = 'account.period'
    _description = 'Accounting Period'
    _order = 'date_start, special desc, id'

    name = fields.Char('Period Name', required=True)
    code = fields.Char('Code', size=12)
    special = fields.Boolean(
        'Opening/Closing Period',
        help='These periods can overlap the regular periods. They carry the '
             'opening and closing entries of the fiscal year.')
    date_start = fields.Date('Start of Period', required=True)
    date_stop = fields.Date('End of Period', required=True)
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear', string='Fiscal Year', required=True,
        index=True, ondelete='cascade')
    state = fields.Selection(
        [('draft', 'Open'), ('done', 'Closed')],
        string='Status', readonly=True, copy=False, default='draft',
        help='Once a period is closed no journal entry may be posted into it.')
    company_id = fields.Many2one(
        'res.company', related='fiscalyear_id.company_id', string='Company',
        store=True, readonly=True)

    _name_company_uniq = models.Constraint(
        'unique (name, company_id)',
        'The period name must be unique per company.',
    )

    @api.constrains('date_start', 'date_stop')
    def _check_dates(self):
        for period in self:
            if period.date_stop < period.date_start:
                raise ValidationError(_('The end of a period cannot be before its start.'))

    @api.constrains('date_start', 'date_stop', 'fiscalyear_id')
    def _check_within_fiscalyear(self):
        for period in self:
            fy = period.fiscalyear_id
            if period.date_start < fy.date_start or period.date_stop > fy.date_stop:
                raise ValidationError(_(
                    'Period %(period)s must stay inside its fiscal year '
                    '(%(start)s .. %(stop)s).',
                    period=period.name, start=fy.date_start, stop=fy.date_stop))

    @api.constrains('date_start', 'date_stop', 'special', 'company_id')
    def _check_overlap(self):
        """Regular periods may not overlap each other; special periods may."""
        for period in self:
            if period.special:
                continue
            overlapping = self.search([
                ('id', '!=', period.id),
                ('special', '=', False),
                ('company_id', '=', period.company_id.id),
                ('date_start', '<=', period.date_stop),
                ('date_stop', '>=', period.date_start),
            ], limit=1)
            if overlapping:
                raise ValidationError(_(
                    'Period %(new)s overlaps %(other)s. Regular periods may not overlap.',
                    new=period.name, other=overlapping.name))

    # ------------------------------------------------------------------
    @api.model
    def find(self, dt=None):
        """Open, non-special periods covering ``dt``."""
        dt = dt or fields.Date.context_today(self)
        company = self.env.company
        periods = self.search([
            ('date_start', '<=', dt), ('date_stop', '>=', dt),
            ('special', '=', False), ('company_id', '=', company.id),
        ])
        if not periods:
            raise UserError(_(
                'There is no open accounting period covering %(date)s for company '
                '%(company)s.\nCreate the fiscal year and its periods under '
                'Accounting / Configuration / Periods.',
                date=dt, company=company.name))
        return periods

    def next(self, period, step=1):
        """The period ``step`` positions after ``period`` (Odoo 8 helper)."""
        ids = self.search([], order='date_start').ids
        if period.id not in ids:
            return False
        index = ids.index(period.id) + step
        if index < 0 or index >= len(ids):
            return False
        return ids[index]

    def action_draft(self):
        """Re-open closed periods (and their fiscal year)."""
        for period in self:
            if period.fiscalyear_id.state == 'done':
                period.fiscalyear_id.state = 'draft'
        self.write({'state': 'draft'})
        return True

    def action_done(self):
        self.write({'state': 'done'})
        return True

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for period in self:
            period.display_name = (
                '%s (%s)' % (period.name, period.code) if period.code else period.name)

    def _check_open(self, action=None):
        """Raise if any of these periods is closed."""
        closed = self.filtered(lambda p: p.state == 'done')
        if closed:
            raise UserError(_(
                'Period %(periods)s is closed. %(what)s',
                periods=', '.join(closed.mapped('name')),
                what=action or _('No journal entry can be posted into it.')))
