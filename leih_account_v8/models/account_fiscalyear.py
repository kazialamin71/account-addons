# -*- coding: utf-8 -*-
"""Fiscal years, as they existed in Odoo 8.

Modern Odoo controls what may be posted through lock dates only. This restores
the explicit ``account.fiscalyear`` record that owns a set of periods, can be
closed, and against which the classic financial reports are run.
"""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountFiscalyear(models.Model):
    _name = 'account.fiscalyear'
    _description = 'Fiscal Year'
    _order = 'date_start, id'

    name = fields.Char('Fiscal Year', required=True)
    code = fields.Char('Code', size=6, required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    date_start = fields.Date('Start Date', required=True)
    date_stop = fields.Date('End Date', required=True)
    period_ids = fields.One2many(
        'account.period', 'fiscalyear_id', string='Periods')
    state = fields.Selection(
        [('draft', 'Open'), ('done', 'Closed')],
        string='Status', readonly=True, copy=False, default='draft')
    end_journal_period_id = fields.Many2one(
        'account.period', string='End of Year Entries Period', readonly=True, copy=False,
        help='The special period holding the closing / opening entries generated '
             'for this fiscal year.')

    _code_company_uniq = models.Constraint(
        'unique (code, company_id)',
        'The fiscal year code must be unique per company.',
    )

    @api.constrains('date_start', 'date_stop')
    def _check_dates(self):
        for fy in self:
            if fy.date_stop < fy.date_start:
                raise ValidationError(_('The end date of a fiscal year cannot be before its start date.'))

    @api.constrains('date_start', 'date_stop', 'company_id')
    def _check_overlap(self):
        for fy in self:
            overlapping = self.search([
                ('id', '!=', fy.id),
                ('company_id', '=', fy.company_id.id),
                ('date_start', '<=', fy.date_stop),
                ('date_stop', '>=', fy.date_start),
            ], limit=1)
            if overlapping:
                raise ValidationError(_(
                    'Fiscal year %(new)s overlaps %(other)s. Fiscal years of the same '
                    'company may not overlap.',
                    new=fy.name, other=overlapping.name))

    # ------------------------------------------------------------------
    # Period generation
    # ------------------------------------------------------------------
    def _create_periods(self, months):
        """Generate periods of ``months`` length covering the whole year, plus the
        special opening period. Mirrors Odoo 8's create_period/create_period3."""
        Period = self.env['account.period']
        for fy in self:
            if fy.period_ids:
                raise UserError(_(
                    "Fiscal year %s already has periods. Delete them first if you "
                    "want to regenerate.", fy.name))
            # Special opening period, one day long, sitting on the first day.
            Period.create({
                'name': _('Opening Period %s', fy.code),
                'code': ('OP%s' % fy.code)[:12],
                'date_start': fy.date_start,
                'date_stop': fy.date_start,
                'special': True,
                'fiscalyear_id': fy.id,
                'company_id': fy.company_id.id,
            })
            start = fy.date_start
            while start < fy.date_stop:
                stop = start + relativedelta(months=months, days=-1)
                if stop > fy.date_stop:
                    stop = fy.date_stop
                Period.create({
                    'name': '%s/%s' % (start.month, start.year),
                    'code': '%02d/%04d' % (start.month, start.year),
                    'date_start': start,
                    'date_stop': stop,
                    'fiscalyear_id': fy.id,
                    'company_id': fy.company_id.id,
                })
                start = stop + relativedelta(days=1)
        return True

    def create_period(self):
        """Monthly periods."""
        return self._create_periods(1)

    def create_period3(self):
        """Quarterly periods."""
        return self._create_periods(3)

    def action_reopen(self):
        self.write({'state': 'draft'})
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    @api.model
    def find(self, dt=None, exception=True):
        """Return the fiscal year covering ``dt`` (today by default)."""
        dt = dt or fields.Date.context_today(self)
        company = self.env.company
        fy = self.search([
            ('date_start', '<=', dt), ('date_stop', '>=', dt),
            ('company_id', '=', company.id),
        ], limit=1)
        if not fy and exception:
            raise UserError(_(
                'There is no fiscal year covering %(date)s for company %(company)s.\n'
                'Create one under Accounting / Configuration / Periods / Fiscal Years.',
                date=dt, company=company.name))
        return fy.id if fy else False

    def _get_periods(self, special=False):
        """Periods of these fiscal years, optionally including the opening one."""
        self.ensure_one()
        periods = self.period_ids
        if not special:
            periods = periods.filtered(lambda p: not p.special)
        return periods

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for fy in self:
            fy.display_name = '%s [%s]' % (fy.name, fy.code) if fy.code else fy.name
